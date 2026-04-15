#!/usr/bin/env python3
"""
H063 Phase 1: 均線作為動態支撐壓力的有效性
三個時間框架：日盤30分K、全日1小時K、日內1分K
"""
import duckdb
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats
from collections import defaultdict

DB_PATH = Path(__file__).parents[3] / "data" / "futures.duckdb"
SYMBOL = "TX"

TOUCH_ZONE = 30
REACTION_BARS = 10
REACTION_THRESHOLD = 20
N_RANDOM = 20


def compute_ma(closes, period):
    """SMA，前 period-1 根為 NaN。"""
    ma = np.full(len(closes), np.nan)
    for i in range(period - 1, len(closes)):
        ma[i] = closes[i - period + 1:i + 1].mean()
    return ma


def check_ma_touches(highs, lows, closes, ma_values, valid_start,
                     touch_zone, reaction_bars, reaction_threshold):
    """檢查價格觸及均線的事件與反應。"""
    events = []
    n = len(closes)
    last_touch_idx = -reaction_bars  # 避免同一段反覆觸及

    for i in range(valid_start, n):
        if np.isnan(ma_values[i]):
            continue
        if i - last_touch_idx < reaction_bars:
            continue

        ma_val = ma_values[i]
        if lows[i] <= ma_val + touch_zone and highs[i] >= ma_val - touch_zone:
            last_touch_idx = i
            entry_price = closes[i]
            price_above_ma = closes[max(0, i - 1)] > ma_val

            end_idx = min(i + reaction_bars, n - 1)
            if i >= n - 1:
                continue
            future = closes[i + 1:end_idx + 1]
            if len(future) == 0:
                continue

            # 均線方向
            ma_rising = (not np.isnan(ma_values[max(0, i - 1)])
                         and ma_values[i] > ma_values[max(0, i - 1)])

            if price_above_ma:
                # 從上方碰到 = 支撐測試，期待反彈向上
                max_reversal = max(future) - entry_price
                max_continuation = entry_price - min(future)
            else:
                # 從下方碰到 = 壓力測試，期待反彈向下
                max_reversal = entry_price - min(future)
                max_continuation = max(future) - entry_price

            events.append({
                "bar_idx": i,
                "ma_val": float(ma_val),
                "entry_price": float(entry_price),
                "price_above_ma": price_above_ma,
                "ma_rising": ma_rising,
                "max_reversal": float(max_reversal),
                "max_continuation": float(max_continuation),
                "is_effective": float(max_reversal) >= reaction_threshold,
            })
    return events


def check_random_touches(highs, lows, closes, n_levels, valid_start,
                         touch_zone, reaction_bars, reaction_threshold, rng):
    """隨機對照組。"""
    events = []
    n = len(closes)
    price_min = float(np.nanmin(lows[valid_start:]))
    price_max = float(np.nanmax(highs[valid_start:]))

    for _ in range(N_RANDOM):
        rand_prices = rng.uniform(price_min, price_max, size=n_levels)
        for rp in rand_prices:
            last_touch = -reaction_bars
            for i in range(valid_start, n):
                if i - last_touch < reaction_bars:
                    continue
                if lows[i] <= rp + touch_zone and highs[i] >= rp - touch_zone:
                    last_touch = i
                    entry_price = closes[i]
                    price_above = closes[max(0, i - 1)] > rp
                    end_idx = min(i + reaction_bars, n - 1)
                    if i >= n - 1:
                        break
                    future = closes[i + 1:end_idx + 1]
                    if len(future) == 0:
                        break
                    if price_above:
                        max_rev = max(future) - entry_price
                    else:
                        max_rev = entry_price - min(future)
                    events.append({
                        "max_reversal": float(max_rev),
                        "is_effective": float(max_rev) >= reaction_threshold,
                    })
                    break  # 每個隨機價位只取第一次觸及
    return events


