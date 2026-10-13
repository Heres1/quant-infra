# quant-infra 架构设计

> 版本 v0.1 · 2026-10-13 · 上游：`DEVELOPMENT_PLAN.md`（方案与里程碑）· 配套：`RISK_CONTROL.md`（风控合规详设）、`MODULE_DESIGNS.md`（模块详设）
> 监管相关数字以交易所/证监会最新公告为准，变化时只改本文 §7/§8 与 `RISK_CONTROL.md` 的参数表。

---

## 1. 设计原则（每条都是对市面某短板的针对性回应）

| # | 原则 | 内容 | 市面现状（我们要超越什么） |
|---|---|---|---|
| P0 | **确定性内核** | 回测/模拟/实盘共用同一套引擎代码；时间通过 `Clock` trait 注入，策略与引擎代码永远不直接读墙钟 | vn.py/backtrader 回测与实盘是两条代码路径；nautilus_trader 做到了但没有 A 股合规层与多用户层 |
| P1 | **默认拒绝（fail-closed）** | 一切"是否放行"的问题默认答案是"否"；风控/合规组件自身故障 = 拒绝所有新订单，而不是放行 | 市面开源的风控普遍是"可绕过的过滤器"（策略可以直接调下单接口） |
| P2 | **合规即架构** | 监管要求（事前报备、高频阈值、留痕、熔断）映射为**不可关闭**的架构组件（见 §8 映射表），不是可选插件 | 市面把合规丢给券商；自研平台普遍没有这一层。2024-10 程序化新规后这层是刚需 |
| P3 | **证据链** | 事件溯源：事件存储 = 审计日志，append-only + 日级哈希链防篡改；任何状态变化可追溯到触发事件 | 开源项目普遍只有散落的应用日志，无防篡改能力 |
| P4 | **显式边界** | 每个模块独占自己的状态，跨模块只经 trait 或事件；每个模块文档化"不变量 + 边界条件 + 失败模式"（MODULE_DESIGNS.md） | 多数开源是单进程 + 全局可变状态，边界靠约定俗成 |
| P5 | **防未来函数是 API 保证，不是纪律** | 数据访问层只吐 `close_time ≤ 引擎当前时间` 的数据；股票池点时化（point-in-time universe） | 几乎所有开源回测框架靠用户自觉，未来函数是回测结果不可信的第一大来源 |
| P6 | **数据可信** | 数据入库前必须过质量门（§MODULE_DESIGNS data-platform），坏数据进隔离区不进主库，字段级来源标记 | tushare 2025-08 停运、akshare 频繁断接口：无质量门的数据管道在真实环境必然翻车 |
| P7 | **通道可替换** | 一切交易所/券商接触收敛在 Gateway trait 之后；通道政策变化只换适配器 | miniQMT 2026-07 起被收紧清理是活教训：押注单一通道 = 架构级风险 |

---

## 2. 系统上下文（谁在用，对接什么）

```
  Admin ─┐                          ┌─ 数据源(akshare/efinance/baostock)
 Researcher ─┤  Web UI(Vue3) / API    ├─ 券商交易通道(PTrade/QMT适配器, 持牌外接)
    Trader ─┘     │                   └─ 通知渠道(邮件/webhook)
                quant-infra 平台
                  │
              Viewer(只读) / 审计员(只读审计日志)
```

关键边界：平台**永不直连交易所**；实盘只经持牌券商通道；行情免费源仅自用不转发（合规红线，见 DEVELOPMENT_PLAN §2.1）。

## 3. 容器视图与进程模型

