#!/usr/bin/env bash
# EN-05 覆盖率门槛：核心 crate 行覆盖率 ≥90%，全局 ≥70%。
# 无实体代码的 crate（可统计行为 0）自动跳过——空壳阶段不阻塞，写码即生效。
# 输入：cargo llvm-cov --workspace --json --summary-only 的输出文件。
set -euo pipefail
cd "$(dirname "$0")/.."

file="${1:?用法: check_coverage.sh <llvm-cov json 输出文件>}"
command -v jq >/dev/null 2>&1 || { echo "❌ 本脚本需要 jq"; exit 2; }

# 结构防御：llvm-cov 的 JSON 格式若在未来版本变更，这里显式失败，绝不静默放过。
if ! jq -e '.data[0].files' "$file" >/dev/null 2>&1; then
  echo "❌ cov json 结构不符合预期（llvm-cov 版本变更？请同步更新本脚本）"
  exit 2
fi

CORE_CRATES="crates/core-types crates/time-core"
CORE_MIN=90
TOTAL_MIN=70
fail=0

# 某前缀下的聚合行覆盖率（covered*100/count）；无数据或 0 行时输出空 → 调用方跳过
# 注意用 contains 而非 startswith：llvm-cov 在部分环境输出绝对路径
crate_pct() {
  jq -r --arg p "$1" \
    '[.data[0].files[] | select(.filename | contains($p)) | .summary.lines]
     | if length == 0 or (map(.count) | add) == 0 then empty
       else (map(.covered) | add) * 100 / (map(.count) | add) end' "$file"
}

for c in $CORE_CRATES; do
  pct=$(crate_pct "$c")
  if [ -z "$pct" ]; then
    echo "⏭  $c 无可统计代码，跳过"
    continue
  fi
  if awk -v a="$pct" -v m="$CORE_MIN" 'BEGIN{exit !(a>=m)}'; then
    echo "✅ $c 行覆盖率 ${pct}%（≥${CORE_MIN}）"
  else
    echo "❌ $c 行覆盖率 ${pct}%（要求 ≥${CORE_MIN}，EN-05）"
    fail=1
  fi
done

total=$(jq -r '.data[0].totals.lines.percent' "$file")
if awk -v a="$total" -v m="$TOTAL_MIN" 'BEGIN{exit !(a>=m)}'; then
  echo "✅ 全局行覆盖率 ${total}%（≥${TOTAL_MIN}）"
else
  echo "❌ 全局行覆盖率 ${total}%（要求 ≥${TOTAL_MIN}，EN-05）"
  fail=1
fi

if [ "$fail" -eq 1 ]; then
  echo "覆盖率门槛未通过"
  exit 1
fi
echo "✅ 覆盖率门槛通过"
