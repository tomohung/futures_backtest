"""H080 ETL: 從 stock_day 計算月度成交金額前 20 排名 → top_lists 表。

清單用途：作為 build_concentration_index.py 中「上月套用本月」的清單來源。
注意：TAIEX 只含上市，故 WHERE market='TWSE'，排除 TPEX。

用法:
  uv run python src/etl/build_top_lists.py                # 全期重建（預設）
  uv run python src/etl/build_top_lists.py --start 2024-01 --end 2026-05
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"


DDL = """
CREATE TABLE IF NOT EXISTS top_lists (
    list_month     VARCHAR,
    rank           INT,
    symbol         VARCHAR,
    name           VARCHAR,
    monthly_value  BIGINT,
    PRIMARY KEY (list_month, rank)
);
"""

BUILD_SQL = """
INSERT OR REPLACE INTO top_lists
WITH monthly AS (
    SELECT
        strftime(trade_date, '%Y-%m')   AS list_month,
        symbol,
        ANY_VALUE(name)                  AS name,
        SUM(value)                       AS monthly_value
    FROM stock_day
    WHERE market = 'TWSE'
      AND strftime(trade_date, '%Y-%m') BETWEEN ? AND ?
    GROUP BY list_month, symbol
),
ranked AS (
    SELECT
        list_month, symbol, name, monthly_value,
        ROW_NUMBER() OVER (PARTITION BY list_month ORDER BY monthly_value DESC) AS rank
    FROM monthly
)
SELECT list_month, rank, symbol, name, monthly_value
FROM ranked
WHERE rank <= 20
ORDER BY list_month, rank;
"""


def build(start_month: str, end_month: str) -> None:
    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(DDL)
        conn.execute(BUILD_SQL, [start_month, end_month])
        n = conn.execute(
            "SELECT COUNT(*) FROM top_lists WHERE list_month BETWEEN ? AND ?",
            [start_month, end_month],
        ).fetchone()[0]
        print(f"top_lists: 寫入 {n} 筆 ({start_month} ~ {end_month})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2018-01", help="YYYY-MM")
    parser.add_argument("--end", default="2026-12", help="YYYY-MM")
    args = parser.parse_args()
    build(args.start, args.end)


if __name__ == "__main__":
    main()
