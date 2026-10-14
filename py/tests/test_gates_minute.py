"""分钟线质量门测试（gate_minute：轻量规则，无跳变检查）。"""

from __future__ import annotations

import pandas as pd
import pytest

from data_platform.quality.gates import gate_minute


def good_minute(rows: int = 6) -> pd.DataFrame:
    base = pd.Timestamp("2026-10-12 09:35:00")
    return pd.DataFrame(
        {
            "symbol": ["600519"] * rows,
            "ts": [base + pd.Timedelta(minutes=5 * i) for i in range(rows)],
            "open": [100.0] * rows,
            "high": [100.8] * rows,
            "low": [99.5] * rows,
            "close": [100.2] * rows,
            "volume": [50_000] * rows,
            "amount": [5_010_000.0] * rows,
        }
    )


def test_good_minute_passes() -> None:
    assert gate_minute(good_minute()).ok


def test_lunch_gap_jump_passes() -> None:
    """午休跳空（11:30 → 13:00）与隔夜跳空不做跳变过滤——设计行为锁定。"""
    df = good_minute()
    df.loc[3, "close"] = df.loc[2, "close"] * 1.3
    df.loc[3, ["open", "high", "low"]] = df.loc[3, ["open", "high", "low"]] * 1.3
    assert gate_minute(df).ok


def test_inject_ohlc_violation() -> None:
    df = good_minute()
    df.loc[1, "low"] = 101.0
    r = gate_minute(df)
    assert not r.ok and any("ohlc" in v.reason for v in r.violations)


def test_inject_non_positive_price() -> None:
    df = good_minute()
    df.loc[2, "close"] = 0.0
    r = gate_minute(df)
    assert not r.ok and any(v.reason == "non_positive_price" for v in r.violations)


def test_inject_duplicate_and_unordered_ts() -> None:
    df = good_minute()
    df.loc[2, "ts"] = df.loc[1, "ts"]
    r = gate_minute(df)
    assert not r.ok and any(v.reason == "duplicate_ts" for v in r.violations)

    df2 = good_minute().iloc[::-1].reset_index(drop=True)
    r2 = gate_minute(df2)
    assert not r2.ok and any(v.reason == "ts_unordered" for v in r2.violations)


def test_inject_future_ts() -> None:
    df = good_minute()
    df["ts"] = [pd.Timestamp.now() + pd.Timedelta(days=3 + i) for i in range(len(df))]
    r = gate_minute(df)
    assert not r.ok and any(v.reason == "future_ts" for v in r.violations)


def test_inject_negative_volume() -> None:
    df = good_minute()
    df.loc[0, "volume"] = -1
    r = gate_minute(df)
    assert not r.ok and any(v.reason == "negative_volume" for v in r.violations)


@pytest.mark.parametrize("col", ["open", "high", "low", "close", "volume", "amount"])
def test_inject_null(col: str) -> None:
    df = good_minute()
    df.loc[0, col] = None
    r = gate_minute(df)
    assert not r.ok and any(v.reason == "null_values" for v in r.violations)