```
┌─────────────────────────── 单机 docker compose ───────────────────────────┐
│                                                                            │
│  [web] Vue3 静态资源                                                        │
│  [server] axum 平台服务：auth/RBAC·策略注册·调度·实验·审计查询·对账展示       │
│      │ gRPC/内存调用                                                        │
│      ├── [engine<acct-A>] 实盘引擎进程（每账户独立进程，崩溃爆炸半径=单账户） │
│      ├── [engine<acct-B>] ...                                              │
│      └── [backtest-worker×N] 回测进程池（任务队列+CPU配额）                  │
│  [storage] ClickHouse(行情) · PostgreSQL(业务/事件存储) · Redis(队列/状态)   │
│  [obs] Prometheus + Grafana · 结构化日志                                    │
└────────────────────────────────────────────────────────────────────────────┘
```

进程模型决策（面试考点）：
- **回测 = 库调用**：engine 是 crate，server 按 CPU 配额 fork 回测子进程。原因：回测是纯计算，进程隔离换稳定性，配额防单用户占满。
- **实盘 = 每账户一个独立进程**：原因：①故障隔离（一个账户的网关崩溃不影响其他账户）②风控组件与账户状态私有 ③未来水平扩展的最小单元。
- **策略 = 引擎进程内的沙箱边界**：v1 靠"策略只能经 SDK 对象操作 + 无网络权限 + 代码 review"保证；WASM/seccomp 强沙箱列入 backlog（§10，诚实声明）。

## 4. Crate 布局（Rust workspace）

```
crates/
  core-types      领域模型与定点数（Instrument/Bar/Order/Fill/Position/Money/Qty/Price）
  time-core       Clock trait · 交易日历 · 时段状态机
  event-core      事件定义 · 事件存储(append-only+哈希链) · 回放
  oms             订单状态机
  accounting      账本 · T+1 可用量 · 费用计算
  risk            事前检查链 · 限流器 · kill switch（规格见 RISK_CONTROL.md）
  compliance      报备管理 · 高频阈值守护 · 留痕
  gateway-api     MarketDataGateway / ExecutionGateway trait + GatewayCaps
  gateway-sim     模拟撮合网关（回测与纸面交易共用）
  gateway-broker  券商适配器（M5：PTrade/QMT 可用通道）
  engine          编排：事件循环 · 装配(Clock+Gateway+OMS+Risk+Accounting)
  pybind          pyo3 绑定（策略 SDK 的 Rust 面）
  server          axum 平台服务
  storage         ClickHouse/PG/Redis 访问层
py/
  sdk             Python 策略 SDK（薄封装 pybind + 类型 stub）
  data-platform   采集/清洗/质量门/入库（akshare 等）
web/              Vue3 前端
docs/             本文 + 模块详设 + 风控详设（文档是交付物的一部分）
```

依赖铁律：`risk`/`compliance` 不依赖任何具体 gateway；`engine` 是唯一能把订单送达 gateway 的组件；策略代码只看得到 `pybind` 暴露面。

## 5. 核心抽象与不变量

### 5.1 时钟与时间边界（time-core）

```rust
trait Clock { fn now(&self) -> EngineTime; fn schedule(&self, at: EngineTime, ev: TimerEvent); }
```
- `EngineTime` = (trade_date, exchange_nanotime)，交易所本地时区 Asia/Shanghai，内部纳秒精度。
- **不变量 INV-T1**：engine/oms/accounting/risk/pybind 的 crate 禁止依赖 `std::time::SystemTime`（CI 用 cargo-deny 检查依赖图 + code review 规则）。
- **不变量 INV-T2**：回测时钟只在引擎消费完当前时间戳的全部事件后前进（同刻事件按 (seq) 全序处理）。
- 时段状态机（2026 规则）：`PreOpen → CallAuctionOpen(9:15-9:20可撤) → CallAuctionFrozen(9:20-9:25不可撤) → QueuedGap(9:25-9:30收单不处理) → Continuous(9:30-11:30,13:00-14:57) → CallAuctionClose(14:57-15:00不可撤) → AfterHoursFix(15:05-15:30,沪深A股+ETF,以收盘价) → Settling`。每次状态迁移发布 `SessionEvent`，风控 R0 依赖它。
- 交易日历是一等数据（节假日/临时休市），由 data-platform 每日校验更新。

