-- quant-infra 行情存储初始化（M1）
-- 数值边界说明：行情价格序列为分析型存储，用 Float64（列存惯例）；
-- 账本/订单路径的定点数纪律（AC-01）在引擎边界生效，两者不混用。

CREATE DATABASE IF NOT EXISTS qinfra;

-- 证券主档（板块由代码前缀推断，status 以交易所披露为准逐步维护）
CREATE TABLE IF NOT EXISTS qinfra.instrument
(
    symbol     String,
    name       String,
    board      LowCardinality(String),
    asset_type LowCardinality(String) DEFAULT 'Stock',
    status     LowCardinality(String) DEFAULT 'Listed',
    updated_at DateTime64(3, 'Asia/Shanghai')
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY symbol;

-- 隔离区（INV-D1：未过质量门的数据只进这里，带原因与原始载荷）
CREATE TABLE IF NOT EXISTS qinfra.quarantine_bar_1d
(
    symbol      String,
    reason      LowCardinality(String),
    detail      String,
    payload     String,
    ingested_at DateTime64(3, 'Asia/Shanghai')
)
ENGINE = MergeTree
ORDER BY ingested_at;

-- K 线表：一次性历史导入 + 实时快照聚合产物共用
CREATE TABLE IF NOT EXISTS qinfra.bar_1d
(
    symbol      String,
    trade_date  Date32,
    open        Float64,
    high        Float64,
    low         Float64,
    close       Float64,
    volume      UInt64,          -- 股
    amount      Float64,         -- 元
    adjust      LowCardinality(String),  -- qfq / hfq / none
    source      LowCardinality(String),  -- akshare-em / qmt / tencent ...
    ingested_at DateTime64(3, 'Asia/Shanghai')
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (symbol, trade_date, adjust);

-- L1 快照表：实时订阅落库（M1-D2/D3）
CREATE TABLE IF NOT EXISTS qinfra.snapshot_l1
(
    symbol      String,
    exchange_ts DateTime64(3, 'Asia/Shanghai'),  -- 源给出的行情时间（事件时间）
    capture_ts  DateTime64(6, 'Asia/Shanghai'),  -- 本机收到时间（处理时间，乱序/延迟诊断用）
    last        Float64,
    open        Float64,
    high        Float64,
    low         Float64,
    pre_close   Float64,
    volume      UInt64,
    amount      Float64,
    bid1 Float64, bid1_vol UInt64,
    ask1 Float64, ask1_vol UInt64,
    bid2 Float64, bid2_vol UInt64,
    ask2 Float64, ask2_vol UInt64,
    bid3 Float64, bid3_vol UInt64,
    ask3 Float64, ask3_vol UInt64,
    bid4 Float64, bid4_vol UInt64,
    ask4 Float64, ask4_vol UInt64,
    bid5 Float64, bid5_vol UInt64,
    ask5 Float64, ask5_vol UInt64,
    source      LowCardinality(String)
)
ENGINE = ReplacingMergeTree(capture_ts)
ORDER BY (symbol, exchange_ts, source);

-- 5 分钟 K 线：沪深300 成分一次性导入（东财接口约回溯 7 周；深度历史走 baostock，backlog）
-- ts 为 bar 结束时刻（东财口径：09:35 = 09:30-09:35）
CREATE TABLE IF NOT EXISTS qinfra.bar_5m
(
    symbol      String,
    ts          DateTime64(3, 'Asia/Shanghai'),
    open        Float64,
    high        Float64,
    low         Float64,
    close       Float64,
    volume      UInt64,
    amount      Float64,
    adjust      LowCardinality(String),
    source      LowCardinality(String),
    ingested_at DateTime64(3, 'Asia/Shanghai')
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (symbol, ts, adjust);

-- 分钟线隔离区
CREATE TABLE IF NOT EXISTS qinfra.quarantine_bar_5m
(
    symbol      String,
    reason      LowCardinality(String),
    detail      String,
    payload     String,
    ingested_at DateTime64(3, 'Asia/Shanghai')
)
ENGINE = MergeTree
ORDER BY ingested_at;
