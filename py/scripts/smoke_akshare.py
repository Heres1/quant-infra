"""D1 冒烟脚本：akshare 拉取茅台日线（前复权），验证数据源连通性与字段形态。

运行：uv run python scripts/smoke_akshare.py
"""

import akshare as ak


def main() -> None:
    df = ak.stock_zh_a_hist(
        symbol="600519",
        period="daily",
        start_date="20240101",
        end_date="20261231",
        adjust="qfq",
    )
    print(f"rows={len(df)}")
    print(f"columns={list(df.columns)}")
    print(df.tail(10).to_string(index=False))


if __name__ == "__main__":
    main()