### 5.2 事件与事件存储（event-core）

- 事件全序：(exchange_nanotime, seq)。回测中时间由重放决定，实盘中由网关回报时间+接收序决定。
- 事件存储 schema：`(seq u64 PK, engine_ts, trade_date, topic, payload_bytes, payload_hash, prev_hash)`，日级锚定。
- **不变量 INV-E1**：append-only，任何组件无 UPDATE/DELETE 权限（PG 层面用权限 + 触发器双重保证）。
- **不变量 INV-E2**：状态可重建——engine 崩溃后 = 最近快照 + 重放其后事件，结果与崩溃前一致（事件处理器必须确定性，禁止在 handler 里读墙钟/随机数/外部状态）。
- 哈希链：`payload_hash = sha256(prev_hash || payload)`，每日锚定到只读介质。篡改任一历史事件 → 链验证失败告警。这是"留痕"的强实现（P3）。

### 5.3 网关抽象（gateway-api）

```rust
trait MarketDataGateway { fn subscribe(...); fn events() -> Receiver<MarketEvent>; fn heartbeat() -> Health; }
trait ExecutionGateway {
    fn capabilities(&self) -> GatewayCaps;            // 支持的订单类型/时段/费率/自身限速
    async fn submit(&self, cmd: SubmitCmd) -> GatewayAck;   // 幂等：client_order_id 去重
    async fn cancel(&self, id: ClientOrderId) -> GatewayAck;
    fn reports(&self) -> Receiver<ExecutionReport>;
}
```
- **不变量 INV-G1**：风控 R2 静态校验的规则数据（涨跌停类型/申报单位/tick）来自 `Instrument`，网关 capabilities 只能收缩不能放宽检查。
- **不变量 INV-G2**：对网关的每个 submit 都带全局唯一 `client_order_id`（UUIDv7，时间有序），网关层幂等去重；重复提交返回同一 Ack。
- `gateway-sim`：回测与纸面交易共用。撮合规则显式建模（涨跌停一字板不成交、按 bar 成交量参与率上限默认 10%、集合竞价以竞价价格成交、滑点模型可配）——撮合可信度边界在 MODULE_DESIGNS §gateway-sim 列全。
- **网关适配器矩阵（2026-10-13 M1 重排后）**：`gateway-qmt`（主源，Windows 端 xtquant 订阅服务，经内部接口投递）/ `gateway-free-http`（腾讯批量轮询 + 东财全市场快照，政策兜底）/ `gateway-sim`。通道政策变化只影响延迟与源选择，不影响可用性。行情事件模型按**快照级**设计（M2 引擎 tick/快照 first，bar 为聚合视图）；实时落库双时间戳（exchange_ts 事件时间 / capture_ts 处理时间）。

### 5.4 订单状态机（oms）

状态：`Created → RiskPassed → Submitted → Accepted → PartiallyFilled → Filled | PendingCancel → Cancelled | Rejected | Expired`

| 迁移 | 触发 | 守卫 |
|---|---|---|
| Created→RiskPassed | 风控链 R0–R8 全通过 | 任一失败 → Rejected(cause=check_id) |
| RiskPassed→Submitted | 会话允许该订单类型（R0） | 非法时段 → 挂起队列（隔夜单语义） |
| Submitted→Accepted | 网关回执 | 心跳超时 → 告警+冻结新单 |
| *→Cancelled | 撤单回执 | 9:20-9:25 / 14:57-15:00 撤单请求直接拒绝（exchange 行为建模） |
| 任意→Rejected | 网关废单回报 | cause 必填，写入审计 |

- **不变量 INV-O1**：状态只能由执行回报事件驱动迁移，策略代码无迁移入口（pybind 不暴露）。
- **不变量 INV-O2**：每个状态迁移 = 一条事件存储记录（谁/何时/为何）。
- 非法迁移（如 Filled→Cancelled）= bug 级告警 + 事件拒绝 + 进 safe mode。

