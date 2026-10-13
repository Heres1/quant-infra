"""ClickHouse 存取：批量插入、隔离区、主档。"""

from __future__ import annotations

import datetime as dt
import threading
from zoneinfo import ZoneInfo

import clickhouse_connect
import pandas as pd

from data_platform import config

_TZ = ZoneInfo("Asia/Shanghai")

# clickhouse-connect 客户端非线程安全：每线程一个实例
_local = threading.local()


def get_client() -> clickhouse_connect.driver.Client:
    client: clickhouse_connect.driver.Client | None = getattr(_local, "client", None)
    if client is None:
        client = clickhouse_connect.get_client(
            host=config.CH_HOST,
            port=config.CH_PORT,
            username=config.CH_USERNAME,
            password=config.CH_PASSWORD,
            database=config.CH_DATABASE,
        )
        _local.client = client
    return client


def _now() -> dt.datetime:
    return dt.datetime.now(_TZ)


def insert_daily(client: clickhouse_connect.driver.Client, df: pd.DataFrame) -> None:
    out = df.copy()
    out["ingested_at"] = _now()
    out["volume"] = out["volume"].astype("int64")
    client.insert_df("qinfra.bar_1d", out)


def insert_quarantine(
    client: clickhouse_connect.driver.Client,
    symbol: str,
    reason: str,
    detail: str,
    payload: str,
) -> None:
    client.insert(
        "qinfra.quarantine_bar_1d",
        [[symbol, reason, detail[:2000], payload[:60000], _now()]],
        column_names=["symbol", "reason", "detail", "payload", "ingested_at"],
    )


def upsert_instruments(client: clickhouse_connect.driver.Client, df: pd.DataFrame) -> None:
    out = df.copy()
    out["updated_at"] = _now()
    client.insert_df("qinfra.instrument", out)


def count_bars(client: clickhouse_connect.driver.Client) -> int:
    return int(client.query("SELECT count() FROM qinfra.bar_1d").result_rows[0][0])
