//! 交易模型静态部分：Bar / OrderIntent / Fill / Position。
//!
//! 边界（MODULE_DESIGNS §1）：订单状态机归 oms（M2），账本变动逻辑归 accounting（M2）；
//! 本文件只定义数据结构与构造期校验。Position 的 T+1 语义字段在此，
//! `available` 的推进（当日买入冻结、次日解冻）由 accounting 拥有。

use crate::fees::FeeBreakdown;
use crate::instrument::Side;
use crate::price::{Price, PriceError};
use crate::qty::Qty;

/// K 线。`ts` 为 Unix 纳秒（UTC）；bar 完成语义（收到下一根才发布上一根）
/// 由数据层保证（INV-D 系，M1）。bar 时间戳口径：覆盖区间为 [ts, ts+period)。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Bar {
    pub ts: i64,
    pub open: Price,
    pub high: Price,
    pub low: Price,
    pub close: Price,
    pub volume: Qty,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BarError {
    Price(PriceError),
    InvalidRange,
    InvalidVolume,
}

impl Bar {
    /// 构造校验：OHLC 关系（low ≤ open/close ≤ high）与成交量非负。
    pub fn new_checked(
        ts: i64,
        open: Price,
        high: Price,
        low: Price,
        close: Price,
        volume: Qty,
    ) -> Result<Self, BarError> {
        if high < low || open < low || close < low || high < open || high < close {
            return Err(BarError::InvalidRange);
        }
        if volume.raw() < 0 {
            return Err(BarError::InvalidVolume);
        }
        Ok(Bar {
            ts,
            open,
            high,
            low,
            close,
            volume,
        })
    }
}

/// 订单意图（策略产出的唯一订单形态；OMS 只接受 Intent，见 ARCHITECTURE §5.4 INV-O1）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OrderIntent {
    /// client_order_id：UUIDv7（OMS 生成）；M0 允许外部传入用于测试
    pub client_id: String,
    pub symbol: String,
    pub side: Side,
    pub order_type: OrderType,
    pub qty: Qty,
}

/// M0 仅限价单。盘后固定价格单（AfterHoursFix）在 M5 引入（ARCHITECTURE §5.1）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum OrderType {
    Limit { price: Price },
}

/// 成交回报（网关侧事实，账本据此过账；幂等键 = client_id + trade_id）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Fill {
    pub client_id: String,
    pub trade_id: String,
    pub symbol: String,
    pub side: Side,
    pub price: Price,
    pub qty: Qty,
    pub fees: FeeBreakdown,
}

/// 持仓快照。T+1 语义（INV-A2）：`available ≤ total`；
/// 当日买入计入 total 不计入 available，次日解冻；
/// 当日卖出回款即时可用（资金侧），股份侧在途卖出由 accounting 维护。
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct Position {
    pub symbol: String,
    pub total_qty: i64,
    pub available_qty: i64,
    pub avg_entry_price: Option<Price>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PositionError {
    NegativeAvailable,
    AvailableExceedsTotal,
}

impl Position {
    /// 构造期不变量校验（账本层的完整校验在 accounting，INV-A2）。
    pub fn validate(&self) -> Result<(), PositionError> {
        if self.available_qty < 0 {
            return Err(PositionError::NegativeAvailable);
        }
        if self.available_qty > self.total_qty {
            return Err(PositionError::AvailableExceedsTotal);
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]
    use super::*;

    fn p(raw: i64) -> Price {
        Price::new_checked(raw, 10).unwrap()
    }

    // Bar 构造校验：OHLC 关系与成交量
    #[test]
    fn bar_new_checked_rejects_bad_range() {
        assert!(Bar::new_checked(1, p(1000), p(1100), p(900), p(1050), Qty::from_raw(100)).is_ok());
        let r = Bar::new_checked(1, p(1000), p(900), p(1100), p(1050), Qty::from_raw(100));
        assert_eq!(r, Err(BarError::InvalidRange));
        let r = Bar::new_checked(1, p(1000), p(1100), p(900), p(1050), Qty::from_raw(-1));
        assert_eq!(r, Err(BarError::InvalidVolume));
        // 收盘高于最高价
        let r = Bar::new_checked(1, p(1000), p(1100), p(900), p(1200), Qty::from_raw(1));
        assert_eq!(r, Err(BarError::InvalidRange));
    }

    // Position 不变量：available ∈ [0, total]
    #[test]
    fn position_validate() {
        let ok = Position {
            symbol: "600519".to_string(),
            total_qty: 1000,
            available_qty: 0, // 当日买入全部冻结（T+1）
            avg_entry_price: Some(p(170_000)),
        };
        assert_eq!(ok.validate(), Ok(()));
        let bad = Position {
            symbol: "600519".to_string(),
            total_qty: 1000,
            available_qty: 1001,
            avg_entry_price: None,
        };
        assert_eq!(bad.validate(), Err(PositionError::AvailableExceedsTotal));
        let neg = Position {
            symbol: "600519".to_string(),
            total_qty: 1000,
            available_qty: -1,
            avg_entry_price: None,
        };
        assert_eq!(neg.validate(), Err(PositionError::NegativeAvailable));
    }
}
