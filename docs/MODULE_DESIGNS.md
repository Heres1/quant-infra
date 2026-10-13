# quant-infra 模块详设

> 版本 v0.1 · 2026-10-13 · 上游：`ARCHITECTURE.md`（总体）、`RISK_CONTROL.md`（risk/compliance/settlement 的规格详设）
> 每个模块统一八段式：**职责 / 不负责（边界）/ 关键接口 / 不变量 / 边界条件 / 失败模式与恢复 / 测试要点 / 对应里程碑**。
> 写代码前先读对应模块；实现与本文冲突时，改代码或改文档必须同步。

---

## 1. core-types（领域模型与定点数）

- **职责**：全部领域类型与数值语义的唯一事实源；舍入表唯一实现。
- **不负责**：任何 IO、时间获取、状态机。
- **关键接口**：`Money(i64, 1e-4元)`、`Price(i64, 1e-3元)`、`Qty(i64)`、`Instrument{symbol, board, asset_type, tick, lot_rule, price_limit_type, status}`、`Order/Fill/Position/Bar`；`fees::estimate_buy/sell()`、`rounding::*`。
- **不变量**：INV-N1 钱与价永不使用浮点；INV-N2 所有舍入只出自 `rounding` 模块；INV-N3 `Instrument` 不可变，变更=新版本。
- **边界条件**：零股卖出（主板/创业板一次性申报）；科创板 200 股起 +1；最小佣金 5 元；涨跌停价按交易所规则**四舍五入**取整至 tick（2026-10-13 修正，原"向内取整"有误，见 TEST_PLAN §4.2）；基金 tick=0.001。
- **失败模式**：无运行时失败（纯函数）；算术溢出用 checked_add，溢出=panic=引擎 safe mode。
- **测试要点**：费用计算对账用例（手工 Excel 核对）；ST/科创板/北交所数量规则参数化测试；溢出用例。
- **里程碑**：M0。

## 2. time-core（时钟/日历/时段状态机）

- **职责**：Clock 抽象、交易日历、时段状态机、EngineTime。
- **不负责**：真实时间之外的任何业务判断；行情数据本身。
- **关键接口**：`Clock::now()/schedule()`；`Calendar::is_trading_day/at_or_next_open()`；`Session::phase(EngineTime) -> Phase`。
- **不变量**：INV-T1 引擎系 crate 零墙钟依赖（CI cargo-deny 强制）；INV-T2 同刻事件全序处理（ARCHITECTURE §5.1）。
- **边界条件**：9:20–9:25 与 14:57–15:00 不可撤窗口；9:25–9:30 收单不处理；11:30–13:00 午休挂起；15:05–15:30 盘后固定价（沪深 A 股+ETF，2026-07 起；北交所暂缓）；临时休市公告进日历的更新流程。
- **失败模式**：日历缺失未来交易日 → 盘前自检失败 → 拒绝进入交易时段（fail-closed）。
- **测试要点**：2026 全年时段边界遍历（每个 Phase 切换分钟级验证）；Clock 注入下策略无法感知真实时间。
- **里程碑**：M0（trait）/M2（状态机完整版）。

## 3. event-core（事件与事件存储）

- **职责**：事件定义、append-only 存储、哈希链、快照与回放。
- **不负责**：业务语义判断；跨服务消息总线（v1 无）。
- **关键接口**：`enum Event{Market(..),Order(..),Account(..),Timer(..),Control(..)}`；`EventStore::append/append_batch/read_range/verify_chain/snapshot/replay`。
- **不变量**：INV-E1 append-only（PG 权限+触发器）；INV-E2 确定性回放可重建状态；INV-E3 `payload_hash=sha256(prev_hash‖payload)`。
- **边界条件**：同刻事件排序=网关接收序；回放期间禁止一切对外副作用（网关调用/通知）；快照粒度=每 10 万事件或每日收盘。
- **失败模式**：写失败（PG 不可达）→ 引擎 safe mode（事件丢不得，账本系统第一原则）。
- **测试要点**：写入后逐日 verify_chain；kill -9 后 replay 与崩溃前状态逐字段相等（property test）；篡改历史 payload → verify 失败。
- **里程碑**：M2（回测内存版）→ M5（PG 持久版+哈希链）。

## 4. gateway-api / gateway-sim（网关与模拟撮合）

