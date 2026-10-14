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
    # payload 上限 2MB（此前 60KB 截断曾把 JSON 切成非法串，导致隔离区不可重放）
    client.insert(
        "qinfra.quarantine_bar_1d",
        [[symbol, reason, detail[:2000], payload[:2_000_000], _now()]],
        column_names=["symbol", "reason", "detail", "payload", "ingested_at"],
    )


def insert_minute(client: clickhouse_connect.driver.Client, df: pd.DataFrame) -> None:
    out = df.copy()
    out["ingested_at"] = _now()
    out["volume"] = out["volume"].astype("int64")
    # clickhouse-connect 会把 naive 时间戳当 UTC 转换（实测 +8h 偏移），必须显式本地化
    out["ts"] = out["ts"].dt.tz_localize("Asia/Shanghai")
    client.insert_df("qinfra.bar_5m", out)


def insert_quarantine_minute(
    client: clickhouse_connect.driver.Client,
    symbol: str,
    reason: str,
    detail: str,
    payload: str,
) -> None:
    client.insert(
        "qinfra.quarantine_bar_5m",
        [[symbol, reason, detail[:2000], payload[:2_000_000], _now()]],
        column_names=["symbol", "reason", "detail", "payload", "ingested_at"],
    )


def insert_snapshot(client: clickhouse_connect.driver.Client, df: pd.DataFrame) -> None:
    out = df.copy()
    out["ingested_at"] = _now()
    out["volume"] = out["volume"].astype("int64")
    # naive 时间戳会被 clickhouse-connect 当 UTC（+8h 坑，bar_5m 实测），统一显式本地化
    for col in ("exchange_ts", "capture_ts"):
        out[col] = out[col].dt.tz_localize("Asia/Shanghai")
    client.insert_df("qinfra.snapshot_l1", out)


def upsert_instruments(
    client: clickhouse_connect.driver.Client, df: pd.DataFrame, status: str = "Listed"
) -> None:
    out = df.copy()
    out["updated_at"] = _now()
    if "status" not in out.columns:
        out["status"] = status
    client.insert_df("qinfra.instrument", out)


def count_bars(client: clickhouse_connect.driver.Client) -> int:
    return int(client.query("SELECT count() FROM qinfra.bar_1d").result_rows[0][0])