def analyze_timeframe(label, all_events_by_ma, all_random):
    """彙整分析一個時間框架的結果。"""
    print(f"\n{'='*60}")
    print(f"時間框架: {label}")
    print(f"{'='*60}")

    for ma_label, events in all_events_by_ma.items():
        df = pd.DataFrame(events)
        rdf = pd.DataFrame(all_random[ma_label])
        if df.empty:
            print(f"\n  {ma_label}: 無觸及事件")
            continue

        hit_rate = df["is_effective"].mean()
        rand_rate = rdf["is_effective"].mean() if not rdf.empty else 0
        avg_rev = df["max_reversal"].mean()
        rand_rev = rdf["max_reversal"].mean() if not rdf.empty else 0

        print(f"\n--- {ma_label} ---")
        print(f"{'':14s} {'命中率':>8s} {'平均反彈':>8s} {'N':>6s}")
        print(f"{'均線':14s} {hit_rate:>7.1%} {avg_rev:>7.1f}pt {len(df):>6d}")
        print(f"{'隨機':14s} {rand_rate:>7.1%} {rand_rev:>7.1f}pt {len(rdf):>6d}")

        if not rdf.empty and len(df) > 0:
            cont = [
                [df["is_effective"].sum(), (~df["is_effective"]).sum()],
                [rdf["is_effective"].sum(), (~rdf["is_effective"]).sum()],
            ]
            if all(v > 0 for row in cont for v in row):
                chi2, p, _, _ = stats.chi2_contingency(cont)
                direction = "均線較好" if hit_rate > rand_rate else "均線較差"
                print(f"  χ² p={p:.4f} ({direction}) {'***' if p < 0.05 else ''}")
            else:
                print(f"  χ² 無法計算（某 cell 為 0）")

        # 按均線方向分組
        if "ma_rising" in df.columns:
            print(f"\n  按均線方向:")
            for rising, sub in df.groupby("ma_rising"):
                label_dir = "上升中" if rising else "下降中"
                h = sub["is_effective"].mean()
                r = sub["max_reversal"].mean()
                print(f"    {label_dir}: 命中率={h:.1%}, 反彈={r:.1f}pt (N={len(sub)})")

        # 按 price_above_ma 分組
        if "price_above_ma" in df.columns:
            print(f"\n  按觸及方向:")
            for above, sub in df.groupby("price_above_ma"):
                label_dir = "從上方碰（支撐測試）" if above else "從下方碰（壓力測試）"
                h = sub["is_effective"].mean()
                r = sub["max_reversal"].mean()
                print(f"    {label_dir}: 命中率={h:.1%}, 反彈={r:.1f}pt (N={len(sub)})")

        # 均線方向 × 觸及方向 交叉
        if "ma_rising" in df.columns and "price_above_ma" in df.columns:
            print(f"\n  交叉分析（順勢觸及 = 上升中從上碰/下降中從下碰）:")
            df_copy = df.copy()
            df_copy["with_trend"] = (
                (df_copy["ma_rising"] & df_copy["price_above_ma"]) |
                (~df_copy["ma_rising"] & ~df_copy["price_above_ma"])
            )
            for wt, sub in df_copy.groupby("with_trend"):
                label_wt = "順勢觸及" if wt else "逆勢觸及"
                h = sub["is_effective"].mean()
                r = sub["max_reversal"].mean()
                print(f"    {label_wt}: 命中率={h:.1%}, 反彈={r:.1f}pt (N={len(sub)})")


def run_30m_day_session(conn, trading_days, rng):
    """日盤 30分K MA21/MA65。"""
    all_events = {"MA21": [], "MA65": []}
    all_random = {"MA21": [], "MA65": []}

    # 一次撈全部，再按日期序列排
    bars = conn.execute("""
        WITH bars_30m AS (
            SELECT
                CASE
                    WHEN time_bucket(INTERVAL '30 minutes', timestamp,
                         TIMESTAMP '2000-01-01 08:45:00')::TIME = '13:45:00'
                    THEN time_bucket(INTERVAL '30 minutes', timestamp,
                         TIMESTAMP '2000-01-01 08:45:00') - INTERVAL '30 minutes'
                    ELSE time_bucket(INTERVAL '30 minutes', timestamp,
                         TIMESTAMP '2000-01-01 08:45:00')
                END AS ts,
                MAX(high)::DOUBLE AS high,
                MIN(low)::DOUBLE AS low,
                LAST(close ORDER BY timestamp)::DOUBLE AS close
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            GROUP BY ts
        )
        SELECT ts, high, low, close FROM bars_30m ORDER BY ts
    """, [SYMBOL]).fetchall()

    if not bars:
        return

    highs = np.array([r[1] for r in bars])
    lows = np.array([r[2] for r in bars])
    closes = np.array([r[3] for r in bars])

    for period, label in [(21, "MA21"), (65, "MA65")]:
        ma = compute_ma(closes, period)
        events = check_ma_touches(
            highs, lows, closes, ma, period,
            TOUCH_ZONE, REACTION_BARS, REACTION_THRESHOLD
        )
        all_events[label] = events
        rand = check_random_touches(
            highs, lows, closes, 2, period,
            TOUCH_ZONE, REACTION_BARS, REACTION_THRESHOLD, rng
        )
        all_random[label] = rand

    analyze_timeframe("日盤 30分K", all_events, all_random)