- **职责**：trait 定义 + caps；sim 实现回测与纸面交易共用撮合。
- **不负责**：风控判定（在链上）；真实通道的协议细节（broker 适配器自己封装）。
- **关键接口**：ARCHITECTURE §5.3；sim 撮合配置 `FillModel{slippage, participation_cap=10%, auction_fill, limit_board_behavior}`。
- **不变量**：INV-G1 caps 只能收缩检查不能放宽；INV-G2 client_order_id 幂等去重；sim 撮合对同一重放序列结果确定。
- **边界条件**：涨跌停一字板不成交（只挂不撮）；成交量参与率上限；集合竞价以竞价价格+量约束成交；停牌日无 bar 无成交；部分成交按 bar 内可容量切片；撤单在下一事件时刻生效（排队延迟可配，默认 0）。
- **失败模式**：sim 无故障面；broker 网关断线 → 在途单预案（cancel-on-disconnect 可配）+ 重连后 open-order reconcile（以券商回报为准）。
- **测试要点**：涨跌停/停牌/竞价/部分成交四族用例；同一事件序列重放两次结果逐字段一致；幂等：同 id 重复 submit 只产生一次成交。
- **里程碑**：M2（sim 日线）→ M5（分钟+实时纸面）→ M5 末（broker 适配器设计稿，实现视通道可行性）。

## 5. oms（订单状态机）

- **职责**：订单生命周期唯一管理者；在途单簿。
- **不负责**：判定订单是否该存在（风控）、成交后记账（accounting）。
- **关键接口**：`Oms::on_intent(OrderIntent)->Result`、`on_report(ExecutionReport)`、`active_orders(account)->Vec`。
- **不变量**：INV-O1 迁移仅由回报事件驱动，pybind 无迁移入口；INV-O2 每次迁移=一条事件存储记录；非法迁移=拒绝+告警+safe mode。
- **边界条件**：状态全表与守卫见 ARCHITECTURE §5.4；回报乱序（先撤后成）→ 以 (seq) 序为准处理并记录冲突审计；超时未获 ack（>30s）→ 冻结新单 + 人工。
- **失败模式**：崩溃恢复=open-order reconcile（ARCHITECTURE §6.3），以券商回报为准修账。
- **测试要点**：全迁移路径覆盖 + 全部非法迁移拒绝；乱序回报注入；崩溃恢复一致性。
- **里程碑**：M2。

## 6. accounting（账本与 T+1）

- **职责**：资金/持仓/费用的账本真相；可用量计算；日终快照。
- **不负责**：对账（settlement）；订单状态。
- **关键接口**：`Ledger::apply_fill(Fill)`、`available_cash()`、`position(sym)->Position{total, available, frozen}`、`daily_snapshot(trade_date)`。
- **不变量**：INV-A1 账本=不可变流水（成交+费用事件）+可重算快照；INV-A2 任意时刻 `available = total − 当日买入 − 在途卖出`；INV-A3 费用科目拆分（佣金/印花税/过户费/经手证管）逐笔可查。
- **边界条件**：**当日卖出回款即时可用于买入**（卖出成交即时贷记可用资金，股份冻结至次日）；当日买入 available=0，次日 09:00 解冻；分红送转事件日按 data-platform 的 adjust_factor 处理；现金永不出现负数（R3 保证，账本层 double-check 拒绝）。
- **失败模式**：apply_fill 幂等（以 fill_id 去重）；重算快照与旧快照不等 = 数据损坏告警。
- **测试要点**：T+1 全场景（当日买卖混排）；卖出回款再买入；分红除权日持仓成本；费用科目与 RISK_CONTROL §8 舍入表一致。
- **里程碑**：M2。

## 7. risk（风控链）——规格详见 RISK_CONTROL.md §3–§5

- **职责**：R0–R8 检查链、三级 kill switch、事中监控。本文只约定模块边界。
- **不变量**：链序不可变；检查器无副作用（R5 扣减除外，失败零副作用）；fail-closed；无旁路（engine 是唯一入口，ARCHITECTURE §4 依赖铁律）。
- **测试要点**：对抗性清单逐条（RISK_CONTROL §7）= 验收测试集。
- **里程碑**：M2 内嵌最小链（R2/R3/R4）→ M6 完整版。

## 8. compliance（合规引擎）

