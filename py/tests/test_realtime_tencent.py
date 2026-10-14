"""腾讯快照解析器测试（字段映射按 2026-10-14 茅台实测校准）。"""

from __future__ import annotations

import datetime as dt

from data_platform.sources.realtime_tencent import TencentRealtimeSource, to_tencent_code

RAW_LINE = (
    'v_sh600519="1~贵州茅台~600519~1274.89~1288.00~1287.00~26573~12230~14343'
    '~1274.66~1~1274.43~2~1274.00~3~1273.98~1~1273.90~1'
    '~1274.89~1~1274.95~1~1274.99~6~1275.00~59~1275.03~1'
    '~~20261013161452~-13.11~-1.02~1288.48~1268.11~1274.89/26573/3393315572~26573~339332~0.21~19.57";'
)


def test_to_tencent_code() -> None:
    assert to_tencent_code("600519") == "sh600519"
    assert to_tencent_code("000001") == "sz000001"
    assert to_tencent_code("300750") == "sz300750"
    assert to_tencent_code("688981") == "sh688981"
    assert to_tencent_code("920000") is None  # 北交所 v1 不支持
    assert to_tencent_code("430047") is None


def test_parse_field_mapping() -> None:
    src = TencentRealtimeSource()
    df = src._parse(RAW_LINE)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["symbol"] == "600519"
    assert row["last"] == 1274.89
    assert row["pre_close"] == 1288.00
    assert row["open"] == 1287.00
    assert row["high"] == 1288.48
    assert row["low"] == 1268.11
    assert row["volume"] == 2_657_300  # 手→股
    assert row["amount"] == 3_393_320_000.0  # 万→元
    assert row["bid1"] == 1274.66 and row["bid1_vol"] == 100
    assert row["ask1"] == 1274.89 and row["ask1_vol"] == 100
    assert row["bid5"] == 1273.90 and row["bid5_vol"] == 100
    assert row["ask5"] == 1275.03 and row["ask5_vol"] == 100
    assert row["exchange_ts"] == dt.datetime(2026, 10, 13, 16, 14, 52)
    assert row["source"] == "tencent"


def test_parse_skips_malformed_lines() -> None:
    src = TencentRealtimeSource()
    text = "v_err=\"1~2\";\n" + RAW_LINE + "\nv_empty=\"\";"
    df = src._parse(text)
    assert len(df) == 1  # 两行异常被跳过
