//! Qty：股数。订单数量必须为正；持仓数量允许 0。

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Default)]
pub struct Qty(i64);

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum QtyError {
    NotPositive,
    Overflow,
}

impl Qty {
    pub const fn from_raw(raw: i64) -> Self {
        Qty(raw)
    }

    /// 订单语义的正数数量。
    pub fn new_checked(raw: i64) -> Result<Self, QtyError> {
        if raw <= 0 {
            return Err(QtyError::NotPositive);
        }
        Ok(Qty(raw))
    }

    pub const fn raw(self) -> i64 {
        self.0
    }

    pub fn checked_add(self, rhs: Qty) -> Result<Qty, QtyError> {
        self.0.checked_add(rhs.0).map(Qty).ok_or(QtyError::Overflow)
    }

    pub fn checked_sub(self, rhs: Qty) -> Result<Qty, QtyError> {
        self.0.checked_sub(rhs.0).map(Qty).ok_or(QtyError::Overflow)
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]
    use super::*;

    #[test]
    fn qty_must_be_positive_for_orders() {
        assert_eq!(Qty::new_checked(0), Err(QtyError::NotPositive));
        assert!(Qty::new_checked(100).is_ok());
        let overflow = Qty::from_raw(i64::MAX).checked_add(Qty::from_raw(1));
        assert_eq!(overflow, Err(QtyError::Overflow));
    }
}
