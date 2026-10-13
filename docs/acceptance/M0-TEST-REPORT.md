# M0 测试报告

> 报告日期：2026-10-13 · 范围：M0（workspace 脚手架、T1 约束基础设施、core-types、time-core）· 总结论：**PASS**

---

## 1. 结论

| 维度 | 结果 |
|---|---|
| CI 流水线（7 job） | **7/7 绿**（run #2 起） |
| 单元测试（L1） | **32/32 通过**（core-types 30 + time-core 2） |
| 覆盖率（EN-05） | core-types **97.86%**、time-core **100%**、全局 **97.95%**（门槛 90/90/70） |
| 供应链审计（cargo-deny） | advisories ok / bans ok / licenses ok / sources ok |
| 秘密扫描（gitleaks） | 全历史 4 commits、157KB，**0 泄漏** |
| 约束扫描器（AC-01/02/08、PR-04） | 通过（含红测自检：注入违规 3 项全部抓出） |
| 静态检查 | fmt ✓、clippy -D warnings 零警告 ✓ |

## 2. 测试环境

- 本地：macOS arm64 · Rust 1.90.0（rust-toolchain.toml 锁定，含 clippy/rustfmt/llvm-tools）· cargo-deny、gitleaks、cargo-llvm-cov（Homebrew）
- CI：GitHub Actions ubuntu-latest · 7 job 并行 · 公开仓库可查（github.com/Heres1/quant-infra/actions）

## 3. CI 运行历史

| Run | 提交 | 结果 | 说明 |
|---|---|---|---|
| #1 | 3a85bb4 | ❌ failure | deny（license 缺失）+ gitleaks（根提交扫描区间）两个设施问题，见 §6 |
| #2 | 0e97fa3 | ✅ success | 修复后 7/7 全绿 |
| #3 | 38e95c6 | ✅ success | 文档提交，回归绿 |

## 4. 单元测试用例（L1，依据 TEST_PLAN §4）

**core-types（30 条）**：

| 组 | 用例 | 覆盖的业务规则 |
|---|---|---|
| TC-C1（3） | Money 加减链无漂移 / 溢出返回 Err / 元串解析与展示 | 定点数语义（万分之一元）、防溢出 |
| TC-C2（2） | tick 对齐校验 / 展示与成交额换算 | 千分之一元、股票 0.01 与基金 0.001 档位 |
| TC-C3（1） | 四板块默认规则映射 | 主板/创业板/科创板/北交所 × 手数 × 涨跌停 |
| TC-C4（10） | 涨跌停 6 例 + 申报数量 4 例 | **四舍五入至 tick**（含 6.105→6.11 精确半分）、ST ±10%（2026-07 新规）、科创板 200 股起/北交所 100 股起、零股一次性申报 |
| TC-C6（4） | 舍入四规则 | half-up/ceil 到分、带余数精确舍入、比例换算到 tick |
| TC-C7（5） | 费用对账 | 最低佣金 5 元、印花 0.05% 仅卖出、费率舍入不串规则（手算核对值） |
| 其他（5） | Bar OHLC 校验 / Position T+1 不变量 / 负成交额拒绝等 | 构造期校验 |

**time-core（2 条）**：EngineTime 全序（事件排序基础）、SessionPhase 10 变体锁定（时段文档为人工 review 项，M2 状态机配全年边界遍历）。

## 5. 工具链检查（T1 约束的机器强制验证）

| 检查 | 命令 | 结果 |
|---|---|---|
| 格式 | cargo fmt --all -- --check | PASS |
| 静态分析 | cargo clippy --workspace --all-targets -- -D warnings（含 unwrap_used/expect_used/panic 禁用） | 0 警告 |
| 约束扫描 | scripts/lint_constraints.sh | PASS（AC-01 禁浮点、AC-02 舍入白名单、AC-08 禁真实时钟、PR-04 ignore 带 issue）+ 红测：注入违规代码 3 项全部命中 |
| 覆盖率 | scripts/check_coverage.sh（llvm-cov） | core-types 97.86% / time-core 100% / 全局 97.95%，全部达标 |
| 供应链 | cargo deny check | advisories / bans / licenses / sources 全 ok |
| 秘密扫描 | gitleaks detect | 4 commits / 157KB / 0 泄漏 |

**覆盖率明细（按文件）**：fees 100% · model 100% · price 100% · rounding 100% · lib 100% · instrument 97% · money 95% · qty 87%（3 行未覆盖为溢出分支的次要路径，达标留观）。

## 6. 缺陷记录（全部关闭，均为 S3 测试设施类）

| # | 现象 | 根因 | 修复 | 状态 |
|---|---|---|---|---|
| D1 | CI run#1 deny 失败（exit 4） | workspace crate 无 license 字段，licenses 检查报 unlicensed | 补 `license = "MIT"` | ✅ run#2 绿 |
| D2 | CI run#1 gitleaks 失败 | 首推扫描区间 `根提交^..` 中 `^` 不存在 → git fatal；**非泄密**（本地全历史 0 泄漏） | 后续 push 区间合法，自愈 | ✅ run#2 绿 |
| D3 | 覆盖率门槛"核心 crate 跳过"误报 | llvm-cov 在 macOS 输出绝对路径，脚本 `startswith` 相对前缀匹配落空（CI 因全局 70% 兜底而绿，实际未逐 crate 强制） | 改 `contains` 匹配 | ✅ 本地复验真实数字 |
| D4 | pre-commit 钩子 rustup 超时 | 全局 git 代理指向 127.0.0.1:7890 且代理未运行；llvm-tools-preview 缺失触发 manifest 下载 | 用户移除失效代理 + rsproxy.cn 镜像补装组件 | ✅ |
| D5 | 本地 deny advisory 库拉取失败 | 上述代理残留损坏本地 advisory-db 缓存；https clone 在该网络下不稳定 | 清缓存 + 环境作用域 git insteadOf 重写为 SSH | ✅ 本地全绿（CI 原生不受影响） |

## 7. 边界与未尽事项（按计划属后续里程碑）

- Python 侧测试（data-platform 质量门 8 类注入、lookahead）→ M1 引入（TEST_PLAN §8）
- property 测试（状态机矩阵/账本守恒/崩溃恢复）→ M2 引入
- 回测性能基线（≥150k bars/s/核）→ M2 验收
- 对抗性测试 13 条 → M6 验收

## 8. M0 出口判定

CONSTRAINTS §6 T1 基础设施清单逐项绿 + CI 证据 + 本报告 → **M0 PASS，正式关闭**（答辩环节按用户指示免除）。
