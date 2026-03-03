#!/usr/bin/env python3
"""
產生日盤/夜盤關鍵價格參考表

使用方式：
    uv run python src/analysis/key_prices.py
"""
import duckdb
from datetime import timedelta
from pathlib import Path

DB_PATH = Path(__file__).parents[2] / "data" / "futures.duckdb"
SYMBOL = "TX"


def get_key_prices():
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        # 最新有日盤資料的交易日（= 昨天）
        last_day = conn.execute("""
            SELECT MAX(timestamp::DATE)
            FROM ohlcv_1m
            WHERE symbol = ?
        """, [SYMBOL]).fetchone()[0]

        # 日盤：昨高 / 昨低 / 收盤（from ohlcv_1m）
        day = conn.execute("""
            SELECT
                MAX(high)::INT,
                MIN(low)::INT,
                arg_max(close, timestamp)::INT
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::DATE = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
        """, [SYMBOL, last_day]).fetchone()

        # 夜盤：last_day 15:00 ~ (last_day+1) 05:00（from ticks，跨日，主力合約）
        next_day = last_day + timedelta(days=1)
        night = conn.execute("""
            WITH night_ticks AS (
                SELECT
                    contract,
                    price,
                    (trade_date::VARCHAR || ' ' || trade_time::VARCHAR)::TIMESTAMP AS ts
                FROM ticks
                WHERE symbol = ?
                  AND (
                    (trade_date = ? AND trade_time >= '15:00:00')
                    OR
                    (trade_date = ? AND trade_time <= '05:00:00')
                  )
            ),
            dominant AS (
                SELECT contract
                FROM night_ticks
                GROUP BY contract
                ORDER BY COUNT(*) DESC
                LIMIT 1
            )
            SELECT
                MAX(price)::INT,
                MIN(price)::INT,
                arg_max(price, ts)::INT
            FROM night_ticks
            WHERE contract = (SELECT contract FROM dominant)
        """, [SYMBOL, last_day, next_day]).fetchone()

        # 30分K 20MA（所有日盤，bucket 對齊 08:45）
        ma_row = conn.execute("""
            WITH bars_30m AS (
                SELECT
                    time_bucket(
                        INTERVAL '30 minutes',
                        timestamp,
                        TIMESTAMP '2000-01-01 08:45:00'
                    ) AS ts,
                    arg_max(close, timestamp) AS close
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:44:59'
                GROUP BY ts
            ),
            ma_calc AS (
                SELECT
                    ts,
                    AVG(close) OVER (
                        ORDER BY ts
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) AS ma20,
                    COUNT(*) OVER (
                        ORDER BY ts
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) AS window_size
                FROM bars_30m
            ),
            with_lag AS (
                SELECT
                    ts,
                    ma20,
                    window_size,
                    LAG(ma20) OVER (ORDER BY ts) AS prev_ma20
                FROM ma_calc
            )
            SELECT
                ROUND(ma20)::INT AS ma20,
                ma20 > prev_ma20 AS is_up
            FROM with_lag
            WHERE window_size = 20
            ORDER BY ts DESC
            LIMIT 1
        """, [SYMBOL]).fetchone()

    return {
        "last_day": last_day,
        "day": {"high": day[0], "low": day[1], "close": day[2]},
        "night": {"high": night[0], "low": night[1], "close": night[2]},
        "ma30_20": ma_row[0] if ma_row else None,
        "ma30_20_up": ma_row[1] if ma_row else None,
    }


def _print_table(rows):
    print(f"  {'項目':<12} {'價格':>8}  備註")
    print("  " + "-" * 34)
    for item, price, note in rows:
        price_str = f"{price:>8}" if price is not None else f"{'N/A':>8}"
        print(f"  {item:<12} {price_str}  {note}")


def print_report(data):
    d = data
    direction = "↑" if d["ma30_20_up"] else "↓"

    print(f"\n參考日期：{d['last_day']}（昨）")

    print("\n## 夜盤關鍵價格")
    _print_table([
        ("昨高", d["night"]["high"], ""),
        ("昨低", d["night"]["low"], ""),
        ("收盤", d["night"]["close"], ""),
    ])

    print("\n## 日盤關鍵價格")
    _print_table([
        ("昨高", d["day"]["high"], ""),
        ("昨低", d["day"]["low"], ""),
        ("收盤", d["day"]["close"], ""),
        ("30分K 20MA", d["ma30_20"], f"當前方向：{direction}"),
    ])
    print()


if __name__ == "__main__":
    data = get_key_prices()
    print_report(data)
