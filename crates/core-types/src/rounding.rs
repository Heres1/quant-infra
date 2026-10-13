//! 舍入规则唯一实现（CONSTRAINTS AC-02：全平台一切舍入只允许出自本文件）。
//!
//! 全整数运算；128 位中间量防止大额价格 × 比例溢出。
//! 涨跌停口径：交易所规则为四舍五入至最小变动单位（TEST_PLAN §4.2 修正记录）。

/// 万分之一元 → 分：四舍五入（half-up，四舍五入口径）。
pub fn round_half_up_to_cent(raw: i64) -> i64 {
    let q = raw / 100;
    let r = raw % 100;
    if r * 2 >= 100 { (q + 1) * 100 } else { q * 100 }
}

/// 万分之一元 → 分：向上取整。
pub fn ceil_to_cent(raw: i64) -> i64 {
    let q = raw / 100;
    let r = raw % 100;
    if r > 0 { (q + 1) * 100 } else { q * 100 }
}

/// 带余数的比例除法：(q, rem) 使 raw*num/den = q + rem/den，商向零截断。
/// 除数 den > 0。返回值用于精确舍入（先截断不丢精度，余数参与判定）。
pub fn ratio_parts(raw: i64, num: i64, den: i64) -> (i128, i128) {
    let n = i128::from(raw) * i128::from(num);
    (n / i128::from(den), n % i128::from(den))
}

/// 分（Money 单位=百分之一分母意义上的"到分"）四舍五入，余数参与 half-up 判定。
/// 即对 q + rem/den（单位：万分之一元）四舍五入到 cent，返回仍是万分之一元。
pub fn round_half_up_cent_exact(q: i128, rem: i128, den: i128) -> Option<i64> {
    let cq = q / 100;
    let cr = q % 100;
    let up = 2 * (cr * den + rem) >= 100 * den;
    let cents = if up { cq + 1 } else { cq };
    i64::try_from(cents * 100).ok()
}

/// 对 q + rem/den（万分之一元）向上取整到 cent。
pub fn ceil_cent_exact(q: i128, rem: i128) -> Option<i64> {
    let cq = q / 100;
    let cr = q % 100;
    let cents = if cr > 0 || rem > 0 { cq + 1 } else { cq };
    i64::try_from(cents * 100).ok()
}

/// prev*num/den（价格毫单位）四舍五入到 tick 整倍数，返回毫单位。
/// 交易所涨跌停价计算口径；TEST_PLAN §4.2 全部用例由本函数 + 费率整数推导验证。
pub fn mul_ratio_round_to_tick(prev: i64, num: i64, den: i64, tick: i64) -> Option<i64> {
    let n = i128::from(prev) * i128::from(num);
    let q = n / i128::from(den);
    let r = n % i128::from(den);
    let qt = q / i128::from(tick);
    let rt = q % i128::from(tick);
    let up = 2 * (rt * i128::from(den) + r) >= i128::from(tick) * i128::from(den);
    let ticks = if up { qt + 1 } else { qt };
    let out = ticks * i128::from(tick);
    i64::try_from(out).ok()
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]
    use super::*;

    // TC-C6-01: half-up 到分（边界 0.5 分进位）
    #[test]
    fn tc_c6_01_round_half_up_cent() {
        assert_eq!(round_half_up_to_cent(166_665), 166_700); // 16.6665 → 16.67
        assert_eq!(round_half_up_to_cent(83_332), 83_300); // 8.3332 → 8.33
        assert_eq!(round_half_up_to_cent(83_350), 83_400); // 8.3350 → 8.34（精确半分进位）
        assert_eq!(round_half_up_to_cent(25_000), 25_000); // 整分不动
    }

    // TC-C6-02: 向上取整到分
    #[test]
    fn tc_c6_02_ceil_cent() {
        assert_eq!(ceil_to_cent(5_410), 5_500); // 0.541 → 0.55
        assert_eq!(ceil_to_cent(1_000), 1_000); // 整分不动
        assert_eq!(ceil_to_cent(1), 100);
    }

    // TC-C6-03: 比例 + tick 四舍五入（涨跌停口径，TEST_PLAN §4.2）
    #[test]
    fn tc_c6_03_mul_ratio_round_tick() {
        // 主板 9.99 ±10% → 10.99 / 8.99
        assert_eq!(mul_ratio_round_to_tick(9_990, 110, 100, 10), Some(10_990));
        assert_eq!(mul_ratio_round_to_tick(9_990, 90, 100, 10), Some(8_990));
        // 创业板 20.05 ±20% → 24.06 / 16.04
        assert_eq!(mul_ratio_round_to_tick(20_050, 120, 100, 10), Some(24_060));
        assert_eq!(mul_ratio_round_to_tick(20_050, 80, 100, 10), Some(16_040));
        // 主板 3.33 ±10% → 3.66 / 3.00
        assert_eq!(mul_ratio_round_to_tick(3_330, 110, 100, 10), Some(3_660));
        assert_eq!(mul_ratio_round_to_tick(3_330, 90, 100, 10), Some(3_000));
        // ETF 1.234 +10%（tick 1）→ 1.357
        assert_eq!(mul_ratio_round_to_tick(1_234, 110, 100, 1), Some(1_357));
        // ST 主板 5.55 ±10% → 6.11 / 5.00（精确半分进位）
        assert_eq!(mul_ratio_round_to_tick(5_550, 110, 100, 10), Some(6_110));
        assert_eq!(mul_ratio_round_to_tick(5_550, 90, 100, 10), Some(5_000));
    }

    // TC-C6-04: 带余数精确舍入（费用计算路径）
    #[test]
    fn tc_c6_04_exact_with_remainder() {
        // 佣金 33,333 元（333,330,000 万分之一元）× 25/100,000 = 8.33325 → 8.33
        let (q, r) = ratio_parts(333_330_000, 25, 100_000);
        assert_eq!(round_half_up_cent_exact(q, r, 100_000), Some(83_300));
        // 印花 33,333 元 × 5/10,000 = 16.6665 → 16.67（ceil）
        let (q, r) = ratio_parts(333_330_000, 5, 10_000);
        assert_eq!(ceil_cent_exact(q, r), Some(166_700));
    }
}
