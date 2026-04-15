#!/usr/bin/env python3
"""
H063 Phase 1 v2: 修正隨機對照組樣本量 + 按時間框架調整反應參數
- 30分K: 5 bars 內反轉 50pt（2.5hr 內需要反轉 50 點才有意義）
- 1小時K: 3 bars 內反轉 80pt（3hr 內需要反轉 80 點）
- 1分K: 10 bars 內反轉 20pt（維持原本）
"""
import duckdb
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

DB_PATH = Path(__file__).parents[3] / "data" / "futures.duckdb"
SYMBOL = "TX"

TOUCH_PCT = 0.15          # 觸及 = 價格進入 MA ± 0.15%
PARAMS = {
    "30m": {"reaction_bars": 5, "reaction_pct": 0.25},   # 5 bars 內反轉 0.25%
    "1h":  {"reaction_bars": 3, "reaction_pct": 0.40},   # 3 bars 內反轉 0.40%
    "1m":  {"reaction_bars": 10, "reaction_pct": 0.10},  # 10 bars 內反轉 0.10%
}


def compute_ma(closes, period):
    ma = np.full(len(closes), np.nan)
    for i in range(period - 1, len(closes)):
        ma[i] = closes[i - period + 1:i + 1].mean()
    return ma


def check_ma_touches(highs, lows, closes, ma_values, valid_start,
                     touch_pct, reaction_bars, reaction_pct):
    events = []
    n = len(closes)
    last_touch_idx = -reaction_bars

    for i in range(valid_start, n):
        if np.isnan(ma_values[i]):
            continue
        if i - last_touch_idx < reaction_bars:
            continue

        ma_val = ma_values[i]
        touch_zone = ma_val * touch_pct / 100
        threshold = ma_val * reaction_pct / 100

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

            ma_rising = (not np.isnan(ma_values[max(0, i - 1)])
                         and ma_values[i] > ma_values[max(0, i - 1)])

            if price_above_ma:
                max_reversal = max(future) - entry_price
                max_continuation = entry_price - min(future)
            else:
                max_reversal = entry_price - min(future)
                max_continuation = max(future) - entry_price

            rev_pct = float(max_reversal) / entry_price * 100

            events.append({
                "bar_idx": i,
                "entry_price": float(entry_price),
                "price_above_ma": price_above_ma,
                "ma_rising": ma_rising,
                "max_reversal_pt": float(max_reversal),
                "max_reversal_pct": rev_pct,
                "is_effective": float(max_reversal) >= threshold,
            })
    return events


def build_random_baseline(highs, lows, closes, valid_start,
                          touch_pct, reaction_bars, reaction_pct,
                          n_trials, rng):
    """產生足夠大的隨機對照組，方法與 MA 完全對稱。"""
    events = []
    n = len(closes)
    price_min = float(np.nanmin(lows[valid_start:]))
    price_max = float(np.nanmax(highs[valid_start:]))

    for _ in range(n_trials):
        rand_level = rng.uniform(price_min, price_max)
        touch_zone = rand_level * touch_pct / 100
        threshold = rand_level * reaction_pct / 100
        last_touch = -reaction_bars
        for i in range(valid_start, n):
            if i - last_touch < reaction_bars:
                continue
            if lows[i] <= rand_level + touch_zone and highs[i] >= rand_level - touch_zone:
                last_touch = i
                entry_price = closes[i]
                price_above = closes[max(0, i - 1)] > rand_level

                end_idx = min(i + reaction_bars, n - 1)
                if i >= n - 1:
                    continue
                future = closes[i + 1:end_idx + 1]
                if len(future) == 0:
                    continue

                if price_above:
                    max_rev = max(future) - entry_price
                else:
                    max_rev = entry_price - min(future)

                rev_pct = float(max_rev) / entry_price * 100

                events.append({
                    "max_reversal_pct": rev_pct,
                    "is_effective": float(max_rev) >= threshold,
                })
    return events


