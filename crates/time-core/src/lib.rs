//! 时钟抽象 · 引擎时间 · 交易时段阶段（M0 最小版；完整时段状态机与交易日历在 M2）。
//!
//! 规格：docs/MODULE_DESIGNS.md §2 · 约束：docs/CONSTRAINTS.md AC-08
//! （本 crate 属"纯净 crate"：真实时钟标识符不得出现——包括注释——扫描器强制）。

/// 引擎时间：交易日 + 当日纳秒（交易所本地时区 Asia/Shanghai）。
/// 日界 = trade_date 而非自然日（ARCHITECTURE §7 时间边界）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct EngineTime {
    /// 交易日，格式 YYYYMMDD，如 20261013
    pub trade_date: i32,
    /// 自当日 00:00（交易所本地）起的纳秒
    pub nanos: i64,
}

impl EngineTime {
    pub const fn new(trade_date: i32, nanos: i64) -> Self {
        EngineTime { trade_date, nanos }
    }
}

/// 时钟抽象（INV-T1）：策略与引擎代码只经此读取时间；
/// 真实时钟的实现位于引擎装配层（LiveClock，M5），不进入任何纯净 crate。
pub trait Clock {
    fn now(&self) -> EngineTime;
}

/// 交易时段阶段（2026 规则；ARCHITECTURE §5.1，时间边界矩阵）。
/// M0 仅定义语义；阶段判定状态机（`phase(EngineTime)`）在 M2 实现并配
/// 全年时段边界遍历测试（MODULE_DESIGNS §2 测试要点）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SessionPhase {
    /// 非交易日，或收盘后（15:30 之后）
    Closed,
    /// 盘前 08:30–09:15：隔夜单挂起队列，不转发
    PreOpen,
    /// 开盘集合竞价 09:15–09:20：可申报、可撤单
    CallAuctionOpen,
    /// 开盘集合竞价 09:20–09:25：可申报、不可撤单（撤单请求直接拒绝并留痕）
    CallAuctionFrozen,
    /// 09:25–09:30：竞价结果撮合；收单但不在本阶段处理
    QueuedGap,
    /// 午间休市 11:30–13:00：收到的单挂起，13:00 处理
    LunchBreak,
    /// 连续竞价 09:30–11:30、13:00–14:57
    Continuous,
    /// 收盘集合竞价 14:57–15:00：不可撤单
    CallAuctionClose,
    /// 盘后固定价格交易 15:05–15:30（2026-07 起扩至沪深全部 A 股及 ETF；北交所暂缓）
    AfterHoursFix,
    /// 清算窗口 15:35 起：T+1 冻结当日买入、日终快照
    Settling,
}

#[cfg(test)]
mod tests {
    use super::*;

    // 引擎时间全序：同日按纳秒、跨日按 trade_date（事件全序的基础，ARCHITECTURE §5.2）
    #[test]
    fn engine_time_ordering() {
        let a = EngineTime::new(20_261_013, 100);
        let b = EngineTime::new(20_261_013, 200);
        let c = EngineTime::new(20_261_014, 1);
        assert!(a < b);
        assert!(b < c);
    }

    // TC-T-01（人工项的机器部分）：阶段变体数量与文档由 review 核对；此处锁定变体集
    #[test]
    fn session_phase_variants_locked() {
        let all = [
            SessionPhase::Closed,
            SessionPhase::PreOpen,
            SessionPhase::CallAuctionOpen,
            SessionPhase::CallAuctionFrozen,
            SessionPhase::QueuedGap,
            SessionPhase::LunchBreak,
            SessionPhase::Continuous,
            SessionPhase::CallAuctionClose,
            SessionPhase::AfterHoursFix,
            SessionPhase::Settling,
        ];
        assert_eq!(all.len(), 10);
    }
}
