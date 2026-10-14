"""实时快照采集守护进程（M1-D3 兜底采集器）。

用法（示例）：
  uv run python -m data_platform.collect_realtime --universe csi300 --interval 3
  uv run python -m data_platform.collect_realtime --universe csi300 --duration 900  # 限时测试

会话门控（v1 简化）：仅工作日 09:15-15:05 采集（集合竞价+连续竞价），
盘后固定价格交易与节假日日历门控归 D6。
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from clickhouse_connect.driver import Client

from data_platform.sources.akshare_minute import fetch_csi300_constituents
from data_platform.sources.base import RealtimeSource
from data_platform.sources.realtime_tencent import TencentRealtimeSource, to_tencent_code
from data_platform.store import ch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("collect_realtime")
logging.getLogger("httpx").setLevel(logging.WARNING)  # 每个请求一行 INFO，太吵


def in_session(now: dt.datetime) -> bool:
    if now.weekday() >= 5:
        return False
    t = now.time()
    return dt.time(9, 15) <= t <= dt.time(15, 5)


def load_universe(kind: str, client: Client) -> list[str]:
    if kind == "csi300":
        return fetch_csi300_constituents()
    rows = client.query(
        "SELECT symbol FROM qinfra.instrument WHERE status='Listed' FINAL"
    ).result_rows
    return [r[0] for r in rows if to_tencent_code(r[0])]


def collect_round(
    source: RealtimeSource, symbols: list[str], workers: int, batch: int
) -> tuple[pd.DataFrame | None, int]:
    """并发分批拉取一轮快照；返回 (拼接结果, 失败批数)。"""
    batches = [symbols[i : i + batch] for i in range(0, len(symbols), batch)]
    frames: list[pd.DataFrame] = []
    failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(lambda b: _safe_fetch(source, b), batches):
            if result is None:
                failed += 1
            else:
                frames.append(result)
    if not frames:
        return None, failed
    df = pd.concat(frames, ignore_index=True)
    df["capture_ts"] = dt.datetime.now()
    return df, failed


def _safe_fetch(source: RealtimeSource, batch: list[str]) -> pd.DataFrame | None:
    try:
        return source.fetch_quotes(batch)
    except Exception as exc:  # noqa: BLE001 —— 单批失败容忍，轮询下一轮
        log.warning("batch fetch failed (%d symbols): %s", len(batch), exc)
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", choices=["csi300", "listed"], default="csi300")
    parser.add_argument("--interval", type=float, default=3.0, help="轮询间隔秒")
    parser.add_argument("--duration", type=float, default=0, help="运行秒数（0=持续运行）")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--batch", type=int, default=60)
    args = parser.parse_args()

    client = ch.get_client()
    symbols = load_universe(args.universe, client)
    source: RealtimeSource = TencentRealtimeSource(batch_size=args.batch)
    log.info("universe=%s symbols=%d interval=%.1fs", args.universe, len(symbols), args.interval)

    deadline = time.monotonic() + args.duration if args.duration else None
    rounds = 0
    while deadline is None or time.monotonic() < deadline:
        now = dt.datetime.now()
        if not in_session(now):
            log.info("outside trading session, sleeping 60s")
            time.sleep(60)
            continue
        started = time.monotonic()
        df, failed = collect_round(source, symbols, args.workers, args.batch)
        rounds += 1
        if df is not None and not df.empty:
            ch.insert_snapshot(client, df)
            log.info(
                "round %d: rows=%d failed_batches=%d exchange_ts=[%s .. %s] took=%.1fs",
                rounds, len(df), failed, df["exchange_ts"].min(), df["exchange_ts"].max(),
                time.monotonic() - started,
            )
        else:
            log.warning("round %d: no data (failed_batches=%d)", rounds, failed)
        elapsed = time.monotonic() - started
        time.sleep(max(0.0, args.interval - elapsed))


if __name__ == "__main__":
    main()
