//! 费用模型：回测与账本共用的费用估算（分项 + 合计）。
//!
//! 默认费率表来源：RISK_CONTROL §8 / TEST_PLAN §4.1。
//! 舍入规则（ARCHITECTURE §5.5）：佣金四舍五入到分；印花税/过户费/经手证管向上取整到分。

use crate::instrument::Side;
use crate::money::Money;
use crate::rounding::{ceil_cent_exact, ratio_parts, round_half_up_cent_exact};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FeeError {
    Overflow,
    InvalidNotional,
}

/// 费率以 (分子, 分母) 整数对表示，避免浮点（AC-01）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FeeSchedule {
    pub commission_num: i64,
    pub commission_den: i64,
    pub stamp_num: i64,
    pub stamp_den: i64,
    pub transfer_num: i64,
    pub transfer_den: i64,
    pub misc_num: i64,
    pub misc_den: i64,
    /// 单笔最低佣金
    pub min_commission: Money,
}

impl Default for FeeSchedule {
    /// 市场常见费率：佣金万 2.5（最低 5 元）、印花 0.05%（仅卖出）、
    /// 过户 0.001%、经手+证管 0.00541%。
    fn default() -> Self {
        FeeSchedule {
            commission_num: 25,
            commission_den: 100_000,
            stamp_num: 5,
            stamp_den: 10_000,
            transfer_num: 1,
            transfer_den: 100_000,
            misc_num: 541,
            misc_den: 10_000_000,
            min_commission: Money::from_raw(50_000), // 5.00 元
        }
    }
}

/// 费用分项（INV-A3：科目逐笔可查）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct FeeBreakdown {
    pub commission: Money,
    pub stamp: Money,
    pub transfer: Money,
    pub misc: Money,
}

impl FeeBreakdown {
    pub fn total(&self) -> Result<Money, MoneyError> {
        self.commission
            .checked_add(self.stamp)?
            .checked_add(self.transfer)?
            .checked_add(self.misc)
    }
}

use crate::money::MoneyError;

/// 按成交额估算单边费用。`notional` 必须非负。
pub fn estimate(notional: Money, side: Side, s: &FeeSchedule) -> Result<FeeBreakdown, FeeError> {
    let raw = notional.raw();
    if raw < 0 {
        return Err(FeeError::InvalidNotional);
    }
    let (qc, rc) = ratio_parts(raw, s.commission_num, s.commission_den);
    let commission_raw =
        round_half_up_cent_exact(qc, rc, i128::from(s.commission_den)).ok_or(FeeError::Overflow)?;
    let commission = Money::from_raw(commission_raw).max(s.min_commission);

    let stamp = match side {
        Side::Buy => Money::ZERO,
        Side::Sell => {
            let (q, r) = ratio_parts(raw, s.stamp_num, s.stamp_den);
            Money::from_raw(ceil_cent_exact(q, r).ok_or(FeeError::Overflow)?)
        }
    };

    let (qt, rt) = ratio_parts(raw, s.transfer_num, s.transfer_den);
    let transfer = Money::from_raw(ceil_cent_exact(qt, rt).ok_or(FeeError::Overflow)?);

    let (qm, rm) = ratio_parts(raw, s.misc_num, s.misc_den);
    let misc = Money::from_raw(ceil_cent_exact(qm, rm).ok_or(FeeError::Overflow)?);

    Ok(FeeBreakdown {
        commission,
        stamp,
        transfer,
        misc,
    })
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]
    use super::*;
    use crate::money::MoneyError;

    fn yuan(s: &str) -> Money {
        Money::from_yuan_str(s).unwrap()
    }

    fn assert_fees(
        fb: &FeeBreakdown,
        commission: &str,
        stamp: &str,
        transfer: &str,
        misc: &str,
        total: &str,
    ) {
        assert_eq!(fb.commission, yuan(commission), "commission");
        assert_eq!(fb.stamp, yuan(stamp), "stamp");
        assert_eq!(fb.transfer, yuan(transfer), "transfer");
        assert_eq!(fb.misc, yuan(misc), "misc");
        assert_eq!(fb.total().unwrap(), yuan(total), "total");
    }

    // TC-C7-01: 买入 10 万（TEST_PLAN §4.1）
    #[test]
    fn tc_c7_01_buy_100k() {
        let fb = estimate(yuan("100000"), Side::Buy, &FeeSchedule::default()).unwrap();
        assert_fees(&fb, "25.00", "0.00", "1.00", "5.41", "31.41");
    }

    // TC-C7-02: 卖出 10 万（印花税仅卖出侧）
    #[test]
    fn tc_c7_02_sell_100k() {
        let fb = estimate(yuan("100000"), Side::Sell, &FeeSchedule::default()).unwrap();
        assert_fees(&fb, "25.00", "50.00", "1.00", "5.41", "81.41");
    }

    // TC-C7-03: 买入 1 万（最低佣金 5 元 + misc 向上取整）
    #[test]
    fn tc_c7_03_buy_10k_min_commission() {
        let fb = estimate(yuan("10000"), Side::Buy, &FeeSchedule::default()).unwrap();
        assert_fees(&fb, "5.00", "0.00", "0.10", "0.55", "5.65");
    }

    // TC-C7-04: 卖出 33,333（四舍五入与向上取整混用不串规则）
    #[test]
    fn tc_c7_04_sell_33333() {
        let fb = estimate(yuan("33333"), Side::Sell, &FeeSchedule::default()).unwrap();
        assert_fees(&fb, "8.33", "16.67", "0.34", "1.81", "27.15");
    }

    // TC-C7-05: 买入 2 万，佣金恰为最低佣金等值（边界不重复不缺失）
    #[test]
    fn tc_c7_05_commission_exactly_min() {
        let fb = estimate(yuan("20000"), Side::Buy, &FeeSchedule::default()).unwrap();
        assert_eq!(fb.commission, yuan("5.00"));
    }

    // 负成交额拒绝
    #[test]
    fn negative_notional_rejected() {
        let n = yuan("100").checked_sub(yuan("101")).unwrap();
        assert_eq!(
            estimate(n, Side::Buy, &FeeSchedule::default()),
            Err(FeeError::InvalidNotional)
        );
    }

    // MoneyError 被 use 但仅用于 total 的错误类型——防止未用导入告警的显式消费
    #[test]
    fn total_overflow_type() {
        let big = Money::from_raw(i64::MAX);
        let fb = FeeBreakdown {
            commission: big,
            stamp: Money::from_raw(1),
            transfer: Money::ZERO,
            misc: Money::ZERO,
        };
        assert!(matches!(fb.total(), Err(MoneyError::Overflow)));
    }
}
