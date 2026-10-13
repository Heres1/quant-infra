#!/usr/bin/env bash
# 约束扫描器——docs/CONSTRAINTS.md 中 T1 约束的机器强制。
# CI（constraints job）与本地调用同一脚本；本脚本通过是合入的必要条件。
#
# 设计取舍：扫描为"原文匹配"，注释中出现被禁标识符同样失败。
# 理由：可预测性优先于便利性——带注释白名单的扫描器会引入自己的规则漏洞。
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0
err() { echo "❌ $*"; fail=1; }

# --- AC-08：纯净 crate 禁止真实时钟 --------------------------------------
# 纯净 crate = 引擎确定性内核（随里程碑扩充：event-core/oms/accounting/risk）。
# LiveClock 的真实时钟实现放在引擎装配层（engine crate），不得加入本名单。
PURE_CRATES="crates/core-types crates/time-core"
for c in $PURE_CRATES; do
  [ -d "$c/src" ] || continue
  matches=$(grep -RInE 'SystemTime|Instant' "$c/src" --include='*.rs' || true)
  if [ -n "$matches" ]; then
    err "AC-08 违反：$c 出现真实时钟标识符（纯净 crate 只能用 Clock trait）"
    echo "$matches"
  fi
done

# --- AC-01：core-types 禁浮点（连注释都不放过） ---------------------------
matches=$(grep -RInE '\b(f64|f32)\b' crates/core-types/src --include='*.rs' || true)
if [ -n "$matches" ]; then
  err "AC-01 违反：core-types 出现浮点类型（Money/Price/Qty 必须是定点整数，见 ARCHITECTURE §5.5）"
  echo "$matches"
fi

# --- AC-02：舍入只出自 rounding 模块（唯一白名单文件） --------------------
WHITELIST="crates/core-types/src/rounding.rs"
matches=$(grep -RInE '\.round\(|[^_a-zA-Z]round\(' crates --include='*.rs' \
  | grep -v "^${WHITELIST}:" || true)
if [ -n "$matches" ]; then
  err "AC-02 违反：rounding 白名单外出出现舍入调用（舍入规则必须收敛在 core-types::rounding）"
  echo "$matches"
fi

# --- PR-04：#[ignore] 测试必须带 issue 编号且不得为空理由 -----------------
while IFS= read -r line; do
  if ! echo "$line" | grep -qE '#[0-9]+'; then
    err "PR-04 违反：#[ignore] 必须在理由中带 issue 编号（如 #[ignore = \"等待 #12\"]）"
    echo "$line"
  fi
done < <(grep -RIn '#\[ignore' crates --include='*.rs' || true)

if [ "$fail" -eq 1 ]; then
  echo "约束扫描未通过——规则见 docs/CONSTRAINTS.md"
  exit 1
fi
echo "✅ 约束扫描通过（AC-01 / AC-02 / AC-08 / PR-04）"
