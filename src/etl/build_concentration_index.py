"""H080 ETL: stock_day + market_breadth + top_lists → concentration_index 寬表。

對每個交易日 t，套用 list_month = strftime(t - INTERVAL 1 MONTH, '%Y-%m')
的 top 20 排名，分別計算 N=1/5/10/20 的成交金額佔比與 20 日平滑指標。

用法:
  uv run python src/etl/build_concentration_index.py
  uv run python src/etl/build_concentration_index.py --start 2018-01-02 --end 2026-12-31
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"

N_VALUES = [1, 5, 10, 20]


def _ddl_columns() -> str:
    cols = []
    for n in N_VALUES:
        cols.append(f"top{n}_value BIGINT, top{n}_share DECIMAL(8,4)")
    for n in N_VALUES:
        cols.append(
            f"top{n}_ma20 DECIMAL(8,4), top{n}_std20 DECIMAL(8,4), "
            f"top{n}_dev_pct DECIMAL(8,4), top{n}_zscore DECIMAL(8,4)"
        )
    return ",\n    ".join(cols)


DDL = f"""
DROP TABLE IF EXISTS concentration_index;
CREATE TABLE concentration_index (
    trade_date    DATE PRIMARY KEY,
    list_month    VARCHAR,
    total_value   BIGINT,
    {_ddl_columns()},
    list_changed  BOOLEAN
);
"""


STAGE1_SQL = """
INSERT INTO concentration_index (
    trade_date, list_month, total_value,
    top1_value, top1_share, top5_value, top5_share,
    top10_value, top10_share, top20_value, top20_share, list_changed
)
WITH days AS (
    SELECT DISTINCT trade_date,
           strftime(trade_date - INTERVAL 1 MONTH, '%Y-%m') AS list_month
    FROM stock_day
    WHERE trade_date BETWEEN ? AND ?
),
day_value AS (
    SELECT d.trade_date, d.list_month,
           tl.symbol, tl.rank, sd.value
    FROM days d
    JOIN top_lists tl ON tl.list_month = d.list_month
    LEFT JOIN stock_day sd ON sd.trade_date = d.trade_date AND sd.symbol = tl.symbol
),
agg AS (
    SELECT trade_date, list_month,
           SUM(CASE WHEN rank <= 1  THEN COALESCE(value,0) END) AS top1_value,
           SUM(CASE WHEN rank <= 5  THEN COALESCE(value,0) END) AS top5_value,
           SUM(CASE WHEN rank <= 10 THEN COALESCE(value,0) END) AS top10_value,
           SUM(CASE WHEN rank <= 20 THEN COALESCE(value,0) END) AS top20_value
    FROM day_value
    GROUP BY trade_date, list_month
),
mb AS (
    SELECT trade_date, SUM(total_value) AS total_value
    FROM market_breadth
    WHERE market = 'TWSE'
      AND trade_date BETWEEN ? AND ?
    GROUP BY trade_date
)
SELECT a.trade_date, a.list_month, mb.total_value,
       a.top1_value,  CAST(a.top1_value  * 100.0 / NULLIF(mb.total_value,0) AS DECIMAL(8,4)),
       a.top5_value,  CAST(a.top5_value  * 100.0 / NULLIF(mb.total_value,0) AS DECIMAL(8,4)),
       a.top10_value, CAST(a.top10_value * 100.0 / NULLIF(mb.total_value,0) AS DECIMAL(8,4)),
       a.top20_value, CAST(a.top20_value * 100.0 / NULLIF(mb.total_value,0) AS DECIMAL(8,4)),
       FALSE
FROM agg a
JOIN mb ON mb.trade_date = a.trade_date
ORDER BY a.trade_date;
"""


def _stage2_sql() -> str:
    parts = []
    for n in N_VALUES:
        parts.append(f"""
UPDATE concentration_index AS ci SET
    top{n}_ma20    = m.ma20,
    top{n}_std20   = m.std20,
    top{n}_dev_pct = CASE WHEN m.ma20 IS NULL OR m.ma20 = 0 THEN NULL
                          ELSE (ci.top{n}_share - m.ma20) * 100.0 / m.ma20 END,
    top{n}_zscore  = CASE WHEN m.std20 IS NULL OR m.std20 = 0 THEN NULL
                          ELSE (ci.top{n}_share - m.ma20) / m.std20 END
FROM (
    SELECT trade_date,
           CASE WHEN ROW_NUMBER() OVER (ORDER BY trade_date) >= 20
                THEN AVG(top{n}_share) OVER w END AS ma20,
           CASE WHEN ROW_NUMBER() OVER (ORDER BY trade_date) >= 20
                THEN STDDEV(top{n}_share) OVER w END AS std20
    FROM concentration_index
    WINDOW w AS (ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
) m
WHERE m.trade_date = ci.trade_date;
""")
    return "\n".join(parts)


def _compute_list_changed(conn: duckdb.DuckDBPyConnection) -> None:
    """用 pandas 算每月清單與上月差異（top 20 symbol set），update 回 concentration_index。"""
    df = conn.execute(
        "SELECT list_month, symbol FROM top_lists WHERE rank <= 20 ORDER BY list_month"
    ).fetchdf()
    months = sorted(df["list_month"].unique())
    prev_set: set[str] = set()
    changed: dict[str, bool] = {}
    for m in months:
        cur = set(df.loc[df["list_month"] == m, "symbol"])
        changed[m] = bool(prev_set) and bool(cur - prev_set)
        prev_set = cur
    for m, c in changed.items():
        conn.execute(
            "UPDATE concentration_index SET list_changed = ? WHERE list_month = ?", [c, m]
        )


def build(start: date, end: date) -> None:
    with duckdb.connect(str(DB_PATH)) as conn:
        conn.execute(DDL)
        conn.execute(STAGE1_SQL, [start, end, start, end])
        conn.execute(_stage2_sql())
        _compute_list_changed(conn)
        n = conn.execute("SELECT COUNT(*) FROM concentration_index").fetchone()[0]
        print(f"concentration_index: 寫入 {n} 列")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2018-01-01", type=date.fromisoformat)
    parser.add_argument("--end", default="2026-12-31", type=date.fromisoformat)
    args = parser.parse_args()
    build(args.start, args.end)


if __name__ == "__main__":
    main()
