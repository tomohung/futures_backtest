"""H087 Step 0.2: 從 market_breadth / stock_day 算 6 個候選廣度指標。

輸出 results/breadth_indicators.csv：
  - breadth_adv_dec             漲家/跌家（TWSE+TPEX 合計）
  - breadth_adv_dec_cum         累積（漲家 - 跌家）— McClellan-style
  - new_highs_52w               收盤 ≥ 252 日最高的個股家數
  - new_lows_52w                收盤 ≤ 252 日最低的個股家數
  - new_high_low_diff           上面兩者差
  - value_concentration_top20   top 20 個股成交額 / 全市場
  - value_per_stock             全市場成交額 / 有成交家數
"""
from __future__ import annotations

import duckdb
from pathlib import Path

ROOT = Path(__file__).parent
DB = ROOT.parent.parent.parent / "data" / "futures.duckdb"
OUT = ROOT / "results" / "breadth_indicators.csv"

# 252 個交易日 ≈ 12 個月。窗口未滿 200 日的個股不算 new high/low（避免新股誤判）。
WIN = 252
MIN_N = 200


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(DB), read_only=True) as c:
        # 1. breadth_adv_dec + breadth_adv_dec_cum（兩市場合計）
        adv_dec = c.execute("""
            WITH agg AS (
                SELECT
                    trade_date,
                    SUM(up_count)   AS up_total,
                    SUM(down_count) AS down_total
                FROM market_breadth
                GROUP BY trade_date
            )
            SELECT
                trade_date,
                up_total::DOUBLE / NULLIF(down_total, 0)            AS breadth_adv_dec,
                SUM(up_total - down_total) OVER (ORDER BY trade_date) AS breadth_adv_dec_cum
            FROM agg
            ORDER BY trade_date
        """).df()
        print(f"  adv_dec rows: {len(adv_dec)}")

        # 2. new_highs / new_lows / diff — 個股 252 日 rolling extremes
        #    PARTITION BY (market, symbol) 確保每檔獨立計算
        highs_lows = c.execute(f"""
            WITH ext AS (
                SELECT
                    trade_date,
                    close,
                    MIN(close) OVER (
                        PARTITION BY market, symbol
                        ORDER BY trade_date
                        ROWS BETWEEN {WIN-1} PRECEDING AND CURRENT ROW
                    ) AS min_w,
                    MAX(close) OVER (
                        PARTITION BY market, symbol
                        ORDER BY trade_date
                        ROWS BETWEEN {WIN-1} PRECEDING AND CURRENT ROW
                    ) AS max_w,
                    COUNT(*) OVER (
                        PARTITION BY market, symbol
                        ORDER BY trade_date
                        ROWS BETWEEN {WIN-1} PRECEDING AND CURRENT ROW
                    ) AS n_w
                FROM stock_day
                WHERE close IS NOT NULL
            )
            SELECT
                trade_date,
                SUM(CASE WHEN close >= max_w AND n_w >= {MIN_N} THEN 1 ELSE 0 END) AS new_highs_52w,
                SUM(CASE WHEN close <= min_w AND n_w >= {MIN_N} THEN 1 ELSE 0 END) AS new_lows_52w
            FROM ext
            GROUP BY trade_date
            ORDER BY trade_date
        """).df()
        highs_lows["new_high_low_diff"] = highs_lows["new_highs_52w"] - highs_lows["new_lows_52w"]
        print(f"  highs_lows rows: {len(highs_lows)}")

        # 3. value_concentration_top20 + value_per_stock
        concentration = c.execute("""
            WITH ranked AS (
                SELECT
                    trade_date, value,
                    ROW_NUMBER() OVER (PARTITION BY trade_date ORDER BY value DESC) AS rk
                FROM stock_day WHERE value IS NOT NULL AND value > 0
            ),
            top20 AS (
                SELECT trade_date, SUM(value) AS top20_value
                FROM ranked WHERE rk <= 20
                GROUP BY trade_date
            ),
            total AS (
                SELECT trade_date, SUM(value) AS total_value, COUNT(*) AS active_stocks
                FROM stock_day WHERE value IS NOT NULL AND value > 0
                GROUP BY trade_date
            )
            SELECT
                t.trade_date,
                top20.top20_value::DOUBLE / NULLIF(t.total_value, 0) AS value_concentration_top20,
                t.total_value::DOUBLE / NULLIF(t.active_stocks, 0)   AS value_per_stock
            FROM total t JOIN top20 ON t.trade_date = top20.trade_date
            ORDER BY t.trade_date
        """).df()
        print(f"  concentration rows: {len(concentration)}")

    # Merge on trade_date
    df = adv_dec.merge(highs_lows, on="trade_date", how="outer") \
                .merge(concentration, on="trade_date", how="outer") \
                .sort_values("trade_date").reset_index(drop=True)

    df.to_csv(OUT, index=False)
    print(f"\nWrote {len(df)} rows → {OUT.relative_to(ROOT.parent.parent.parent)}")
    print("\nSummary:")
    print(df.describe().T[["count", "mean", "std", "min", "max"]].to_string())


if __name__ == "__main__":
    main()
