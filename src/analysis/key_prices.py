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

        # 前天 10點前 15分K 收盤（扣底值，08:45~09:59）
        bars_15m_pre10 = conn.execute("""
            WITH bars_15m AS (
                SELECT
                    time_bucket(INTERVAL '15 minutes', timestamp, TIMESTAMP '2000-01-01 08:45:00') AS ts,
                    arg_max(close, timestamp)::INT AS close
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::DATE = ?
                  AND timestamp::TIME BETWEEN '08:45:00' AND '09:59:00'
                GROUP BY ts
            )
            SELECT MAX(close), MIN(close), ROUND(AVG(close))::INT
            FROM bars_15m
        """, [SYMBOL, prev_day]).fetchone()

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
        "bars_15m_pre10": bars_15m_pre10,
    }


def print_report(data):
    d = data
    ld = d["last_day"]
    pd_ = d["prev_day"]
    night = d["night"]
    ma = d["ma30_20"]
    ref = night["close"] if night else None

    # ── helpers ──────────────────────────────────────────
    def n(v):
        return f"{v:,}" if v is not None else "—"

    def ud(price, benchmark):
        if price is None or benchmark is None:
            return "-"
        return "↑ up" if price > benchmark else "↓ down"

    # ── header ───────────────────────────────────────────
    ref_label = f"夜收 {ref:,}" if ref else "（無夜盤）"
    print(f"# 關鍵價格參考｜{ld}（昨）  基準：{ref_label}\n")

    # ── 昨日行情：日盤 vs 夜盤並排 ───────────────────────
    print("### 昨日行情")
    print(f"|      |    日盤 |    夜盤 |")
    print(f"|------|--------:|--------:|")
    print(f"| 高   | {n(d['day']['high'])} | {n(night['high'] if night else None)} |")
    print(f"| 低   | {n(d['day']['low'])}  | {n(night['low']  if night else None)} |")
    print(f"| 收盤 | {n(d['day']['close'])} | {n(night['close'] if night else None)} |")

    # ── 成本：昨 vs 前天並排 ─────────────────────────────
    vwap_last = d["vwap"].get(ld)
    vwap_prev = d["vwap"].get(pd_)
    big_last  = d["big_cost"].get(ld)
    big_prev  = d["big_cost"].get(pd_)

    print()
    print("### 成本")
    print(f"|               | 昨 {ld.strftime('%m/%d')} | 前天 {pd_.strftime('%m/%d')} |")
    print(f"|---------------|--------:|----------:|")
    print(f"| 平均成本 VWAP | {n(vwap_last)} | {n(vwap_prev)} |")
    print(f"| 大戶成本      | {n(big_last)}  | {n(big_prev)}  |")

    # ── 趨勢 ─────────────────────────────────────────────
    ma_dir = ud(ref, ma)
    pre10 = d.get("bars_15m_pre10")

    print()
    print("### 趨勢")
    print(f"| 項目              | 數值   | 備註 |")
    print(f"|-------------------|-------:|------|")
    ma_str = n(ma)
    print(f"| 30分K 20MA        | {ma_str} | 方向 {ma_dir}，夜收 {n(ref)} |")
    if pre10 and pre10[0] is not None:
        h, l, avg = pre10
        print(f"| 前天10點前扣底    | {n(h)} / {n(l)} | 均 {n(avg)}（{pd_.strftime('%m/%d')}） |")

    # ── 評估 ─────────────────────────────────────────────
    if ref is not None:
        if ref > d["day"]["high"]:
            two_day = f"新高（昨高 {n(d['day']['high'])}）"
        elif ref < d["day"]["low"]:
            two_day = f"新低（昨低 {n(d['day']['low'])}）"
        else:
            two_day = "-"
    else:
        two_day = "-"

    if ref is not None and ma is not None:
        dist_pct = abs(ref - ma) / ma * 100
        risk = "高" if dist_pct < 0.3 else ("中" if dist_pct < 1.5 else "低")
        reversal_risk = f"{risk}（距 {dist_pct:.1f}%）"
    else:
        reversal_risk = "-"

    print()
    print(f"### 評估")
    print(f"| 項目                      | 結果 |")
    print(f"|---------------------------|------|")
    print(f"| 夜收 vs 昨成本 {n(vwap_last)} | {ud(ref, vwap_last)} |")
    print(f"| 夜收 vs 前天成本 {n(vwap_prev)} | {ud(ref, vwap_prev)} |")
    print(f"| 二日高低突破              | {two_day} |")
    print(f"| 30分K 20MA 方向           | {ma_dir} |")
    print(f"| 均線轉向風險              | {reversal_risk} |")


if __name__ == "__main__":
    data = get_key_prices()
    print_report(data)