def analyze_timeframe(label, all_events_by_ma, all_random, params):
    print(f"\n{'='*60}")
    print(f"時間框架: {label}")
    print(f"反應參數: {params['reaction_bars']} bars 內反轉 {params['reaction_pct']}%")
    print(f"{'='*60}")

    for ma_label, events in all_events_by_ma.items():
        df = pd.DataFrame(events)
        rdf = pd.DataFrame(all_random[ma_label])
        if df.empty:
            print(f"\n  {ma_label}: 無觸及事件")
            continue

        hit_rate = df["is_effective"].mean()
        rand_rate = rdf["is_effective"].mean() if not rdf.empty else 0
        avg_rev_pct = df["max_reversal_pct"].mean()
        rand_rev_pct = rdf["max_reversal_pct"].mean() if not rdf.empty else 0

        print(f"\n--- {ma_label} ---")
        print(f"{'':14s} {'命中率':>8s} {'平均反彈%':>9s} {'N':>6s}")
        print(f"{'均線':14s} {hit_rate:>7.1%} {avg_rev_pct:>8.3f}% {len(df):>6d}")
        print(f"{'隨機':14s} {rand_rate:>7.1%} {rand_rev_pct:>8.3f}% {len(rdf):>6d}")

        if not rdf.empty and len(df) > 0:
            cont = [
                [int(df["is_effective"].sum()), int((~df["is_effective"]).sum())],
                [int(rdf["is_effective"].sum()), int((~rdf["is_effective"]).sum())],
            ]
            if all(v > 0 for row in cont for v in row):
                chi2, p, _, _ = stats.chi2_contingency(cont)
                direction = "均線較好" if hit_rate > rand_rate else "均線較差"
                print(f"  χ² p={p:.4f} ({direction}) {'***' if p < 0.05 else ''}")

        if "ma_rising" in df.columns:
            print(f"\n  按均線方向:")
            for rising, sub in df.groupby("ma_rising"):
                d = "上升中" if rising else "下降中"
                print(f"    {d}: 命中率={sub['is_effective'].mean():.1%}, "
                      f"反彈={sub['max_reversal_pct'].mean():.3f}% (N={len(sub)})")

        if "price_above_ma" in df.columns:
            print(f"\n  按觸及方向:")
            for above, sub in df.groupby("price_above_ma"):
                d = "從上方碰（支撐）" if above else "從下方碰（壓力）"
                print(f"    {d}: 命中率={sub['is_effective'].mean():.1%}, "
                      f"反彈={sub['max_reversal_pct'].mean():.3f}% (N={len(sub)})")

        if "ma_rising" in df.columns and "price_above_ma" in df.columns:
            print(f"\n  交叉（順勢=上升中從上碰 / 下降中從下碰）:")
            df_c = df.copy()
            df_c["with_trend"] = (
                (df_c["ma_rising"] & df_c["price_above_ma"]) |
                (~df_c["ma_rising"] & ~df_c["price_above_ma"])
            )
            for wt, sub in df_c.groupby("with_trend"):
                d = "順勢" if wt else "逆勢"
                print(f"    {d}: 命中率={sub['is_effective'].mean():.1%}, "
                      f"反彈={sub['max_reversal_pct'].mean():.3f}% (N={len(sub)})")


def run_30m(conn, rng):
    params = PARAMS["30m"]
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

    highs = np.array([r[1] for r in bars])
    lows = np.array([r[2] for r in bars])
    closes = np.array([r[3] for r in bars])

    all_events = {}
    all_random = {}
    for period, label in [(21, "MA21"), (65, "MA65")]:
        ma = compute_ma(closes, period)
        all_events[label] = check_ma_touches(
            highs, lows, closes, ma, period,
            TOUCH_PCT, params["reaction_bars"], params["reaction_pct"]
        )
        all_random[label] = build_random_baseline(
            highs, lows, closes, period,
            TOUCH_PCT, params["reaction_bars"], params["reaction_pct"],
            n_trials=500, rng=rng
        )

    analyze_timeframe("日盤 30分K", all_events, all_random, params)


def run_1h(conn, rng):
    params = PARAMS["1h"]
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

    highs = np.array([r[1] for r in bars])
    lows = np.array([r[2] for r in bars])
    closes = np.array([r[3] for r in bars])

    all_events = {}
    all_random = {}
    for period, label in [(21, "MA21"), (65, "MA65")]:
        ma = compute_ma(closes, period)
        all_events[label] = check_ma_touches(
            highs, lows, closes, ma, period,
            TOUCH_PCT, params["reaction_bars"], params["reaction_pct"]
        )
        all_random[label] = build_random_baseline(
            highs, lows, closes, period,
            TOUCH_PCT, params["reaction_bars"], params["reaction_pct"],
            n_trials=500, rng=rng
        )

    analyze_timeframe("全日 1小時K", all_events, all_random, params)


def run_1m(conn, rng):
    params = PARAMS["1m"]
    trading_days = conn.execute("""
        SELECT DISTINCT timestamp::DATE AS td
        FROM ohlcv_1m
        WHERE symbol = ?
          AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
        ORDER BY td
    """, [SYMBOL]).fetchall()
    trading_days = [r[0] for r in trading_days]

    all_events = {"MA21": [], "MA65": []}
    all_random = {"MA21": [], "MA65": []}

    for td in trading_days:
        rows = conn.execute("""
            SELECT high::DOUBLE, low::DOUBLE, close::DOUBLE
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::DATE = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ORDER BY timestamp
        """, [SYMBOL, td]).fetchall()

        if not rows or len(rows) < 65:
            continue

        highs = np.array([r[0] for r in rows])
        lows = np.array([r[1] for r in rows])
        closes = np.array([r[2] for r in rows])

        for period, label in [(21, "MA21"), (65, "MA65")]:
            ma = compute_ma(closes, period)
            events = check_ma_touches(
                highs, lows, closes, ma, period,
                TOUCH_PCT, params["reaction_bars"], params["reaction_pct"]
            )
            all_events[label].extend(events)

            rand = build_random_baseline(
                highs, lows, closes, period,
                TOUCH_PCT, params["reaction_bars"], params["reaction_pct"],
                n_trials=5, rng=rng
            )
            all_random[label].extend(rand)

    analyze_timeframe("日內 1分K（每日獨立）", all_events, all_random, params)


def main():
    rng = np.random.default_rng(42)

    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        td_range = conn.execute("""
            SELECT MIN(timestamp::DATE), MAX(timestamp::DATE),
                   COUNT(DISTINCT timestamp::DATE)
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
        """, [SYMBOL]).fetchone()
        print(f"資料: {td_range[0]} ~ {td_range[1]} ({td_range[2]} 天)\n")

        run_30m(conn, rng)
        run_1h(conn, rng)
        run_1m(conn, rng)


if __name__ == "__main__":
    main()