- **职责**：高频阈值守护（R5 计数与仪表）、报备档案管理、留痕与哈希链协作、月度合规报表、外接报送导出。
- **不负责**：判定单一订单是否违规（风控链负责）；监管政策解读（文档维护人负责）。
- **关键接口**：`Limiter::acquire(account, strategy, now)->Result`、`ProfileStore`（报备档案 CRUD+导出）、`Report::monthly(trade_month)`。
- **不变量**：限流计数口径=申报+撤单合计（与监管一致）；config 硬顶=监管值，越顶配置启动失败；档案缺失的实盘账户无法启动（ARCHITECTURE §8）。
- **边界条件**：跨日重置以 trade_date；Redis 与本地双层计数不一致→取大者（保守）；档案"需重新报告"状态自动置位条件=账户/策略类型/软件信息变更。
- **失败模式**：计数存储不可用→fail-closed 拒新单。
- **测试要点**：RISK_CONTROL §7 前三行用例；报表数字与手工统计一致。
- **里程碑**：M5 基础（档案+限流）→ M6 完整（报表+仪表）。

## 9. data-platform（Python：采集/清洗/质量门/入库）

- **职责**：多源采集（akshare 为主，efinance/baostock 冗余）、清洗复权、**质量门**、ClickHouse/Parquet 入库、查询 API（服务端）、交易日历与 Instrument 主档维护。
- **不负责**：实时行情低延迟分发（M5 的行情网关单独做）；交易。
- **关键接口**：CLI/任务：`ingest（增量+全量）、rebuild-adjust、validate`；查询 API：`bars(symbol, range, adjust, as_of)`——**as_of 参数强制**（点时查询）。
- **不变量**：INV-D1 未过质量门的数据进隔离区（quarantine 表），永不进主库；INV-D2 每行带 source 与 ingested_at 字段级标记；INV-D3 查询 API 永不返回 close_time > as_of 的数据（P5 的数据侧保证）。
- **边界条件**：多源冲突→优先级 akshare>efinance>baostock，字段级表决，分歧>阈值入隔离区+告警；复权因子变更导致历史价差>1%→全量重建任务；停牌日无 bar 不补值（显式缺失）；退市股票保留（防幸存者偏差，股票池点时化）。
- **质量门清单**：schema/类型校验 → 空值与重复检测 → OHLC 关系（low≤open,close≤high）→ 涨跌停界内校验（对照 Instrument）→ 成交量≥0 → 复权连续性 → 跨源一致性 → 日历完整性（交易日无数据=告警）。
- **失败模式**：源站接口变动→采集失败告警+冗余源顶替；质量门失败→隔离+告警，主库不受影响。
- **测试要点**：注入 8 类坏数据（错价/缺行/复权错/重复/停牌有价/超涨跌停/负量/未来行）→ 质量门全部拦截；as_of 点时查询不泄露未来。
- **里程碑**：M1（含 Python 学习任务，见 DEVELOPMENT_PLAN §7）。

## 10. strategy-runtime + pybind / sdk（策略运行时）

- **职责**：引擎装配与事件循环（engine crate）；pyo3 绑定；Python SDK 面。
- **不负责**：策略内容；平台服务。
- **SDK 表面（全部，v1 不加）**：

```python
class Strategy:
    def on_start(self, ctx): ...
    def on_bar(self, ctx, bar): ...
    def on_order(self, ctx, report): ...
    def on_trade(self, ctx, fill): ...
    def on_stop(self, ctx): ...

# ctx 能力面（越界即 AttributeError——能力即边界）
ctx.now()                      # 引擎时间，非墙钟
ctx.history(symbol, n, freq)   # 只返回 close_time <= now 的数据
ctx.universe(as_of=date)       # 点时股票池
ctx.submit(symbol, side, qty, price=None, tif=...)   # 唯一下单入口→风控链
ctx.cancel(client_order_id)
ctx.account.cash / ctx.account.position(sym)          # 只读快照
# ctx 没有：网络、文件、time.time()、绕过 submit 的任何下单途径
```

- **不变量**：INV-S1 策略进程无网络/文件写权限（v1 靠进程边界+review，强沙箱=§backlog）；INV-S2 SDK 数据面只吐引擎时间可见数据；INV-S3 回测/模拟/实盘三模式策略代码零修改。
- **边界条件**：on_bar 内抛异常→策略级熔断（L3）+ 事件留痕，不影响引擎与其他策略；策略阻塞超过 bar 预算→告警（回测中=直接终止该回测）。
- **失败模式**：策略进程崩溃→重启后从事件存储重放恢复上下文（实盘），回测直接判负。
- **测试要点**：三模式切换同结果；恶意 ctx 使用（访问私有属性/超界）全部被拒；异常策略不拖垮引擎。
- **里程碑**：M2（绑定+最小 API）→ M3（完整 SDK+示例策略）。

## 11. server（平台服务：认证/RBAC/策略注册/调度/实验/审计查询）

