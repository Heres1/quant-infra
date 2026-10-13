"""质量门注入测试（TEST_PLAN §8 M1：8 类坏数据全部拦截）。"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from data_platform.quality.gates import gate_daily


def good_df(rows: int = 5) -> pd.DataFrame:
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
        }
    )


def test_good_data_passes() -> None:
    assert gate_daily(good_df()).ok


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
    assert any(v.reason.startswith("ohlc") for v in r.violations)


def test_inject_negative_volume() -> None:
    df = good_df()
    df.loc[0, "volume"] = -100
    r = gate_daily(df)
    assert not r.ok and any(v.reason == "negative_volume" for v in r.violations)


def test_inject_duplicate_dates() -> None:
    df = good_df()
    df.loc[2, "trade_date"] = df.loc[1, "trade_date"]
    r = gate_daily(df)
    assert not r.ok and any(v.reason == "duplicate_dates" for v in r.violations)


def test_inject_unordered_dates() -> None:
    df = good_df()
    df = df.iloc[::-1].reset_index(drop=True)
    r = gate_daily(df)
    assert not r.ok and any(v.reason == "dates_unordered" for v in r.violations)


def test_inject_future_dates() -> None:
    df = good_df()
    df["trade_date"] = [dt.date.today() + dt.timedelta(days=30 + i) for i in range(len(df))]
    r = gate_daily(df)
    assert not r.ok and any(v.reason == "future_dates" for v in r.violations)


def test_inject_suspicious_jump() -> None:
    df = good_df()
    df.loc[3, "close"] = df.loc[2, "close"] * 1.5  # +50%，超北交所 ±30% 上限
    r = gate_daily(df)
    assert not r.ok and any(v.reason == "suspicious_jump" for v in r.violations)


def test_jump_within_limit_passes() -> None:
    df = good_df()
    df.loc[3, "close"] = df.loc[2, "close"] * 1.099  # +9.9%，正常
    df.loc[3, "high"] = df.loc[3, "close"] * 1.001  # 保持 OHLC 关系成立
    assert gate_daily(df).ok


@pytest.mark.parametrize("price_col", ["open", "high", "low", "close"])
def test_inject_non_positive_price(price_col: str) -> None:
    df = good_df()
    df.loc[0, price_col] = 0.0
    r = gate_daily(df)
    assert not r.ok and any(v.reason == "non_positive_price" for v in r.violations)
