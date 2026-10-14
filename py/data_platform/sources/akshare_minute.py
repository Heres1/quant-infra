"""akshare 分钟线源：沪深300 成分与 5 分钟历史（字段规范化 + 单位转换）。

数据边界（2026-10-13 实测）：东财 5 分钟历史仅回溯约 7 周；深度历史走 baostock（backlog）。
bar 时间戳口径：东财给的是 bar 结束时刻（09:35 = 09:30-09:35）。
"""

from __future__ import annotations

import akshare as ak
import pandas as pd

_MIN_COL_MAP = {
    "时间": "ts",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume_hand",
    "成交额": "amount",
}


def fetch_csi300_constituents() -> list[str]:
    """沪深300 成分代码列表（中证指数官网口径）。"""
    df = ak.index_stock_cons_csindex(symbol="000300")
    codes: list[str] = df["成分券代码"].astype(str).tolist()
    return codes


def fetch_minute(
    symbol: str, start: str, end: str, adjust: str = "qfq", period: str = "5"
) -> pd.DataFrame:
    """单只股票 5 分钟历史，规范化为存储 schema（手→股，时间→datetime）。

    start/end 格式："2026-08-01 09:30:00"。

    Raises:
        ValueError: 返回为空或缺少必需列时（调用方计入隔离区）。
    """
    raw: pd.DataFrame = ak.stock_zh_a_hist_min_em(
        symbol=symbol,
        period=period,
        start_date=start,
        end_date=end,
        adjust=adjust,
    )
    if raw is None or raw.empty:
        raise ValueError(f"empty minute history for {symbol}")
    missing = set(_MIN_COL_MAP) - set(raw.columns)
    if missing:
        raise ValueError(f"unexpected minute columns for {symbol}: missing {missing}")

    df = raw.rename(columns=_MIN_COL_MAP)
    df["volume"] = (df.pop("volume_hand") * 100).astype("int64")
    df["ts"] = pd.to_datetime(df["ts"])
    df["symbol"] = symbol
    df["adjust"] = adjust
    df["source"] = "akshare-em"
    cols = ["symbol", "ts", "open", "high", "low", "close", "volume", "amount", "adjust", "source"]
    return df[cols]
