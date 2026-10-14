"""akshare 数据源：全市场名单与日线历史（字段规范化 + 单位转换）。"""

from __future__ import annotations

import akshare as ak
import pandas as pd

# stock_zh_a_hist 中文列 → 标准列（成交量单位为"手"，统一转"股"×100）
_DAILY_COL_MAP = {
    "日期": "trade_date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume_hand",
    "成交额": "amount",
}


def infer_board(symbol: str) -> str:
    """按代码前缀推断板块（Instrument 主档的初始来源）。"""
    if symbol.startswith(("600", "601", "603", "605")):
        return "MainSH"
    if symbol.startswith(("000", "001", "002", "003")):
        return "MainSZ"
    if symbol.startswith(("300", "301", "302")):
        return "ChiNext"
    if symbol.startswith(("688", "689")):
        return "Star"
    if symbol.startswith(("43", "83", "87", "88", "92")):
        return "Bse"
    return "Unknown"


def fetch_stock_list() -> pd.DataFrame:
    """全市场 A 股名单：symbol / name / board。"""
    df: pd.DataFrame = ak.stock_info_a_code_name()
    out = df.rename(columns={"code": "symbol", "name": "name"})
    out["board"] = out["symbol"].map(infer_board)
    return out[["symbol", "name", "board"]]


# 内部规范标签 → akshare 参数（akshare 不复权是空字符串，"none" 会 KeyError）
_AK_ADJUST = {"none": "", "qfq": "qfq", "hfq": "hfq"}


def fetch_delisted() -> pd.DataFrame:
    """沪深退市股名单（点时股票池元数据；价格数据东财不提供，backlog: baostock）。

    按交易所独立容错：单个交易所接口超时只减少覆盖，不整体失败。
    """
    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    try:
        sh: pd.DataFrame = ak.stock_info_sh_delist()
        frames.append(
            sh.rename(columns={"公司代码": "symbol", "公司简称": "name"})[["symbol", "name"]]
        )
    except Exception as exc:  # noqa: BLE001 —— 单交易所失败容忍
        errors.append(f"sh:{exc}")
    try:
        sz: pd.DataFrame = ak.stock_info_sz_delist()
        frames.append(
            sz.rename(columns={"证券代码": "symbol", "证券简称": "name"})[["symbol", "name"]]
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"sz:{exc}")
    if not frames:
        raise RuntimeError(f"delist list unavailable: {errors}")
    df = pd.concat(frames, ignore_index=True)
    df["symbol"] = df["symbol"].astype(str).str.zfill(6)
    df["board"] = df["symbol"].map(infer_board)
    df["status"] = "Delisted"
    return df


def fetch_daily(symbol: str, start: str, end: str, adjust: str = "qfq") -> pd.DataFrame:
    """单只股票日线历史，规范化为存储 schema（手→股，日期→date）。

    adjust 使用内部标签：none（不复权）/ qfq（前复权）/ hfq（后复权）。

    Raises:
        ValueError: 返回为空或缺少必需列时（调用方计入隔离区）。
    """
    raw: pd.DataFrame = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start,
        end_date=end,
        adjust=_AK_ADJUST[adjust],
    )
    if raw is None or raw.empty:
        raise ValueError(f"empty daily history for {symbol}")
    missing = set(_DAILY_COL_MAP) - set(raw.columns)
    if missing:
        raise ValueError(f"unexpected columns for {symbol}: missing {missing}")

    df = raw.rename(columns=_DAILY_COL_MAP)
    df["volume"] = (df.pop("volume_hand") * 100).astype("int64")
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["symbol"] = symbol
    df["adjust"] = adjust
    df["source"] = "akshare-em"
    cols = [
        "symbol", "trade_date", "open", "high", "low", "close",
        "volume", "amount", "adjust", "source",
    ]
    return df[cols]
