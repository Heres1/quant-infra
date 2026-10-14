"""沪深300 五分钟线一次性导入：成分 → 逐票拉取(重试) → gate_minute → 入库/隔离。

用法：
  uv run python -m data_platform.ingest_minute_csi300 --limit 10   # 验证
  nohup uv run python -m data_platform.ingest_minute_csi300 &      # 全量（300 只）
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from data_platform.quality.gates import gate_minute
from data_platform.sources.akshare_minute import fetch_csi300_constituents, fetch_minute
from data_platform.store import ch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingest_minute")

STATE_PATH = Path.home() / ".quant-infra" / "state" / "ingest_minute.json"


def load_state() -> set[str]:
    if STATE_PATH.exists():
        return set(json.loads(STATE_PATH.read_text()).get("done", []))
    return set()


def save_state(done: set[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"done": sorted(done)}))


def fetch_with_retry(symbol: str, start: str, end: str, attempts: int = 3) -> pd.DataFrame:
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return fetch_minute(symbol, start, end)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(1 + 2 * i)
    raise RuntimeError(f"fetch failed after {attempts} attempts: {last_exc}") from last_exc


def process_one(symbol: str, start: str, end: str) -> tuple[str, str]:
    client = ch.get_client()
    try:
        df = fetch_with_retry(symbol, start, end)
    except Exception as exc:  # noqa: BLE001
        ch.insert_quarantine_minute(client, symbol, "fetch_error", str(exc), "")
        return symbol, "quarantine:fetch_error"

    result = gate_minute(df)
    if not result.ok:
        ch.insert_quarantine_minute(
            client,
            symbol,
            result.reason_summary,
            str(result.violations),
            df.to_json(orient="records", date_format="iso"),
        )
        return symbol, f"quarantine:{result.reason_summary}"

    ch.insert_minute(client, df)
    return symbol, "ok"


def main() -> None:
    parser = argparse.ArgumentParser()
    # 东财 5 分钟约 7 周上限
    parser.add_argument("--days", type=int, default=50, help="回溯自然日数")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    import datetime as dt

    end = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    start = (dt.datetime.now() - dt.timedelta(days=args.days)).strftime("%Y-%m-%d 09:30:00")

    client = ch.get_client()
    symbols = fetch_csi300_constituents()
    log.info("csi300 constituents: %d", len(symbols))

    done = set() if args.no_resume else load_state()
    todo = [s for s in symbols if s not in done]
    if args.limit:
        todo = todo[: args.limit]
    log.info("to import: %d", len(todo))

    stats = {"ok": 0, "quarantine": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process_one, s, start, end): s for s in todo}
        for n, fut in enumerate(as_completed(futures), 1):
            symbol, status = fut.result()
            done.add(symbol)
            stats["ok" if status == "ok" else "quarantine"] += 1
            if n % 50 == 0:
                save_state(done)
                log.info("progress %d/%d stats=%s", n, len(todo), stats)

    save_state(done)
    bars = client.query("SELECT count() FROM qinfra.bar_5m").result_rows[0][0]
    log.info("done. stats=%s bars_5m_total=%d", stats, bars)


if __name__ == "__main__":
    main()