### 5.5 数值与舍入（core-types）

- `Money = i64`，单位 0.0001 元（万分之一元）；`Price = i64`，单位 0.001 元（milli-yuan，股票 2 位小数×10，基金 3 位小数×1）；`Qty = i64`（股）。
- 禁用 f64 做钱（QuantKit 用 f64 是单机个人项目的性能取舍；本平台是账本系统，精度是正确性问题）。
- 舍入表（全平台唯一实现 `core-types::rounding`，禁止散落 `round()`）：
  - 印花税 0.05% 卖出：`notional*5/10000` 向上取整到分
  - 佣金：`max(notional*rate, 5.00元)`，费率乘完后四舍五入到分
  - 过户费 0.001%、经手+证管 0.00541%：向上取整到分
  - 展示层舍入与账本内部值分离，账本永远是精确 i64。

### 5.6 身份与幂等

- `client_order_id`：UUIDv7（OMS 生成，含时间前缀便于排查）。
- 全链路追踪：`trace_id = client_order_id` 贯穿 风控判定→网关→回报→账本→审计日志。
- 配置/策略变更：`change_id` 单调递增，每次生效记录审计事件（谁、何时、改了什么、审批人）。

## 6. 关键时序

### 6.1 实盘下单全链路（延迟预算为单机内部预算，不含券商）

```
策略(Python) ctx.submit(order)
 1 pybind 校验+序列化                          (<10µs)
 2 engine 投递事件 (OrderIntent)               (<50µs)
 3 risk 链 R0→R8 顺序判定                      (<200µs，含限流器原子操作)
 4 compliance 高频限流器扣令牌+计数             (<50µs)
 5 oms: Created→RiskPassed→Submitted，事件落库  (<100µs，批量异步持久化+同步ack语义)
 6 gateway.submit(client_order_id)             (网络，不计入)
 7 回报 ExecutionReport → oms 迁移 → accounting 过账 → 事件落库
 8 SDK 回调 on_order/on_trade (策略只读)
```
铁律：步骤 3–4 失败 → 步骤 5-6 永不发生；风控组件 panic/超时 → 引擎进入 safe mode（拒新单+告警），**绝不降级放行**（P1）。

### 6.2 回测一个交易日（gateway-sim 重放）

```
当日复权因子校验 → 隔夜队列单 9:15 进集合竞价 → 9:20 冻结撤单 → 9:25 竞价撮合(以开盘价,量约束)
→ 连续竞价逐 bar 撮合(涨跌停一字板不成交、参与率≤成交量10%、滑点+费用) → 14:57 收盘竞价
→ 15:05-15:30 盘后固定价单(收盘价撮合) → 15:35 结算: T+1 冻结当日买入 → 账本快照 → 绩效累计
```

### 6.3 崩溃恢复

`engine 重启 → 读最近账本快照 → 重放其后事件(INV-E2) → 向网关发送在途订单查询(open order reconcile) → 差异以网关回报为准修正账本并记录审计事件 → 恢复或进 safe mode`。**以券商回报为准**是最高原则：本地账本与通道冲突时，先禁交易再修账。

## 7. 边界条件矩阵（总表，逐条归属模块详设）

