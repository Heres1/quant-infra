//! Price：定点价格，内部单位 = 千分之一元（1e-3 CNY）。
//!
//! tick 语义：股票 10（0.01 元）、基金 1（0.001 元）。
//! 构造必须过 `new_checked`：正数且按 tick 对齐（交易所废单语义，RISK_CONTROL R2）。

use crate::Money;
use crate::qty::Qty;
use core::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Price(i64);

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PriceError {
    NotPositive,
    NotTickAligned,
    Overflow,
}

impl Price {
    pub const fn from_raw(raw: i64) -> Self {
        Price(raw)
    }

    pub const fn raw(self) -> i64 {
        self.0
    }

    pub fn new_checked(raw: i64, tick: i64) -> Result<Self, PriceError> {
        if raw <= 0 {
            return Err(PriceError::NotPositive);
        }
        if tick <= 0 || raw % tick != 0 {
            return Err(PriceError::NotTickAligned);
        }
        Ok(Price(raw))
    }

    /// 成交额 = 价格 × 数量，换算到 Money 单位（千分之一元 × 股 × 10）。
    pub fn mul_qty(self, qty: Qty) -> Result<Money, PriceError> {
        (self.0 as i128)
            .checked_mul(qty.raw() as i128)
            .and_then(|v| v.checked_mul(10))
            .and_then(|v| i64::try_from(v).ok())
            .map(Money::from_raw)
            .ok_or(PriceError::Overflow)
    }
}

impl fmt::Display for Price {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let sign = if self.0 < 0 { "-" } else { "" };
        let a = self.0.unsigned_abs();
        let mut s = format!("{}.{:03}", a / 1000, a % 1000);
        while s.ends_with('0') {
            s.pop();
        }
        if s.ends_with('.') {
            s.pop();
        }
        write!(f, "{sign}{s}")
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]
    use super::*;

    // TC-C2-01: tick 对齐校验（股票 tick=10 即 0.01 元）
    #[test]
    fn tc_c2_01_tick_alignment() {
        assert_eq!(
            Price::new_checked(1001, 10),
            Err(PriceError::NotTickAligned)
        );
        assert!(Price::new_checked(1000, 10).is_ok());
        assert_eq!(Price::new_checked(0, 10), Err(PriceError::NotPositive));
        assert_eq!(Price::new_checked(-1, 10), Err(PriceError::NotPositive));
        // 基金 tick=1：任意正毫单位都对齐
        assert!(Price::new_checked(1001, 1).is_ok());
    }

    // TC-C2-02: 展示（3 位小数去尾零）与成交额换算
    #[test]
    fn tc_c2_02_display_and_notional() {
        assert_eq!(Price::from_raw(1234).to_string(), "1.234");
        assert_eq!(Price::from_raw(10990).to_string(), "10.99");
        assert_eq!(Price::from_raw(3000).to_string(), "3");
        let notional = Price::from_raw(10990).mul_qty(Qty::new_checked(100).unwrap());
        assert_eq!(notional.unwrap().raw(), 10_990_000); // 10.99 元 × 100 股 = 1099 元
    }
}
