//! Money：定点金额，内部单位 = 万分之一元（1e-4 CNY）。
//!
//! 依据：ARCHITECTURE §5.5（定点整数、唯一舍入实现）、CONSTRAINTS AC-01/AC-02。
//! 全部算术走 Result，无隐式溢出；workspace 两个 profile 都开启 overflow-checks 作最后防线。
//! Display 仅用于展示：截断到分，不影响账本内部值（内部精度保持到万分之一元）。

use core::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Default)]
pub struct Money(i64);

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MoneyError {
    Overflow,
    InvalidFormat(String),
}

impl Money {
    pub const ZERO: Money = Money(0);

    pub const fn from_raw(raw: i64) -> Self {
        Money(raw)
    }

    pub const fn raw(self) -> i64 {
        self.0
    }

    pub fn checked_add(self, rhs: Money) -> Result<Money, MoneyError> {
        self.0
            .checked_add(rhs.0)
            .map(Money)
            .ok_or(MoneyError::Overflow)
    }

    pub fn checked_sub(self, rhs: Money) -> Result<Money, MoneyError> {
        self.0
            .checked_sub(rhs.0)
            .map(Money)
            .ok_or(MoneyError::Overflow)
    }

    /// 按整数倍缩放（如费用分摊、份额换算）。
    pub fn scale(self, factor: i64) -> Result<Money, MoneyError> {
        (self.0 as i128)
            .checked_mul(factor as i128)
            .and_then(|v| i64::try_from(v).ok())
            .map(Money)
            .ok_or(MoneyError::Overflow)
    }

    pub fn is_negative(self) -> bool {
        self.0 < 0
    }

    /// 解析十进制元字符串（最多 4 位小数），如 `"31.41"`、`"-0.05"`、`"3"`。
    pub fn from_yuan_str(s: &str) -> Result<Money, MoneyError> {
        let t = s.trim();
        let (neg, body) = match t.strip_prefix('-') {
            Some(b) => (true, b),
            None => (false, t.strip_prefix('+').unwrap_or(t)),
        };
        let (int_part, frac_part) = match body.split_once('.') {
            Some((i, f)) => (i, f),
            None => (body, ""),
        };
        let bad = || MoneyError::InvalidFormat(s.to_string());
        if int_part.is_empty() && frac_part.is_empty() {
            return Err(bad());
        }
        if int_part.len() > 12 || frac_part.len() > 4 {
            return Err(bad());
        }
        if !int_part.bytes().all(|b| b.is_ascii_digit())
            || !frac_part.bytes().all(|b| b.is_ascii_digit())
        {
            return Err(bad());
        }
        let int_val: i64 = if int_part.is_empty() {
            0
        } else {
            int_part.parse().map_err(|_| bad())?
        };
        let mut frac_val = 0i64;
        for (i, b) in frac_part.bytes().enumerate() {
            frac_val += i64::from(b - b'0') * 10i64.pow(3 - i as u32);
        }
        let units = int_val
            .checked_mul(10_000)
            .and_then(|v| v.checked_add(frac_val))
            .ok_or(MoneyError::Overflow)?;
        if neg {
            units.checked_neg().map(Money).ok_or(MoneyError::Overflow)
        } else {
            Ok(Money(units))
        }
    }
}

impl fmt::Display for Money {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let sign = if self.0 < 0 { "-" } else { "" };
        let a = self.0.unsigned_abs();
        write!(f, "{}{}.{:02}", sign, a / 10_000, (a % 10_000) / 100)
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]
    use super::*;

    // TC-C1-01: 定点加减无漂移（TEST_PLAN §4.4）
    #[test]
    fn tc_c1_01_add_sub_chain_no_drift() {
        let a = Money::from_yuan_str("31.41").unwrap();
        let b = Money::from_yuan_str("5.65").unwrap();
        let c = Money::from_yuan_str("27.15").unwrap();
        let r = a.checked_add(b).unwrap().checked_sub(c).unwrap();
        assert_eq!(r, Money::from_yuan_str("9.91").unwrap());
        assert_eq!(r.raw(), 99_100);
    }

    // TC-C1-02: 溢出返回 Err，不中断进程（CONSTRAINTS AC-10/EN-03）
    #[test]
    fn tc_c1_02_overflow_returns_err() {
        let max = Money::from_raw(i64::MAX);
        assert_eq!(
            max.checked_add(Money::from_raw(1)),
            Err(MoneyError::Overflow)
        );
        let min = Money::from_raw(i64::MIN);
        assert_eq!(
            min.checked_sub(Money::from_raw(1)),
            Err(MoneyError::Overflow)
        );
        assert_eq!(
            Money::from_raw(i64::MAX).scale(2),
            Err(MoneyError::Overflow)
        );
    }

    // TC-C1-03: 元字符串解析与展示
    #[test]
    fn tc_c1_03_parse_and_display() {
        assert_eq!(Money::from_yuan_str("31.41").unwrap().raw(), 314_100);
        assert_eq!(Money::from_yuan_str("-0.05").unwrap().raw(), -500);
        assert_eq!(Money::from_yuan_str("3").unwrap().raw(), 30_000);
        assert_eq!(Money::from_yuan_str("0.0001").unwrap().raw(), 1);
        assert_eq!(Money::from_raw(314_100).to_string(), "31.41");
        assert_eq!(Money::from_raw(-500).to_string(), "-0.05");
        assert!(Money::from_yuan_str("1.00001").is_err());
        assert!(Money::from_yuan_str("abc").is_err());
        assert!(Money::from_yuan_str("").is_err());
    }
}