def run_1h_full_session(conn, trading_days, rng):
    """全日（日盤+夜盤）1小時K MA21/MA65。"""
    all_events = {"MA21": [], "MA65": []}
    all_random = {"MA21": [], "MA65": []}

    bars = conn.execute("""
        WITH bars AS (
            SELECT
                time_bucket(INTERVAL '1 hour', timestamp) AS ts,
                MAX(high)::DOUBLE AS high,
                MIN(low)::DOUBLE AS low,
                LAST(close ORDER BY timestamp)::DOUBLE AS close
            FROM ohlcv_1m
            WHERE symbol = ?
              AND (timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
                   OR timestamp::TIME >= '15:00:00'
                   OR timestamp::TIME < '05:01:00')
            GROUP BY ts
            HAVING SUM(volume) > 0
        )
        SELECT ts, high, low, close FROM bars ORDER BY ts
    """, [SYMBOL]).fetchall()

    if not bars:
        return

    highs = np.array([r[1] for r in bars])
    lows = np.array([r[2] for r in bars])
    closes = np.array([r[3] for r in bars])

    for period, label in [(21, "MA21"), (65, "MA65")]:
        ma = compute_ma(closes, period)
        events = check_ma_touches(
            highs, lows, closes, ma, period,
            TOUCH_ZONE, REACTION_BARS, REACTION_THRESHOLD
        )
        all_events[label] = events
        rand = check_random_touches(
            highs, lows, closes, 2, period,
            TOUCH_ZONE, REACTION_BARS, REACTION_THRESHOLD, rng
        )
        all_random[label] = rand

    analyze_timeframe("全日 1小時K", all_events, all_random)


def run_intraday_1m(conn, trading_days, rng):
    """日內 1分K MA21/MA65，每日獨立計算。"""
    all_events = {"MA21": [], "MA65": []}
    all_random = {"MA21": [], "MA65": []}

    for td in trading_days:
        rows = conn.execute("""
            SELECT timestamp, high::DOUBLE, low::DOUBLE, close::DOUBLE
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::DATE = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ORDER BY timestamp
        """, [SYMBOL, td]).fetchall()

        if not rows or len(rows) < 65:
            continue

        highs = np.array([r[1] for r in rows])
        lows = np.array([r[2] for r in rows])
        closes = np.array([r[3] for r in rows])

        for period, label in [(21, "MA21"), (65, "MA65")]:
            ma = compute_ma(closes, period)
            # 從第 period 根開始才有效
            events = check_ma_touches(
                highs, lows, closes, ma, period,
                TOUCH_ZONE, REACTION_BARS, REACTION_THRESHOLD
            )
            for e in events:
                e["trade_date"] = td
            all_events[label].extend(events)

            rand = check_random_touches(
                highs, lows, closes, 2, period,
                TOUCH_ZONE, REACTION_BARS, REACTION_THRESHOLD, rng
            )
            all_random[label].extend(rand)

    analyze_timeframe("日內 1分K（每日獨立）", all_events, all_random)


def main():
    rng = np.random.default_rng(42)

    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        trading_days = conn.execute("""
            SELECT DISTINCT timestamp::DATE AS td
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ORDER BY td
        """, [SYMBOL]).fetchall()
        trading_days = [r[0] for r in trading_days]
        print(f"全部資料: {trading_days[0]} ~ {trading_days[-1]} ({len(trading_days)} 天)")

        run_30m_day_session(conn, trading_days, rng)
        run_1h_full_session(conn, trading_days, rng)
        run_intraday_1m(conn, trading_days, rng)


if __name__ == "__main__":
    main()
