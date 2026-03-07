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

        # 當日與前一日的成本（VWAP = sum(close*volume)/sum(volume)，日盤）
        prev_day = conn.execute("""
            SELECT MAX(timestamp::DATE)
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::DATE < ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
        """, [SYMBOL, last_day]).fetchone()[0]

        vwap_rows = conn.execute("""
            SELECT
                timestamp::DATE AS date,
                ROUND(SUM(close * volume) / SUM(volume))::INT AS vwap
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::DATE IN (?, ?)
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            GROUP BY date
            ORDER BY date DESC
        """, [SYMBOL, last_day, prev_day]).fetchall()

        vwap = {row[0]: row[1] for row in vwap_rows}

        # 大戶成本：1分K volume >= 20MA(volume) 的 bar 才計入，再算 VWAP
        big_rows = conn.execute("""
            WITH vol_ma AS (
                SELECT
                    timestamp::DATE AS date,
                    timestamp,
                    close,
                    volume,
                    AVG(volume) OVER (
                        PARTITION BY timestamp::DATE
                        ORDER BY timestamp
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) AS ma20_vol
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::DATE IN (?, ?)
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ),
            filtered AS (
                SELECT date, close, volume
                FROM vol_ma
                WHERE volume >= ma20_vol
            )
            SELECT
                date,
                ROUND(SUM(close * volume) / SUM(volume))::INT AS big_cost
            FROM filtered
            GROUP BY date
            ORDER BY date DESC
        """, [SYMBOL, last_day, prev_day]).fetchall()

        big_cost = {row[0]: row[1] for row in big_rows}

        # 30分K 20MA（所有日盤，bucket 對齊 08:45）
        # 13:45 這根 1分K（日盤真實收盤）合併進 13:15 的 bucket
        ma_row = conn.execute("""
            WITH bars_30m AS (
                SELECT
                    CASE
                        WHEN time_bucket(INTERVAL '30 minutes', timestamp, TIMESTAMP '2000-01-01 08:45:00')::TIME = '13:45:00'
                        THEN time_bucket(INTERVAL '30 minutes', timestamp, TIMESTAMP '2000-01-01 08:45:00') - INTERVAL '30 minutes'
                        ELSE time_bucket(INTERVAL '30 minutes', timestamp, TIMESTAMP '2000-01-01 08:45:00')
                    END AS ts,
                    arg_max(close, timestamp) AS close
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
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

    has_night = night and night[0] is not None
    return {
        "last_day": last_day,
        "prev_day": prev_day,
        "day": {"high": day[0], "low": day[1], "close": day[2]},
        "night": {"high": night[0], "low": night[1], "close": night[2]} if has_night else None,
        "vwap": vwap,
        "big_cost": big_cost,
        "ma30_20": ma_row[0] if ma_row else None,
        "ma30_20_up": ma_row[1] if ma_row else None,
    }


def print_report(data):
    d = data
    direction = "↑" if d["ma30_20_up"] else "↓"

    print(f"# 關鍵價格參考 {d['last_day']}（昨）\n")

    print("## 夜盤")
    print("| 項目 | 價格 |")
    print("|------|-----:|")
    if d["night"]:
        print(f"| 昨高 | {d['night']['high']:,} |")
        print(f"| 昨低 | {d['night']['low']:,} |")
        print(f"| 收盤 | {d['night']['close']:,} |")
    else:
        print("| （無夜盤資料） | — |")

    print()
    print("## 日盤")
    print("| 項目 | 價格 | 備註 |")
    print("|------|-----:|------|")
    print(f"| 昨高 | {d['day']['high']:,} | |")
    print(f"| 昨低 | {d['day']['low']:,} | |")
    print(f"| 收盤 | {d['day']['close']:,} | |")
    ma = d['ma30_20']
    ma_str = f"{ma:,}" if ma is not None else "N/A"
    print(f"| 30分K 20MA | {ma_str} | 當前方向：{direction} |")
    vwap_today = d['vwap'].get(d['last_day'])
    vwap_prev  = d['vwap'].get(d['prev_day'])
    vwap_today_str = f"{vwap_today:,}" if vwap_today else "N/A"
    vwap_prev_str  = f"{vwap_prev:,}"  if vwap_prev  else "N/A"
    print(f"| 平均成本 {d['last_day']} | {vwap_today_str} | VWAP |")
    print(f"| 平均成本 {d['prev_day']} | {vwap_prev_str} | VWAP |")
    big_today = d['big_cost'].get(d['last_day'])
    big_prev  = d['big_cost'].get(d['prev_day'])
    big_today_str = f"{big_today:,}" if big_today else "N/A"
    big_prev_str  = f"{big_prev:,}"  if big_prev  else "N/A"
    print(f"| 大戶成本 {d['last_day']} | {big_today_str} | vol≥20MA |")
    print(f"| 大戶成本 {d['prev_day']} | {big_prev_str} | vol≥20MA |")


if __name__ == "__main__":
    data = get_key_prices()
    print_report(data)
