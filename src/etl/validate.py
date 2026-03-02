"""
Step 4: 驗證資料正確性

1. ohlcv_1m 基本統計
2. 隨機抽一天，比對 tick 和 1分K 的 OHLCV 是否一致
3. 換倉日前後 adj_close 連續性檢查
"""

import random
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"


def check_basic_stats(conn: duckdb.DuckDBPyConnection) -> None:
    row = conn.execute("""
        SELECT
            MIN(d)           AS min_date,
            MAX(d)           AS max_date,
            SUM(daily_bars)  AS total_bars,
            COUNT(*)         AS trading_days,
            AVG(daily_vol)   AS avg_daily_vol
        FROM (
            SELECT
                timestamp::date  AS d,
                COUNT(*)         AS daily_bars,
                SUM(volume)      AS daily_vol
            FROM ohlcv_1m WHERE symbol = 'TX'
            GROUP BY d
        ) t
    """).fetchone()

    print("=== ohlcv_1m 基本統計 ===")
    print(f"日期範圍：{row[0]} ~ {row[1]}")
    print(f"總 bar 數：{row[2]:,}")
    print(f"交易日數：{row[3]}")
    print(f"每日平均成交量：{row[4]:.0f}")


def check_tick_vs_1m(conn: duckdb.DuckDBPyConnection) -> None:
    # 隨機抽一個有 tick 且有 1m 資料的日期
    dates = conn.execute("""
        SELECT DISTINCT t.trade_date
        FROM ticks t
        JOIN (SELECT DISTINCT timestamp::date AS d FROM ohlcv_1m WHERE symbol='TX') o
          ON t.trade_date = o.d
        WHERE t.symbol = 'TX'
    """).fetchall()

    if not dates:
        print("\n（無可比對的日期）")
        return

    sample_date = random.choice(dates)[0]
    print(f"\n=== tick vs 1分K 比對（抽樣日：{sample_date}）===")

    # 查出當日 ohlcv_1m 使用的主力合約
    contract_row = conn.execute("""
        SELECT contract FROM ohlcv_1m
        WHERE symbol = 'TX' AND timestamp::date = ?
        LIMIT 1
    """, [sample_date]).fetchone()
    if not contract_row:
        print("ohlcv_1m 無當日資料")
        return
    dominant_contract = contract_row[0]
    print(f"主力合約：{dominant_contract}")

    # tick 角度的每分鐘統計（限主力合約）
    tick_agg = conn.execute("""
        SELECT
            DATE_TRUNC('minute', (trade_date::VARCHAR || ' ' || trade_time::VARCHAR)::TIMESTAMP) AS ts,
            FIRST(price ORDER BY trade_time)  AS open,
            MAX(price)                        AS high,
            MIN(price)                        AS low,
            LAST(price ORDER BY trade_time)   AS close,
            SUM(volume)                       AS volume,
            COUNT(*)                          AS tick_count
        FROM ticks
        WHERE symbol = 'TX'
          AND contract = ?
          AND trade_date = ?
          AND trade_time >= '08:45:00'
          AND trade_time <= '13:45:00'
        GROUP BY 1
        ORDER BY 1
    """, [dominant_contract, sample_date]).df()

    # ohlcv_1m 當日（只看有成交的分鐘）
    ohlcv = conn.execute("""
        SELECT timestamp AS ts, open, high, low, close, volume, tick_count
        FROM ohlcv_1m
        WHERE symbol = 'TX'
          AND timestamp::date = ?
          AND tick_count > 0
        ORDER BY timestamp
    """, [sample_date]).df()

    if tick_agg.empty or ohlcv.empty:
        print("資料不足，無法比對")
        return

    merged = tick_agg.merge(ohlcv, on="ts", suffixes=("_tick", "_1m"))
    mismatches = merged[
        (merged["open_tick"] != merged["open_1m"]) |
        (merged["high_tick"] != merged["high_1m"]) |
        (merged["low_tick"]  != merged["low_1m"])  |
        (merged["close_tick"] != merged["close_1m"]) |
        (merged["volume_tick"] != merged["volume_1m"])
    ]

    print(f"比對 {len(merged)} 根有成交的分鐘 K")
    if mismatches.empty:
        print("✓ 全部一致，無差異")
    else:
        print(f"✗ 發現 {len(mismatches)} 根不一致：")
        print(mismatches.to_string(index=False))


def check_adj_continuity(conn: duckdb.DuckDBPyConnection) -> None:
    print("\n=== 換倉日 adj_close 連續性 ===")

    result = conn.execute("""
        WITH spine AS (
            SELECT
                timestamp::date AS trade_date,
                MAX(adj_close) AS last_adj
            FROM ohlcv_1m
            WHERE symbol = 'TX'
            GROUP BY timestamp::date
        ),
        with_prev AS (
            SELECT
                trade_date,
                last_adj,
                LAG(last_adj) OVER (ORDER BY trade_date) AS prev_last_adj
            FROM spine
        )
        SELECT
            w.trade_date,
            ROUND(w.prev_last_adj, 2) AS prev_day_close,
            ROUND(w.last_adj, 2)      AS this_day_close,
            ROUND(w.last_adj - w.prev_last_adj, 2) AS gap,
            r.old_contract,
            r.new_contract
        FROM with_prev w
        JOIN rollover_log r ON w.trade_date = r.rollover_date AND r.symbol = 'TX'
        ORDER BY w.trade_date
    """).df()

    if result.empty:
        print("（無換倉記錄）")
        return

    large_gaps = result[result["gap"].abs() > 50]
    print(f"換倉次數：{len(result)}")
    if large_gaps.empty:
        print("✓ 所有換倉日 adj_close 跳空均 ≤ 50 點")
    else:
        print(f"⚠ 發現 {len(large_gaps)} 筆跳空 > 50 點：")
        print(large_gaps.to_string(index=False))

    print("\n換倉日摘要（全部）：")
    print(result[["trade_date", "prev_day_close", "this_day_close", "gap",
                  "old_contract", "new_contract"]].to_string(index=False))


def main() -> None:
    with duckdb.connect(str(DB_PATH)) as conn:
        check_basic_stats(conn)
        check_tick_vs_1m(conn)
        check_adj_continuity(conn)


if __name__ == "__main__":
    main()
