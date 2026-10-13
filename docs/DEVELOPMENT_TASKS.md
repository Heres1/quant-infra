# quant-infra 开发任务计划（滚动式）

> 版本 v1.0 · 2026-10-13 · 上游：DEVELOPMENT_PLAN.md（里程碑路线图）
> 定位：本文是**任务级执行计划**——当前里程碑拆到子任务（含工时/验收/负责人），下一里程碑概要级，其余保持里程碑级，每个里程碑开工前一周细化。
> 为什么滚动式：为 12 个月后的事写任务细节必然腐烂；为当前一周的事写细节才能严格执行。

---

## 1. 执行工作流（每个任务的生命周期）

```
todo → in_progress → 读规格(MODULE_DESIGNS/ARCHITECTURE) → 编码
    → 本地 CI 全绿(fmt/clippy/test/扫描) → 自审(CONSTRAINTS §7.2 checklist)
    → 合入 main → DoD 确认(TC 全过) → 更新本文"状态"列
```

**分工边界**（CONSTRAINTS PR-03 的落地）：

| 谁 | 做什么 |
|---|---|
| AI | **全部开发**（2026-10-13 用户全权委托）：领域代码、脚手架、CI/工具链、文档、调研、review |
| 用户 | 方向决策、里程碑验收与答辩、约束变更审批、GitHub 账号操作 |
| 沿用机制 | PR 描述含"设计要点"；里程碑验收 3 问（PR-03 修订版），架构叙事可辩护性由 docs/ 文档集承载 |

**状态维护**：下表"状态"列是唯一进度事实源；合入即更新。M0.5 建立仓库后，新任务走 GitHub issues，本文维护里程碑任务表状态。

## 2. M0 任务分解（当前里程碑）

| ID | 任务 | 交付物 | 验收 | 预估 | 负责 | 状态 |
|---|---|---|---|---|---|---|
| T0.1 | workspace 地基 | Cargo.toml/两空壳 crate/toolchain/.gitignore | clippy+test 绿 | 1h | AI | ✅ done 2026-10-13 |
| T0.2 | T1 强制基础设施 | CI×7 job、扫描器、覆盖率门槛、deny、pre-commit | 本地绿 + 扫描器红测通过；coverage/deny/gitleaks 待 T0.5 首跑验证 | 2h | AI | ✅ done 2026-10-13 |
| T0.3 | core-types 领域类型 | money/price/qty/instrument/rounding/fees/model 七模块 + lib 出口 | 30/30 测试绿（TC-C1..C7 全过）、clippy -D warnings 零警告、约束扫描过；覆盖率待 T0.5 CI 首跑确认 | ~15h | AI | ✅ done 2026-10-13 |
| T0.4 | time-core 最小版 | EngineTime/Clock trait/SessionPhase 枚举（10 变体含文档） | 2/2 测试绿 + AC-08 扫描过 | 2h | AI | ✅ done 2026-10-13 |
| T0.5 | GitHub 上线 | 公开仓库、main 分支保护(7 checks)、hooksPath、toolchain 固定 1.90.0、CI 首跑修复 | CI 全绿含 coverage/deny/gitleaks | 1-2h | 用户+AI | ✅ done 2026-10-13：github.com/Heres1/quant-infra 公开；CI run#2 7/7 绿；分支保护生效；deny 修复（license 字段）、gitleaks 根提交区间问题自愈 |
| T0.6 | M0 验收演示 | 演示记录（截图/数据） | CONSTRAINTS §6 全项 + DEVELOPMENT_PLAN §9 M0 场景 | 1h | 用户+AI | ✅ 记录完成 docs/acceptance/M0-acceptance.md；待用户 3 问答辩（PR-03）后正式关闭 M0 |

**M0 出口准则**：CONSTRAINTS §6 T1 基础设施清单逐项绿 + 演示记录归档（PR-05）。

### T0.3 子任务表（core-types，按序实现，每步 `cargo test`）

| ID | 子任务 | 要点 | 对应用例 | 预估 |
|---|---|---|---|---|
| T0.3a | `Money(i64)` 万分之一元 | Add/Sub/checked 系（溢出返回 Result/Option 不 panic）/Display（元，2 位小数） | TC-C1-01..03 | 2h |
| T0.3b | `Price(i64)` 千分之一元 | `new_checked(tick)` 对齐校验/Display | TC-C2-01..02 | 1.5h |
| T0.3c | `Qty(i64)` + 板块枚举 | Board{Main,ChiNext,Star,Bse}/LotRule/PriceLimitType/AssetType | TC-C3-01 | 1h |
| T0.3d | `Instrument` | `check_qty(qty, side, is_odd_lot_close)` 申报规则；`price_limit(prev_close)` 涨跌停（**四舍五入至 tick**，见 TEST_PLAN §4.2 修正记录） | TC-C4-01..06 | 3h |
| T0.3e | Bar/Order/Fill/Position | 参考 QuantKit types.rs；升级：定点数、Position 分 `total/available`（T+1 语义字段） | 字段审查（后续模块消费） | 2h |
| T0.3f | `rounding` 模块 | 佣金四舍五入到分；印花税/过户费/经手证管向上取整到分（RISK_CONTROL §8） | TC-C6-01..04 | 1.5h |
| T0.3g | `fees` 模块 | `estimate_buy/sell`：分项+合计；最小佣金 5 元 | TC-C7-01..05 | 2h |
| T0.3h | 覆盖率补齐+自审合入 | llvm-cov ≥90%；PR 描述三段式 | CI 绿 | 1h |

> PR-06 时间盒：任何子任务超 2× 预算即停，书面记录阻塞点，拆分或调整。

## 3. M1 概要（下一里程碑，2026-11 开工前细化进本文）

| ID | 任务 | 一句话验收 |
|---|---|---|
| D1 | Python 环境与第一课 | uv + 30 行 akshare 拉茅台日线（Python 学习任务，Rust 对照教学） |
| D2 | 日线采集器 | 全市场增量下载，断点续采 |
| D3 | 清洗复权+质量门 | 8 类坏数据注入全部被拦（TEST_PLAN M1 节） |
| D4 | 存储 | ClickHouse 主库 + Parquet 导出 |
| D5 | 查询 API | `as_of` 点时查询，lookahead 测试过 |
| D6 | 日历/Instrument 主档 | 交易日历与证券主档的日常维护任务 |

## 4. M2–M6（里程碑级，细化见 MODULE_DESIGNS 各节）

M2 回测引擎+pyo3 → M3 策略 SDK+示例策略 → M4 平台服务 → M5 模拟盘+网关+合规基础 → M6 风控完整版+可观测+压测。各自开工前按 §2 格式细化。

## 5. 计划变更与让步记录（append-only）

| 日期 | 变更 | 原因 | 影响里程碑 |
|---|---|---|---|
| 2026-10-13 | 涨跌停取整规则由"向内取整"修正为"四舍五入至 tick"（RISK_CONTROL R2、MODULE_DESIGNS §1 同步修正） | 写 TEST_PLAN 具体用例时核对交易所规则发现规格错误 | T0.3d |
| 2026-10-13 | 开发模式变更：领域代码改由 AI 全权开发（用户明确委托"完全交给你来做"）；CONSTRAINTS PR-03 同步修订 | 用户全职入职后时间稀缺，明确指令 | 全部里程碑 |
