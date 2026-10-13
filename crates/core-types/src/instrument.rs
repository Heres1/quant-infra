//! Instrument：证券主档静态部分 + 申报数量规则 + 涨跌停价格规则。
//!
//! 规则依据：DEVELOPMENT_PLAN §2.3 参数表（含 2026-07 修订：主板 ST ±10%、
//! 盘后固定价格扩围）、TEST_PLAN §4.2/§4.3 用例。

use crate::price::{Price, PriceError};
use crate::qty::Qty;
use crate::rounding::mul_ratio_round_to_tick;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Board {
    Main,
    ChiNext,
    Star,
    Bse,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum LotRule {
    /// 100 股整数倍；卖出允许零股一次性申报
    Lot100,
    /// 科创板：200 股起，超出部分可 1 股递增；卖出不足 200 股一次性申报
    StarLot200,
    /// 北交所：100 股起，可 1 股递增
    BseLot100,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum PriceLimitType {
    Pct10,
    Pct20,
    Pct30,
}

impl PriceLimitType {
    fn upper_ratio(self) -> (i64, i64) {
        match self {
            PriceLimitType::Pct10 => (110, 100),
            PriceLimitType::Pct20 => (120, 100),
            PriceLimitType::Pct30 => (130, 100),
        }
    }

    fn lower_ratio(self) -> (i64, i64) {
        match self {
            PriceLimitType::Pct10 => (90, 100),
            PriceLimitType::Pct20 => (80, 100),
            PriceLimitType::Pct30 => (70, 100),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum AssetType {
    Stock,
    Etf,
    ConvertibleBond,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum InstrumentStatus {
    Listed,
    Suspended,
    Delisted,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Side {
    Buy,
    Sell,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Instrument {
    /// A 股代码，如 "600519"（M0 不含交易所后缀，接入多市场时再演进）
    pub symbol: String,
    pub board: Board,
    pub asset_type: AssetType,
    pub status: InstrumentStatus,
    /// 价格最小变动单位（毫单位）：股票 10（0.01 元）、基金 1（0.001 元）
    pub tick: i64,
    pub lot: LotRule,
    pub limit_type: PriceLimitType,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum QtyRuleError {
    /// 买入数量不符合手数规则
    NotLotMultiple,
    /// 低于板块最低申报数量（科创板 200 / 北交所 100）
    BelowMinimum,
    /// 卖出含零股但未标记一次性全部申报
    OddLotMustBeOneShot,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LimitError {
    Price(PriceError),
    Overflow,
}

impl Instrument {
    /// 板块默认（手数、涨跌停）规则（TC-C3-01）。
    pub fn defaults_for_board(board: Board) -> (LotRule, PriceLimitType) {
        match board {
            Board::Main => (LotRule::Lot100, PriceLimitType::Pct10),
            Board::ChiNext => (LotRule::Lot100, PriceLimitType::Pct20),
            Board::Star => (LotRule::StarLot200, PriceLimitType::Pct20),
            Board::Bse => (LotRule::BseLot100, PriceLimitType::Pct30),
        }
    }

    /// 申报数量静态校验（风控链 R2 的规则核心，RISK_CONTROL §3）。
    ///
    /// `is_odd_lot_close`：本次卖出是否为"零股一次性全部申报"。
    /// 是否确为全部持仓由调用方（账本可用量检查 R4）保证，本函数只做规则判定。
    pub fn check_qty(
        &self,
        qty: Qty,
        side: Side,
        is_odd_lot_close: bool,
    ) -> Result<(), QtyRuleError> {
        let q = qty.raw();
        match (self.lot, side) {
            (LotRule::Lot100, Side::Buy) => {
                if q % 100 == 0 {
                    Ok(())
                } else {
                    Err(QtyRuleError::NotLotMultiple)
                }
            }
            (LotRule::Lot100, Side::Sell) => {
                if q % 100 == 0 || is_odd_lot_close {
                    Ok(())
                } else {
                    Err(QtyRuleError::OddLotMustBeOneShot)
                }
            }
            (LotRule::StarLot200, Side::Buy) => {
                if q >= 200 {
                    Ok(())
                } else {
                    Err(QtyRuleError::BelowMinimum)
                }
            }
            (LotRule::StarLot200, Side::Sell) => {
                if q >= 200 || is_odd_lot_close {
                    Ok(())
                } else {
                    Err(QtyRuleError::OddLotMustBeOneShot)
                }
            }
            (LotRule::BseLot100, Side::Buy) => {
                if q >= 100 {
                    Ok(())
                } else {
                    Err(QtyRuleError::BelowMinimum)
                }
            }
            (LotRule::BseLot100, Side::Sell) => {
                if q >= 100 || is_odd_lot_close {
                    Ok(())
                } else {
                    Err(QtyRuleError::OddLotMustBeOneShot)
                }
            }
        }
    }

    /// 涨跌停价：昨收 × (1 ± 涨跌幅)，四舍五入至 tick（交易所口径，TEST_PLAN §4.2）。
    /// 前提：`prev_close` 已按本合约 tick 对齐（数据层质量门保证）。
    pub fn price_limit(&self, prev_close: Price) -> Result<(Price, Price), LimitError> {
        let (un, ud) = self.limit_type.upper_ratio();
        let (ln, ld) = self.limit_type.lower_ratio();
        let up = mul_ratio_round_to_tick(prev_close.raw(), un, ud, self.tick)
            .ok_or(LimitError::Overflow)?;
        let lo = mul_ratio_round_to_tick(prev_close.raw(), ln, ld, self.tick)
            .ok_or(LimitError::Overflow)?;
        Ok((Price::from_raw(up), Price::from_raw(lo)))
    }

    /// 价格是否在当日涨跌停区间内（含边界）。
    pub fn price_within_limit(&self, price: Price, prev_close: Price) -> Result<bool, LimitError> {
        let (up, lo) = self.price_limit(prev_close)?;
        Ok(price >= lo && price <= up)
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]
    use super::*;

    fn main_stock() -> Instrument {
        Instrument {
            symbol: "600519".to_string(),
            board: Board::Main,
            asset_type: AssetType::Stock,
            status: InstrumentStatus::Listed,
            tick: 10,
            lot: LotRule::Lot100,
            limit_type: PriceLimitType::Pct10,
        }
    }

    fn star_stock() -> Instrument {
        Instrument {
            symbol: "688001".to_string(),
            board: Board::Star,
            asset_type: AssetType::Stock,
            status: InstrumentStatus::Listed,
            tick: 10,
            lot: LotRule::StarLot200,
            limit_type: PriceLimitType::Pct20,
        }
    }

    fn bse_stock() -> Instrument {
        Instrument {
            symbol: "830001".to_string(),
            board: Board::Bse,
            asset_type: AssetType::Stock,
            status: InstrumentStatus::Listed,
            tick: 10,
            lot: LotRule::BseLot100,
            limit_type: PriceLimitType::Pct30,
        }
    }

    fn chi_next_stock() -> Instrument {
        Instrument {
            symbol: "300001".to_string(),
            board: Board::ChiNext,
            asset_type: AssetType::Stock,
            status: InstrumentStatus::Listed,
            tick: 10,
            lot: LotRule::Lot100,
            limit_type: PriceLimitType::Pct20,
        }
    }

    fn etf() -> Instrument {
        Instrument {
            symbol: "159915".to_string(),
            board: Board::ChiNext,
            asset_type: AssetType::Etf,
            status: InstrumentStatus::Listed,
            tick: 1,
            lot: LotRule::Lot100,
            limit_type: PriceLimitType::Pct20,
        }
    }

    // TC-C3-01: 板块默认规则
    #[test]
    fn tc_c3_01_board_defaults() {
        assert_eq!(
            Instrument::defaults_for_board(Board::Main),
            (LotRule::Lot100, PriceLimitType::Pct10)
        );
        assert_eq!(
            Instrument::defaults_for_board(Board::ChiNext),
            (LotRule::Lot100, PriceLimitType::Pct20)
        );
        assert_eq!(
            Instrument::defaults_for_board(Board::Star),
            (LotRule::StarLot200, PriceLimitType::Pct20)
        );
        assert_eq!(
            Instrument::defaults_for_board(Board::Bse),
            (LotRule::BseLot100, PriceLimitType::Pct30)
        );
    }

    // TC-C4-01/02: 主板 9.99 ±10% → 10.99 / 8.99（四舍五入口径）
    #[test]
    fn tc_c4_01_02_main_board_price_limit() {
        let inst = main_stock();
        let (up, lo) = inst.price_limit(Price::from_raw(9_990)).unwrap();
        assert_eq!(up, Price::from_raw(10_990)); // 10.99
        assert_eq!(lo, Price::from_raw(8_990)); // 8.99
    }

    // TC-C4-03: 创业板 20.05 ±20% → 24.06 / 16.04
    #[test]
    fn tc_c4_03_chi_next_price_limit() {
        let inst = chi_next_stock();
        let (up, lo) = inst.price_limit(Price::from_raw(20_050)).unwrap();
        assert_eq!(up, Price::from_raw(24_060));
        assert_eq!(lo, Price::from_raw(16_040));
    }

    // TC-C4-04: 主板 3.33 ±10% → 3.66 / 3.00（2.997 half-up 到 3.00）
    #[test]
    fn tc_c4_04_half_up_boundary() {
        let inst = main_stock();
        let (up, lo) = inst.price_limit(Price::from_raw(3_330)).unwrap();
        assert_eq!(up, Price::from_raw(3_660));
        assert_eq!(lo, Price::from_raw(3_000));
    }

    // TC-C4-05: ETF 1.234 +10%（tick 0.001）→ 1.357（非创业板 ETF 涨跌幅 ±10%）
    #[test]
    fn tc_c4_05_etf_tick_1() {
        let mut inst = etf();
        inst.limit_type = PriceLimitType::Pct10;
        let (up, _lo) = inst.price_limit(Price::from_raw(1_234)).unwrap();
        assert_eq!(up, Price::from_raw(1_357));
    }

    // TC-C4-06: ST 主板 5.55 ±10%（2026-07 新规）→ 6.11 / 5.00（精确半分进位）
    #[test]
    fn tc_c4_06_st_new_rule() {
        let inst = main_stock();
        let (up, lo) = inst.price_limit(Price::from_raw(5_550)).unwrap();
        assert_eq!(up, Price::from_raw(6_110));
        assert_eq!(lo, Price::from_raw(5_000));
    }

    // TC-C4-07: 主板申报数量（买 100 整数倍；卖零股须一次性）
    #[test]
    fn tc_c4_07_main_lot_rules() {
        let inst = main_stock();
        assert!(inst.check_qty(Qty::from_raw(100), Side::Buy, false).is_ok());
        assert_eq!(
            inst.check_qty(Qty::from_raw(150), Side::Buy, false),
            Err(QtyRuleError::NotLotMultiple)
        );
        // 卖出 1130 = 1000 + 130 零股，一次性全部申报 → 允许
        assert!(
            inst.check_qty(Qty::from_raw(1130), Side::Sell, true)
                .is_ok()
        );
        // 卖出零股但未标记一次性 → 拒绝
        assert_eq!(
            inst.check_qty(Qty::from_raw(130), Side::Sell, false),
            Err(QtyRuleError::OddLotMustBeOneShot)
        );
    }

    // TC-C4-08: 科创板（200 起可 1 股递增）
    #[test]
    fn tc_c4_08_star_qty_rules() {
        let inst = star_stock();
        assert_eq!(
            inst.check_qty(Qty::from_raw(199), Side::Buy, false),
            Err(QtyRuleError::BelowMinimum)
        );
        assert!(inst.check_qty(Qty::from_raw(200), Side::Buy, false).is_ok());
        assert!(inst.check_qty(Qty::from_raw(350), Side::Buy, false).is_ok());
        assert_eq!(
            inst.check_qty(Qty::from_raw(150), Side::Sell, false),
            Err(QtyRuleError::OddLotMustBeOneShot)
        );
        assert!(inst.check_qty(Qty::from_raw(150), Side::Sell, true).is_ok());
    }

    // TC-C4-09: 北交所（100 起可 1 股递增）
    #[test]
    fn tc_c4_09_bse_qty_rules() {
        let inst = bse_stock();
        assert_eq!(
            inst.check_qty(Qty::from_raw(99), Side::Buy, false),
            Err(QtyRuleError::BelowMinimum)
        );
        assert!(inst.check_qty(Qty::from_raw(100), Side::Buy, false).is_ok());
        assert!(inst.check_qty(Qty::from_raw(101), Side::Buy, false).is_ok());
    }

    // TC-C4-10: 创业板手数（100 整数倍）
    #[test]
    fn tc_c4_10_chi_next_lot_rules() {
        let inst = chi_next_stock();
        assert!(inst.check_qty(Qty::from_raw(100), Side::Buy, false).is_ok());
        assert_eq!(
            inst.check_qty(Qty::from_raw(101), Side::Buy, false),
            Err(QtyRuleError::NotLotMultiple)
        );
    }

    // 区间判断：边界价含在区间内
    #[test]
    fn price_within_limit_inclusive() {
        let inst = main_stock();
        let prev = Price::from_raw(9_990);
        assert!(
            inst.price_within_limit(Price::from_raw(10_990), prev)
                .unwrap()
        );
        assert!(
            inst.price_within_limit(Price::from_raw(8_990), prev)
                .unwrap()
        );
        assert!(
            !inst
                .price_within_limit(Price::from_raw(11_000), prev)
                .unwrap()
        );
    }
}
