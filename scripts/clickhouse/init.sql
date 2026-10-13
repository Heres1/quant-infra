-- quant-infra 行情存储初始化（M1）
-- 数值边界说明：行情价格序列为分析型存储，用 Float64（列存惯例）；
-- 账本/订单路径的定点数纪律（AC-01）在引擎边界生效，两者不混用。

CREATE DATABASE IF NOT EXISTS qinfra;

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
