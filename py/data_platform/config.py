"""集中配置：ClickHouse 连接、日期范围、源标记。"""

from __future__ import annotations

CH_HOST = "127.0.0.1"
CH_PORT = 8123
CH_USERNAME = "default"
CH_PASSWORD = ""
CH_DATABASE = "qinfra"

SOURCE_AKSHARE_EM = "akshare-em"
SOURCE_QMT = "qmt"
SOURCE_TENCENT = "tencent"

# 历史导入默认区间（一次性导入，起点覆盖 quant-infra 设计所需的回测深度）
HISTORY_START = "20150101"

# 日线质量门：单日涨跌幅超过该值视为可疑（北交所 ±30% 为最宽）
MAX_DAILY_PCT = 0.31
