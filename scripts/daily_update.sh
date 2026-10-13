#!/usr/bin/env bash
# 每日增量更新（欠账#4 / M1-D6 的增量部分）：
#   交易日收盘后拉取近 7 日全市场日线（ReplacingMergeTree 幂等覆盖）。
# 由 launchd 在周一至周五 17:30 调用（plist: com.quantinfra.dailyupdate）。
set -euo pipefail

export PATH="/opt/homebrew/bin:$PATH"
cd "$(dirname "$0")/../py"

# 非交易日直接跳过（v1 简化：周末判断；法定节假日由 akshare 日历在导入侧兜底——
# 非交易日拉取为空会进隔离区，属已知噪声，D6 用日历门控后移除）
DOW=$(date +%u)   # 1=周一 … 7=周日
if [ "$DOW" -ge 6 ]; then
    echo " weekend, skip"
    exit 0
fi

START=$(date -v-7d +%Y%m%d)
END=$(date +%Y%m%d)

echo "[$(date '+%F %T')] daily incremental update: $START -> $END"
uv run python -m data_platform.ingest_daily --start "$START" --end "$END" --workers 4 --no-resume
echo "[$(date '+%F %T')] done"
