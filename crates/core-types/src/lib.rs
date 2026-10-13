//! quant-infra 领域模型与定点数——全平台数值语义的唯一事实源。
//!
//! 规格：docs/MODULE_DESIGNS.md §1 · 约束：docs/CONSTRAINTS.md AC-01/AC-02。

pub mod fees;
pub mod instrument;
pub mod model;
pub mod money;
pub mod price;
pub mod qty;
pub mod rounding;

pub use fees::{FeeBreakdown, FeeError, FeeSchedule};
pub use instrument::{
    AssetType, Board, Instrument, InstrumentStatus, LimitError, LotRule, PriceLimitType,
    QtyRuleError, Side,
};
pub use model::{Bar, BarError, Fill, OrderIntent, OrderType, Position, PositionError};
pub use money::{Money, MoneyError};
pub use price::{Price, PriceError};
pub use qty::{Qty, QtyError};
