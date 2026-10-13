"""日线一次性导入编排：名单 → 逐票拉取(重试) → 质量门 → 入库/隔离，带断点续传。

用法：
  uv run python -m data_platform.ingest_daily --limit 50        # 验证前 50 只
  nohup uv run python -m data_platform.ingest_daily &           # 全量后台跑
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from data_platform import config
from data_platform.quality.gates import gate_daily
from data_platform.sources.akshare_daily import fetch_daily, fetch_stock_list
from data_platform.store import ch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingest_daily")

STATE_PATH = Path.home() / ".quant-infra" / "state" / "ingest_daily.json"


def load_state() -> set[str]:
    if STATE_PATH.exists():
        return set(json.loads(STATE_PATH.read_text()).get("done", []))
    return set()


def save_state(done: set[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"done": sorted(done)}))


def fetch_with_retry(
    symbol: str, start: str, end: str, adjust: str, attempts: int = 3
) -> pd.DataFrame:
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return fetch_daily(symbol, start, end, adjust=adjust)
        except Exception as exc:  # noqa: BLE001 —— 源站异常形态不可枚举，重试后仍失败则隔离
            last_exc = exc
            time.sleep(1 + 2 * i)
    raise RuntimeError(f"fetch failed after {attempts} attempts: {last_exc}") from last_exc


def fetch_history(symbol: str, start: str, end: str) -> pd.DataFrame:
    """方案 C：每票同时取原始价（none）与前复权（qfq）两套，拼接后统一过门。"""
    frames = [fetch_with_retry(symbol, start, end, adjust) for adjust in ("none", "qfq")]
    return pd.concat(frames, ignore_index=True)


def process_one(symbol: str, start: str, end: str) -> tuple[str, str]:
    """返回 (symbol, ok|quarantine:原因)。客户端在线程内自取（thread-local，非线程安全）。"""
    client = ch.get_client()
    try:
        df = fetch_history(symbol, start, end)
    except Exception as exc:  # noqa: BLE001
        ch.insert_quarantine(client, symbol, "fetch_error", str(exc), "")
        return symbol, "quarantine:fetch_error"

    result = gate_daily(df)
    if not result.ok:
        ch.insert_quarantine(
            client,
            symbol,
            result.reason_summary,
            str(result.violations),
            df.to_json(orient="records"),
        )
        return symbol, f"quarantine:{result.reason_summary}"

    ch.insert_daily(client, df)
    return symbol, "ok"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=config.HISTORY_START)
    parser.add_argument("--end", default=time.strftime("%Y%m%d"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="只导入前 N 只（0=全量）")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    client = ch.get_client()
    stock_list = fetch_stock_list()
    ch.upsert_instruments(client, stock_list)
    log.info("stock list: %d instruments upserted", len(stock_list))

    done = set() if args.no_resume else load_state()
    symbols = [s for s in stock_list["symbol"] if s not in done]
    if args.limit:
        symbols = symbols[: args.limit]
    log.info("to import: %d (resume skipped %d)", len(symbols), len(done))

    stats = {"ok": 0, "quarantine": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process_one, s, args.start, args.end): s for s in symbols}
        for n, fut in enumerate(as_completed(futures), 1):
            symbol, status = fut.result()
            done.add(symbol)
            stats["ok" if status == "ok" else "quarantine"] += 1
            if n % 100 == 0:
                save_state(done)
                bars = ch.count_bars(client)
                log.info("progress %d/%d bars_total=%d stats=%s", n, len(symbols), bars, stats)

    save_state(done)
    log.info("done. stats=%s bars_total=%d", stats, ch.count_bars(client))


if __name__ == "__main__":
    main()
