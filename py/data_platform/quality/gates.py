"""数据质量门（INV-D1：未过门数据只进隔离区）。

复权感知规则（方案 C，2026-10-13 用户确认）：
- 主库同时存 adjust=none（原始价）与 adjust=qfq（前复权）两套；
- none：结构校验全严格，**不做跳变检查**（除权/高送转跳空是真实数据），负价必拒；
- qfq：**豁免负价**（高分红股前复权可为负，数学产物非坏数据），保留跳变检查
  （qfq 已消除除权跳空，超限跳变=可疑）；次新股上市初期无涨跌幅导致的误伤
  隔离待 D4 配合主档上市日期精确豁免。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from data_platform.config import MAX_DAILY_PCT, NEW_LISTING_GRACE_ROWS


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


def _check_block(block: pd.DataFrame, adjust: str, today: dt.date) -> list[GateViolation]:
    v: list[GateViolation] = []
    allow_negative_price = adjust == "qfq"
    check_jump = adjust == "qfq"
    tag = f"[{adjust}]"

    if (block["low"] > block["high"]).any():
        v.append(GateViolation(f"{tag}ohlc_low_gt_high", "low > high present"))
    if ((block["open"] > block["high"]) | (block["open"] < block["low"])).any():
        v.append(GateViolation(f"{tag}ohlc_open_out_of_range", "open outside [low, high]"))
    if ((block["close"] > block["high"]) | (block["close"] < block["low"])).any():
        v.append(GateViolation(f"{tag}ohlc_close_out_of_range", "close outside [low, high]"))

    if not allow_negative_price and (block[["open", "high", "low", "close"]] <= 0).any().any():
        v.append(GateViolation(f"{tag}non_positive_price", "price <= 0 present"))
    if (block["volume"] < 0).any():
        v.append(GateViolation(f"{tag}negative_volume", "volume < 0 present"))

    if block["trade_date"].duplicated().any():
        first_dup = block["trade_date"].duplicated().idxmax()
        v.append(GateViolation(f"{tag}duplicate_dates", f"first_dup={first_dup}"))
    if not block["trade_date"].is_monotonic_increasing:
        v.append(GateViolation(f"{tag}dates_unordered", "trade_date not ascending"))
    if (block["trade_date"] > today).any():
        v.append(GateViolation(f"{tag}future_dates", f"max={block['trade_date'].max()}"))

    if check_jump and len(block) > 1:
        pct = block.sort_values("trade_date")["close"].pct_change().abs()
        # 上市初期无涨跌幅限制：豁免宽限窗口内的真实跳变（D4 换主档上市日期后精确化）
        if len(pct) > NEW_LISTING_GRACE_ROWS:
            pct = pct.iloc[NEW_LISTING_GRACE_ROWS:]
        max_pct = pct.max()
        if max_pct and max_pct > MAX_DAILY_PCT:
            v.append(GateViolation(f"{tag}suspicious_jump", f"max_abs_pct_change={max_pct:.4f}"))

    return v


def gate_minute(df: pd.DataFrame, now: pd.Timestamp | None = None) -> GateResult:
    """分钟线批量质量门（轻量）：schema/空值/OHLC/正数/重复/时序/未来时间。

    与日线的差异：不做跳变检查——午休（11:30→13:00）与隔夜开盘的正常跳空
    在分钟粒度占比过高，逐 bar 跳变过滤留给引擎侧（复权 qfq 已消除除权缺口）。
    """
    v: list[GateViolation] = []
    now = now or pd.Timestamp.now(tz="Asia/Shanghai")

    required = {"symbol", "ts", "open", "high", "low", "close", "volume", "amount"}
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
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        v.append(GateViolation("non_positive_price", "price <= 0 present"))
    if (df["volume"] < 0).any():
        v.append(GateViolation("negative_volume", "volume < 0 present"))
    if df["ts"].duplicated().any():
        v.append(GateViolation("duplicate_ts", "ts duplicated"))
    if not df["ts"].is_monotonic_increasing:
        v.append(GateViolation("ts_unordered", "ts not ascending"))

    ts_naive = df["ts"].dt.tz_localize(None) if df["ts"].dt.tz is not None else df["ts"]
    if (ts_naive > now.to_pydatetime().replace(tzinfo=None)).any():
        v.append(GateViolation("future_ts", f"max={ts_naive.max()}"))

    return GateResult(not v, v)


def gate_daily(df: pd.DataFrame, today: dt.date | None = None) -> GateResult:
    """日线批量质量门：按 adjust 分组执行复权感知规则。"""
    v: list[GateViolation] = []
    today = today or dt.date.today()

    required = {
        "symbol", "trade_date", "open", "high", "low", "close", "volume", "amount", "adjust",
    }
    missing = required - set(df.columns)
    if missing:
        return GateResult(False, [GateViolation("schema_missing", f"missing={sorted(missing)}")])

    if df.empty:
        v.append(GateViolation("empty", "no rows"))

    null_counts = df[list(required)].isna().sum()
    if (null_counts > 0).any():
        v.append(GateViolation("null_values", null_counts[null_counts > 0].to_dict().__str__()))

    if "adjust" in df.columns and not df.empty:
        for adjust_val, block in df.groupby("adjust", sort=True):
            v.extend(_check_block(block.dropna(subset=["trade_date"]), str(adjust_val), today))

    return GateResult(not v, v)
