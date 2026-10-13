"""隔离区重放（欠账#2：整票隔离 → 复权感知规则下的按票重判）。

实现说明（2026-10-13 修订）：曾尝试"重放隔离载荷"，但 v1 导入器把 payload 截断在
60KB，JSON 全部非法——载荷不可靠，源才可靠。故重放 = 从数据源重新拉取该票全部
历史，用当前质量门重判：
- 通过 → 入主库（ReplacingMergeTree 幂等），并从隔离区清除该票
- 仍不通过 → 以新原因重新入隔离区
可重复执行：入库幂等，重放状态不落盘。
"""

from __future__ import annotations

import datetime as dt
import logging
import time

from data_platform import config
from data_platform.ingest_daily import fetch_history
from data_platform.quality.gates import gate_daily
from data_platform.store import ch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("replay_quarantine")


def main() -> None:
    client = ch.get_client()
    symbols = [r[0] for r in client.query(
        "SELECT DISTINCT symbol FROM qinfra.quarantine_bar_1d"
    ).result_rows]
    log.info("replaying %d quarantined symbols (refetch from source)", len(symbols))

    stats = {"ok": 0, "still_quarantined": 0}
    recovered: list[str] = []
    end = time.strftime("%Y%m%d")
    for symbol in symbols:
        try:
            df = fetch_history(symbol, config.HISTORY_START, end)
        except Exception as exc:  # noqa: BLE001 —— 源不可用则保留原隔离记录，下轮重试
            log.warning("refetch failed for %s: %s", symbol, exc)
            continue

        result = gate_daily(df)
        if result.ok:
            ch.insert_daily(client, df)
            recovered.append(symbol)
            stats["ok"] += 1
        else:
            ch.insert_quarantine(
                client,
                symbol,
                result.reason_summary,
                str(result.violations),
                df.to_json(orient="records"),
            )
            stats["still_quarantined"] += 1
        time.sleep(0.15)

    if recovered:
        symbol_list = ",".join(f"'{s}'" for s in recovered)
        client.command(
            f"ALTER TABLE qinfra.quarantine_bar_1d DELETE WHERE symbol IN ({symbol_list})"
        )
    log.info(
        "done. stats=%s bars_total=%d as_of=%s",
        stats,
        ch.count_bars(client),
        dt.date.today(),
    )


if __name__ == "__main__":
    main()