| 类别 | 边界条件（必须显式建模，禁止"默认行为"） | 归属 |
|---|---|---|
| 时间 | 时段状态机全迁移含"不可撤单"窗口；隔夜单语义；半日市(如有)/临时休市；日界=trade_date 而非自然日 | time-core |
| 数据 | bar 完成语义（时间戳 09:31 的 1m bar 覆盖 09:30:00–09:31:00，收到下一根才发布上一根——防部分 bar 泄露）；停牌无 bar；复权因子变更日；多源冲突取优先级+字段级表决，分歧入隔离区；缺失数据显式 NaN 不补值 | data-platform |
| 状态 | 订单状态机非法迁移=bug；账本不可变流水+可重算快照；网关断线在途单预案（cancel-on-disconnect 可配） | oms/accounting/gateway |
| 数值 | 舍入表唯一实现（§5.5）；零股卖出规则（主板/创业板含零股须一次性申报、科创板<200 股一次性）；最小佣金 5 元；价格超 tick 对齐=废单 | core-types/accounting |
| 并发 | 一账户一引擎（actor）；跨账户零共享可变状态；限流器为原子计数器；回测进程 CPU 配额 | engine/server |
| 故障 | fail-closed 全覆盖（风控/日历/行情源/网关任一异常→safe mode）；对账差异→次日禁交易直至人工解决 | risk/settlement |
| 合规 | 300 笔/秒、20000 笔/日阈值硬顶（config 上限即监管值，改配置需 Admin+双人复核+审计）；策略代码无网络/文件/时钟能力（v1 进程边界） | compliance/strategy-runtime |

## 8. 合规映射表（监管要求 → 架构机制，P2 的落地证明）

| 监管要求（出处） | 平台机制 | 不可关闭性保证 |
|---|---|---|
| 程序化交易事前报告（证监会 2024-10 规定；2025-07 交易所细则） | compliance 报备档案：账户/资金/策略类型/软件信息，一键导出；信息变更自动标记"需重新报告" | 组件常驻，无开关；实盘账户无报备档案 → 引擎拒绝启动实盘 |
| 高频认定：单账户 300 笔/秒 或 20000 笔/日（申报+撤单合计） | risk R5 限流器：默认 5 笔/秒，日 2000 笔；config 硬顶=监管值；利用率仪表盘 + 50%/80%/95% 三级预警 | 限流器位于订单必经路径，故障=fail-closed；阈值调整需双人审批+审计 |
| 交易留痕（证券法：委托记录保存不少于 20 年） | event-core 哈希链事件存储 + 年度 Parquet 冷归档 + 全生命周期审计查询 | append-only 由 DB 权限+触发器强制 |
| 异常行为监控（瞬时申报速率异常、频繁瞬时撤单） | R8 撤单比监控 + 速率指标，异常即告警并可自动降级为 safe mode | 同 R5 |
| 外接新规（2026-08 中证协/中基协）：禁止转借接口、熔断机制、报送 | 网关凭据按账户隔离加密存储；三级 kill switch；季度报送数据导出报表 | 凭据永不出 storage 模块、永不入日志（测试断言） |
| 数据不转售（行情授权边界） | 对外数据出口 API 默认关闭；任何导出走审计 | server 路由白名单实现 |
| 不做投顾/荐股（牌照红线） | 产品边界：无策略分享/推荐功能；README 免责声明；策略代码默认用户私有 | 产品决策，写进 CONTRIBUTING |

## 9. 性能与容量预算（验收硬指标）

| 指标 | 预算 | 依据 |
|---|---|---|
| 回测吞吐 | ≥150k bars/s/核（全市场 3 年日线 8 核 ≤30s） | 5000 股×750 bar=3.75M bar |
| 实盘订单内部路径 P99 | < 1ms（§6.1 步骤 1–5） | 分钟级策略富余，为 M6 压测报告留测量法 |
| 事件循环单 tick | < 500µs | 事件驱动内核健康度 |
| 事件存储写入 | 批量异步、崩溃零丢失（WAL） | INV-E2 |
| 单机资源地板 | 4C8G（docker compose 全家桶） | 单机生产级定位 |

## 10. 诚实声明：v1 明确不做（防范围蔓延 + 面试时的 trade-off 叙事）

- 策略强沙箱（WASM/seccomp）——v1 进程边界+review，backlog 有方案草图
- 多机高可用/异地容灾——单机 compose，事件存储设计已为多副本留缝（事件溯源天然支持）
- Tick 级撮合与排队位置建模——分钟/日线定位（DEVELOPMENT_PLAN §1）
- 期货/期权/两融、LLM 因子——见方案 §6"明确不做"清单
