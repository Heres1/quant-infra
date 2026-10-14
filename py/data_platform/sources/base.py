"""实时行情源抽象（M1 Python 侧；Rust 侧 gateway trait 在 M2 对应实现）。

可插拔契约：实现 fetch_quotes(symbols) -> DataFrame（snapshot_l1 schema，
不含 ingested_at），采集守护进程只依赖此协议——qmt/腾讯/东财可互换。
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd

SNAPSHOT_COLUMNS = [
    "symbol", "exchange_ts", "last", "open", "high", "low", "pre_close",
    "volume", "amount",
    "bid1", "bid1_vol", "ask1", "ask1_vol",
    "bid2", "bid2_vol", "ask2", "ask2_vol",
    "bid3", "bid3_vol", "ask3", "ask3_vol",
    "bid4", "bid4_vol", "ask4", "ask4_vol",
    "bid5", "bid5_vol", "ask5", "ask5_vol",
    "source",
]


class RealtimeSource(Protocol):
    """实时快照源协议。exchange_ts 为源给出的行情时间（tz-naive，入库层统一本地化）。"""

    source_name: str

    def fetch_quotes(self, symbols: list[str]) -> pd.DataFrame:
        """拉取一批标的的 L1 快照；失败抛异常，由采集器按批容错。"""
        ...
