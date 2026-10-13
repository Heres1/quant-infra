"""质量门注入测试（TEST_PLAN §8 M1：8 类坏数据全部拦截 + 方案 C 复权感知规则）。"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from data_platform.quality.gates import gate_daily


def good_df(rows: int = 5, adjust: str = "none") -> pd.DataFrame:
    base = dt.date(2026, 9, 1)
    dates = [base + dt.timedelta(days=i) for i in range(rows)]
    return pd.DataFrame(
        {
            "symbol": ["600519"] * rows,
            "trade_date": dates,
            "open": [100.0] * rows,
            "high": [101.0] * rows,
            "low": [99.0] * rows,
            "close": [100.5] * rows,
            "volume": [1_000_000] * rows,
            "amount": [100_500_000.0] * rows,
            "adjust": [adjust] * rows,
        }
    )


def test_good_data_passes() -> None:
    assert gate_daily(good_df()).ok


def test_both_adjusts_pass() -> None:
    df = pd.concat([good_df(adjust="none"), good_df(adjust="qfq")], ignore_index=True)
    assert gate_daily(df).ok


def test_inject_missing_column() -> None:
    df = good_df().drop(columns=["amount"])
    r = gate_daily(df)
    assert not r.ok and r.violations[0].reason == "schema_missing"


def test_inject_null() -> None:
    df = good_df()
    df.loc[2, "close"] = None
    r = gate_daily(df)
    assert not r.ok and r.violations[0].reason == "null_values"


def test_inject_ohlc_violation() -> None:
    df = good_df()
    df.loc[1, "high"] = 90.0  # high < open/close 且 < low
    r = gate_daily(df)
    assert not r.ok
    assert any("ohlc" in v.reason for v in r.violations)


def test_inject_negative_volume() -> None:
    df = good_df()
    df.loc[0, "volume"] = -100
    r = gate_daily(df)
    assert not r.ok and any(v.reason.endswith("negative_volume") for v in r.violations)


def test_inject_duplicate_dates() -> None:
    df = good_df()
    df.loc[2, "trade_date"] = df.loc[1, "trade_date"]
    r = gate_daily(df)
    assert not r.ok and any(v.reason.endswith("duplicate_dates") for v in r.violations)


def test_inject_unordered_dates() -> None:
    df = good_df()
    df = df.iloc[::-1].reset_index(drop=True)
    r = gate_daily(df)
    assert not r.ok and any(v.reason.endswith("dates_unordered") for v in r.violations)


def test_inject_future_dates() -> None:
    df = good_df()
    df["trade_date"] = [dt.date.today() + dt.timedelta(days=30 + i) for i in range(len(df))]
    r = gate_daily(df)
    assert not r.ok and any(v.reason.endswith("future_dates") for v in r.violations)


def test_inject_suspicious_jump() -> None:
    # 跳变检查只作用于 qfq（none 豁免，见 test_none_adjust_exempt_from_jump）
    df = good_df(adjust="qfq")
    df.loc[3, "close"] = df.loc[2, "close"] * 1.5  # +50%，超北交所 ±30% 上限
    r = gate_daily(df)
    assert not r.ok and any(v.reason.endswith("suspicious_jump") for v in r.violations)


def test_jump_within_limit_passes() -> None:
    df = good_df()
    df.loc[3, "close"] = df.loc[2, "close"] * 1.099  # +9.9%，正常
    df.loc[3, "high"] = df.loc[3, "close"] * 1.001  # 保持 OHLC 关系成立
    assert gate_daily(df).ok


# ---- 方案 C：复权感知规则 ----


def test_qfq_negative_price_allowed() -> None:
    """高分红股前复权负价是数学产物，qfq 必须放行（600188 案例：整段为负的历史区间）。"""
    df = good_df(adjust="qfq")
    df[["open", "high", "low", "close"]] = [
        [-0.92, -0.33, -0.95, -0.33],
        [-0.90, -0.32, -0.94, -0.32],
        [-0.91, -0.31, -0.93, -0.31],
        [-0.89, -0.30, -0.92, -0.30],
        [-0.88, -0.29, -0.91, -0.29],
    ]
    assert gate_daily(df).ok


def test_none_negative_price_rejected() -> None:
    """原始价（none）出现非正数必拒。"""
    df = good_df(adjust="none")
    df.loc[0, ["open", "high", "low", "close"]] = [-0.92, -0.33, -0.95, -0.33]
    r = gate_daily(df)
    assert not r.ok and any("non_positive_price" in v.reason for v in r.violations)


def test_none_adjust_exempt_from_jump() -> None:
    """none 数据的除权/高送转跳空是真实数据，不做跳变检查。"""
    df = good_df(adjust="none")
    df.loc[3, "close"] = df.loc[2, "close"] * 0.5  # 10送10 除权，-50%
    df.loc[3, ["open", "high", "low"]] = df.loc[3, ["open", "high", "low"]] * 0.5
    assert gate_daily(df).ok


def test_qfq_jump_still_checked() -> None:
    """qfq 已消除除权跳空，超限跳变仍要拦。"""
    df = good_df(adjust="qfq")
    df.loc[3, "close"] = df.loc[2, "close"] * 1.5
    df.loc[3, "high"] = df.loc[3, "close"] * 1.001
    r = gate_daily(df)
    assert not r.ok and any(v.reason.endswith("suspicious_jump") for v in r.violations)


@pytest.mark.parametrize("price_col", ["open", "high", "low", "close"])
def test_inject_non_positive_price(price_col: str) -> None:
    df = good_df()
    df.loc[0, price_col] = 0.0
    r = gate_daily(df)
    assert not r.ok and any(v.reason.endswith("non_positive_price") for v in r.violations)