- **职责**：axum API 与 Web 后端；用户与权限；策略版本注册；任务调度；实验记录；审计查询；通知。
- **不负责**：引擎内决策；行情服务性能路径（查询代理给 data-platform）。
- **关键接口**：REST `/auth /users /strategies /experiments /jobs /audit /recon`；调度任务表（见下）。
- **不变量**：INV-P1 密码 Argon2id、网关凭据 AES-GCM 加密且永不出 storage、永不入日志（测试断言 grep 日志）；INV-P2 审计查询接口只读；INV-P3 策略版本一经 approved 不可变（git-backed，tag 锁定）；INV-P4 实盘启动检查链：报备档案（R1）+ kill switch 复位 + 对账无未决差异。
- **边界条件**：RBAC 矩阵（DEVELOPMENT_PLAN §2.5）；双人规则操作（限流参数变更、L1 恢复、差异销账）需两个不同 Admin 的审计签名；回测任务队列按用户配额调度，防单用户占满。
- **调度任务表**：08:30 盘前自检 | 09:00 T+1 解冻核对 | 盘中策略定时任务 | 15:35 结算快照 | 16:00 对账单拉取 | 16:15 对账 | 每日 17:00 数据更新 | 每月 1 日合规报表。
- **失败模式**：调度任务失败→重试 3 次指数退避→告警；对账任务失败视同对账差异（次日禁交易，宁可错杀）。
- **测试要点**：RBAC 矩阵全覆盖（4 角色 × 全接口）；越权 401/403；双人规则不可单人完成；凭据不出日志。
- **里程碑**：M4（axum 是你的补强技能，先做 auth/RBAC/实验记录最小闭环）。

## 12. settlement（清算与对账）

- **职责**：日终结算（T+1 冻结/解冻）、三方对账、差异工单、修账流程。
- **不负责**：账本日常记账（accounting）。
- **关键接口**：`settle(trade_date)`、`reconcile(broker_statement)`、`diff_report()`、`resolve_diff(diff_id, approver×2)`。
- **不变量**：INV-R1 匹配键=client_order_id+券商回报号，数量/价格/费用全等；INV-R2 有未决差异→平台实盘禁交易（L1）；INV-R3 修账必须以券商为准+审计事件+双人确认。
- **边界条件**：券商对账单字段缺失/格式变化→按对账失败处理（fail-closed）；费用差异容差=0；T 日 16:15 未完成对账→视同差异。
- **测试要点**：构造 5 类差异（多成交/少成交/费差/持仓差/资金差）逐个走全流程；销账后审计可查全链。
- **里程碑**：M5（纸面交易对账=自对自，验证管道）→ M6（broker 对账单接入）。

## 13. observability（横切）

- **职责**：指标、结构化日志、告警路由。
- **关键指标**：订单路径延迟直方图（§6.1 分段）、R0–R8 各检查拒绝计数（按 reason_code）、R5 限流器利用率、网关心跳与重连、行情新鲜度、回测吞吐、调度任务成功率、对账差异计数。
- **不变量**：日志含 trace_id=client_order_id（订单全链路可查）；日志禁含凭据/个人敏感信息。
- **实现**：tracing + Prometheus exporter + Grafana 面板（dashboard JSON 进 repo）。
- **里程碑**：M2 起埋点（tracing 先行）→ M6 完整面板+告警。

---

## 附 A：实现顺序与里程碑对照

| 里程碑 | 模块交付 | 演示验收（DEVELOPMENT_PLAN §9） |
|---|---|---|
| M0 | core-types、time-core(trait)、CI | cargo test 全绿 |
| M1 | data-platform | 全市场日线入库+质量门抓错 |
| M2 | event-core、gateway-sim、oms、accounting、pybind、risk(最小链)、engine | Python 10 行跑 3 年回测 ≤30s |
| M3 | sdk 完整、示例策略×3 | 策略零 Rust |
| M4 | server(auth/RBAC/调度/实验)、web 核心 | 双用户 RBAC 演示 |
| M5 | 实时行情、纸面网关、compliance(档案+限流)、settlement(自对账) | 实时模拟盘+对账 |
| M6 | risk 完整、observability、部署、压测 | 对抗性测试清单全过 + Grafana 演示 |

## 附 B：文档维护规则

- 监管参数变化 → 只改 `RISK_CONTROL.md` §8 与 `ARCHITECTURE.md` §7/§8，代码 config 跟随。
- 模块实现与本文冲突 → 当场改文档（小改）或开 issue（大改），禁止代码静默偏离。
- 每个模块的"测试要点"就是该模块 DoD（完成的定义）。
