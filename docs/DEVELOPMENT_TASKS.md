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
| T0.6 | M0 验收演示 | 演示记录（截图/数据） | CONSTRAINTS §6 全项 + DEVELOPMENT_PLAN §9 M0 场景 | 1h | 用户+AI | ✅ done 2026-10-13：M0 正式关闭（答辩按用户指示免除，PR-03 二次修订）；记录 docs/acceptance/M0-acceptance.md + M0-TEST-REPORT.md |

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

## 3. M1 任务分解（当前里程碑，2026-10-13 重排：实时行情优先 + 一次性历史导入）

> 重排原因（用户决策 2026-10-13）：行情采集改为 **QMT/miniQMT 订阅优先**（低延迟推送），实时落库离线化，回放器驱动后续一切开发；历史数据用 akshare **一次性导入**解决回测冷启动。原"持续批量采集管道"取消。

| ID | 任务 | 要点 | 验收 | 预估 | 负责 | 状态 |
|---|---|---|---|---|---|---|
| D0 | 存储就绪 | docker-compose：ClickHouse 单机；建库表（snapshot/bar 双表 + source/capture_ts/exchange_ts 双时间戳字段） | 一条命令起库，SQL 查询通 | 2h | AI | ✅ done 2026-10-13：docker hub 在本网络不可达，本地改为 brew 官方单二进制 + `scripts/ch-start.sh`（compose 保留给服务器部署）；bar_1d/snapshot_l1 建表完成 |
| D1 | Python 环境 + 一次性历史导入 | uv 环境；akshare 拉全市场日线+分钟线（一次性）→ 质量门 → 入库；茅台冒烟脚本 | 全市场历史入库，TC 注入测试过 | 6h | AI | 🔄 大头完成 2026-10-13：方案 C 双份存（none+qfq 各 10,722,928 行，5257 只，2015→今），隔离 317 只带载荷；剩余：沪深300 分钟线（东财 1 分钟仅近 5 日，5 分钟可回溯数年——源限制） |
| D2 | 行情订阅网关 v1（QMT） | `gateway-qmt`：Windows 端采集服务（xtquant 订阅推送 → 双时间戳 → 投递数据层）；Mac 端接收落库 | 盘中实采 ≥1 交易日全量快照落库 | 8h | AI | ⏳ 等 QMT 开通 |
| D3 | 兜底采集适配器 | `gateway-free-http`：腾讯批量轮询（主兜底）+ 东财全市场快照（名单/兜底），同一 trait 可插拔 | 兜底源盘中独立采集 1 日通过质量门 | 4h | AI | ⏳ |
| D4 | 质量门 v2（快照流） | 8 类注入测试适配快照；乱序/缺口检测（按 exchange_ts）；跨源交叉校验 | 注入全拦 + 缺口告警 | 4h | AI | ⏳ |
| D5 | 回放器 | 按 (exchange_ts, seq) 重放驱动 Clock（接 time-core trait）；倍速控制 | 回放一日数据驱动引擎事件流 | 4h | AI | ⏳ |
| D6 | 调度与主档 | 盘中录制调度（时段状态机门控）；交易日历/Instrument 主档日常维护 | 日历+主档每日自更新 | 3h | AI | ⏳ |

**外部依赖（用户行动项）**：券商开通 QMT/miniQMT（资金门槛+办理周期）；准备一台 Windows 环境（实体/虚拟机/云主机）跑采集服务。
**合规注**：免费源与 QMT 自用落库均在边界内；不转发不售卖（LC-05）；未来若接付费 L2 先读转存条款。
**架构注**：双适配器（qmt 主/free-http 兜底）同一 trait，政策变化只影响延迟不影响可用性。

## 4. M2–M6（里程碑级，细化见 MODULE_DESIGNS 各节）

M2 **快照级事件回测引擎**（事件模型按 tick/快照设计，bar 为聚合视图；pyo3 暴露）→ M3 策略 SDK+示例策略 → M4 平台服务 → M5 实盘通道适配（行情已被 M1 消化）→ M6 风控完整版+可观测+压测。各自开工前按 §2 格式细化。

## 5. 计划变更与让步记录（append-only）

| 日期 | 变更 | 原因 | 影响里程碑 |
|---|---|---|---|
| 2026-10-13 | 涨跌停取整规则由"向内取整"修正为"四舍五入至 tick"（RISK_CONTROL R2、MODULE_DESIGNS §1 同步修正） | 写 TEST_PLAN 具体用例时核对交易所规则发现规格错误 | T0.3d |
| 2026-10-13 | 开发模式变更：领域代码改由 AI 全权开发（用户明确委托"完全交给你来做"）；CONSTRAINTS PR-03 同步修订 | 用户全职入职后时间稀缺，明确指令 | 全部里程碑 |
| 2026-10-13 | M1 重排：行情改为 QMT/miniQMT 订阅优先（实时落库+回放），历史数据 akshare 一次性导入；M2 引擎改快照级事件模型 | 用户决策（低延迟行情优先）；免费快照做兜底适配器对冲 QMT 政策风险 | M1/M2 |

### 5.1 欠账偿还（2026-10-13 还债日，对应 PHASE-REPORT §5）

| 欠账 | 状态 | 结果 / 方案 |
|---|---|---|
| #2 隔离整票粒度（317 只 none 数据丢失） | ✅ 已还 | `replay_quarantine`：重放改为**从源重新拉取**（载荷 60KB 截断不可靠的教训，截断上限提至 2MB）；质量门加上市初期宽限窗口（前 10 根 bar 豁免跳变）。回收 81 只；236 只中段 `[qfq]suspicious_jump` 留 D4（需主档+跨源判真伪），载荷留存 |
| #4 每日增量未自动化 | ✅ 已还 | `scripts/daily_update.sh` + launchd `com.quantinfra.dailyupdate`（工作日 17:30，近 7 日窗口幂等覆盖）；节假日空数据噪声暂由隔离区吸收，D6 日历门控后移除 |
| #5 文档漂移 | ✅ 已还 | ARCHITECTURE §5.3 补网关适配器矩阵与快照级事件模型；MODULE_DESIGNS §9 补复权感知质量门规则 |
| #1 分钟线 | 方案定稿，下会话执行 | 新表 `bar_5m`；源=akshare `stock_zh_a_hist_min_em`（period="5"；**东财 1 分钟仅近 5 日，属源限制**）；标的=沪深300 成分（`index_stock_cons_csindex("000300")`）；轻量 `gate_minute`（OHLC/正数/时序，无跳变检查——午休开盘跳空正常） |
| #3 退市股（幸存者偏差） | 方案定稿，下会话执行 | 元数据先行：`stock_info_sh_delist`/`stock_info_sz_delist` → instrument.status=Delisted（点时股票池基础）；价格数据探测 EM 对退市股的支持度，不足则补 baostock 源 |
| #6 python job 分支保护 | 本轮浏览器补勾选 | — |
| #7 单源无交叉校验 | 方案（D3/D4） | 兜底源上线后质量门加跨源字段级表决：同一 symbol 同一分钟两源价差 >0.1% 告警并双记 |
| #8 ingest 编排测试 / hfq / 观测 | 方案（分摊） | ingest 重试/断点用注入式 source mock 测（D4）；hfq 三份存等动态复权需求出现再加（backlog）；数据新鲜度 lag 指标提前到 D6 实现 |
