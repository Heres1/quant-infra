"""数据质量门（INV-D1：未过门数据只进隔离区）。

M0/M1 范围：日线批量导入的批量级校验；快照流与涨跌停界校验在 D4（需 Instrument 主档）。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from data_platform.config import MAX_DAILY_PCT


@dataclass
class GateViolation:
    reason: str
    detail: str


@dataclass
class GateResult:
    ok: bool
    violations: list[GateViolation]

    @property
    def reason_summary(self) -> str:
        return ";".join(v.reason for v in self.violations)


def gate_daily(df: pd.DataFrame, today: dt.date | None = None) -> GateResult:
    """日线批量质量门：schema/空值/OHLC 关系/正数/重复/时序/异常跳变/未来日期。"""
    v: list[GateViolation] = []
    today = today or dt.date.today()

    required = {"symbol", "trade_date", "open", "high", "low", "close", "volume", "amount"}
    missing = required - set(df.columns)
    if missing:
        return GateResult(False, [GateViolation("schema_missing", f"missing={sorted(missing)}")])

    if df.empty:
        v.append(GateViolation("empty", "no rows"))

    null_counts = df[list(required)].isna().sum()
    if (null_counts > 0).any():
        v.append(GateViolation("null_values", null_counts[null_counts > 0].to_dict().__str__()))

    if (df["low"] > df["high"]).any():
        v.append(GateViolation("ohlc_low_gt_high", "low > high present"))
    if ((df["open"] > df["high"]) | (df["open"] < df["low"])).any():
        v.append(GateViolation("ohlc_open_out_of_range", "open outside [low, high]"))
    if ((df["close"] > df["high"]) | (df["close"] < df["low"])).any():
        v.append(GateViolation("ohlc_close_out_of_range", "close outside [low, high]"))

    if ((df[["open", "high", "low", "close"]] <= 0).any().any()):
        v.append(GateViolation("non_positive_price", "price <= 0 present"))
    if (df["volume"] < 0).any():
        v.append(GateViolation("negative_volume", "volume < 0 present"))

    if df["trade_date"].duplicated().any():
        dup = df.loc[df["trade_date"].duplicated(), "trade_date"].iloc[0]
        v.append(GateViolation("duplicate_dates", f"first_dup={dup}"))
    if not df["trade_date"].is_monotonic_increasing:
        v.append(GateViolation("dates_unordered", "trade_date not ascending"))

    if (df["trade_date"] > today).any():
        v.append(GateViolation("future_dates", f"max={df['trade_date'].max()}"))

    if len(df) > 1:
        pct = df["close"].pct_change().abs().max()
        if pct and pct > MAX_DAILY_PCT:
            v.append(GateViolation("suspicious_jump", f"max_abs_pct_change={pct:.4f}"))

    return GateResult(not v, v)
