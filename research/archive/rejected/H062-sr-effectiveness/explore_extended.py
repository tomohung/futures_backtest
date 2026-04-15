#!/usr/bin/env python3
"""
H062 延伸分析：
1. 拉長至全部可用資料（~2年+）
2. 比較 30分K S/R vs 日K S/R
3. 聚焦 strength 4+ 的排斥效應
"""
import duckdb
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.signal import find_peaks
from scipy import stats

DB_PATH = Path(__file__).parents[3] / "data" / "futures.duckdb"
SYMBOL = "TX"

TOUCH_ZONE = 30
REACTION_BARS = 10
REACTION_THRESHOLD = 20


def calc_sr_30m(conn, as_of_date, lookback_days=30, bin_size=50,
                swing_window=3, cluster_dist=100):
    """原版：30分K Swing + VP HVN。"""
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
                MAX(high)::INT AS high,
                MIN(low)::INT  AS low,
                SUM(volume)    AS volume
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
              AND timestamp::DATE < ?
              AND timestamp::DATE >= ? - ? * INTERVAL '1 day'
            GROUP BY ts
        )
        SELECT high, low, volume FROM bars_30m ORDER BY ts
    """, [SYMBOL, as_of_date, as_of_date, lookback_days]).fetchall()

    if len(bars) < 20:
        return None
    return _extract_swing_levels(bars, swing_window, cluster_dist)


def calc_sr_daily(conn, as_of_date, lookback_days=60, swing_window=3, cluster_dist=150):
    """日K 版本：用日盤 OHLC 算 Swing。lookback 拉長、cluster 距離加大。"""
    bars = conn.execute("""
        SELECT
            MAX(high)::INT AS high,
            MIN(low)::INT  AS low,
            SUM(volume)    AS volume
        FROM ohlcv_1m
        WHERE symbol = ?
          AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
          AND timestamp::DATE < ?
          AND timestamp::DATE >= ? - ? * INTERVAL '1 day'
        GROUP BY timestamp::DATE
        ORDER BY timestamp::DATE
    """, [SYMBOL, as_of_date, as_of_date, lookback_days]).fetchall()

    if len(bars) < 10:
        return None
    return _extract_swing_levels(bars, swing_window, cluster_dist)


def _extract_swing_levels(bars, swing_window, cluster_dist):
    highs = np.array([r[0] for r in bars], dtype=float)
    lows = np.array([r[1] for r in bars], dtype=float)
    n = len(bars)

    swing_highs, swing_lows = [], []
    for i in range(swing_window, n - swing_window):
        if highs[i] == max(highs[i - swing_window:i + swing_window + 1]):
            swing_highs.append(float(highs[i]))
        if lows[i] == min(lows[i - swing_window:i + swing_window + 1]):
            swing_lows.append(float(lows[i]))

    def cluster(levels):
        if not levels:
            return []
        levels = sorted(levels)
        groups = [[levels[0]]]
        for lv in levels[1:]:
            if lv - groups[-1][-1] <= cluster_dist:
                groups[-1].append(lv)
            else:
                groups.append([lv])
        return [(round(np.mean(g)), len(g)) for g in groups]

    sr_levels = []
    for price, count in cluster(swing_highs):
        sr_levels.append({"price": price, "type": "swing_high", "strength": count})
    for price, count in cluster(swing_lows):
        sr_levels.append({"price": price, "type": "swing_low", "strength": count})
    return sr_levels


def analyze_one_method(conn, trading_days, calc_fn, method_name):
    """對一種 S/R 算法跑完整分析。"""
    print(f"\n{'='*60}")
    print(f"方法: {method_name}")
    print(f"{'='*60}")

    all_touch_events = []
    all_repulsion = []
    all_range = []
    rng = np.random.default_rng(42)
    days_ok = 0

    for td in trading_days:
        sr_levels = calc_fn(conn, td)
        if sr_levels is None:
            continue

        rows = conn.execute("""
            SELECT timestamp, open, high, low, close
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::DATE = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ORDER BY timestamp
        """, [SYMBOL, td]).fetchall()
        if not rows or len(rows) < 30:
            continue

        days_ok += 1
        day_high = max(r[2] for r in rows)
        day_low = min(r[3] for r in rows)
        day_open = float(rows[0][1])
        closes = [float(r[4]) for r in rows]
        margin = 200

        relevant_sr = [
            sr for sr in sr_levels
            if day_low - margin <= sr["price"] <= day_high + margin
        ]

        # --- 觸及 + 反應分析 ---
        for sr in relevant_sr:
            p = sr["price"]
            min_dist = min(
                min(abs(float(r[2]) - p) for r in rows),
                min(abs(float(r[3]) - p) for r in rows),
            )
            touched = any(r[3] <= p + TOUCH_ZONE and r[2] >= p - TOUCH_ZONE for r in rows)
            approached = any(r[3] <= p + 100 and r[2] >= p - 100 for r in rows)

            all_repulsion.append({
                "strength": sr["strength"],
                "min_dist": float(min_dist),
                "touched": touched,
                "approached": approached,
            })

            # 觸及反應
            if touched:
                for i, r in enumerate(rows):
                    if r[3] <= p + TOUCH_ZONE and r[2] >= p - TOUCH_ZONE:
                        entry_price = float(r[4])
                        is_from_below = closes[max(0, i - 1)] < p
                        end_idx = min(i + REACTION_BARS, len(rows) - 1)
                        if i >= len(rows) - 1:
                            break
                        future = closes[i + 1:end_idx + 1]
                        if not future:
                            break
                        if is_from_below:
                            max_rev = entry_price - min(future)
                        else:
                            max_rev = max(future) - entry_price
                        all_touch_events.append({
                            "sr_type": sr["type"],
                            "strength": sr["strength"],
                            "max_reversal": float(max_rev),
                            "is_effective": float(max_rev) >= REACTION_THRESHOLD,
                        })
                        break

        # --- 隨機對照（觸及反應）---
        n_rand = len(relevant_sr) if relevant_sr else 3
        for _ in range(20):
            rand_prices = rng.integers(int(day_low - margin), int(day_high + margin) + 1, size=n_rand)
            for rp in rand_prices:
                rp = int(rp)
                for i, r in enumerate(rows):
                    if r[3] <= rp + TOUCH_ZONE and r[2] >= rp - TOUCH_ZONE:
                        entry_price = float(r[4])
                        is_from_below = closes[max(0, i - 1)] < rp
                        end_idx = min(i + REACTION_BARS, len(rows) - 1)
                        if i >= len(rows) - 1:
                            break
                        future = closes[i + 1:end_idx + 1]
                        if not future:
                            break
                        if is_from_below:
                            max_rev = entry_price - min(future)
                        else:
                            max_rev = max(future) - entry_price
                        all_touch_events.append({
                            "sr_type": "random",
                            "strength": 0,
                            "max_reversal": float(max_rev),
                            "is_effective": float(max_rev) >= REACTION_THRESHOLD,
                        })
                        break

        # --- 振幅框住分析 ---
        above = [sr["price"] for sr in relevant_sr if sr["price"] > day_open]
        below = [sr["price"] for sr in relevant_sr if sr["price"] < day_open]
        if above and below:
            nearest_res = min(above)
            nearest_sup = max(below)
            all_range.append({
                "actual_range": float(day_high - day_low),
                "sr_range": float(nearest_res - nearest_sup),
                "broke_res": float(day_high) > nearest_res,
                "broke_sup": float(day_low) < nearest_sup,
            })

    print(f"有效交易日: {days_ok}")

    # === 觸及反應 ===
    tdf = pd.DataFrame(all_touch_events)
    sr_mask = tdf["sr_type"] != "random"
    rand_mask = tdf["sr_type"] == "random"

    sr_hit = tdf[sr_mask]["is_effective"].mean()
    rand_hit = tdf[rand_mask]["is_effective"].mean()
    sr_rev = tdf[sr_mask]["max_reversal"].mean()
    rand_rev = tdf[rand_mask]["max_reversal"].mean()

    print(f"\n--- 觸及後反應 ---")
    print(f"{'':12s} {'命中率':>8s} {'平均反彈':>8s} {'N':>6s}")
    print(f"{'S/R':12s} {sr_hit:>7.1%} {sr_rev:>7.1f}pt {tdf[sr_mask].shape[0]:>6d}")
    print(f"{'隨機':12s} {rand_hit:>7.1%} {rand_rev:>7.1f}pt {tdf[rand_mask].shape[0]:>6d}")

    if tdf[sr_mask].shape[0] > 0 and tdf[rand_mask].shape[0] > 0:
        chi2, p, _, _ = stats.chi2_contingency([
            [tdf[sr_mask]["is_effective"].sum(), (~tdf[sr_mask]["is_effective"]).sum()],
            [tdf[rand_mask]["is_effective"].sum(), (~tdf[rand_mask]["is_effective"]).sum()],
        ])
        print(f"  χ² p={p:.4f} {'***' if p < 0.05 else ''}")

    # 按 strength
    print(f"\n--- 按 strength ---")
    sr_only = tdf[sr_mask].copy()
    sr_only["sg"] = pd.cut(sr_only["strength"], bins=[0, 1, 2, 3, 100], labels=["1", "2", "3", "4+"])
    for grp, sub in sr_only.groupby("sg", observed=True):
        if sub.empty:
            continue
        print(f"  str={grp}: 命中率={sub['is_effective'].mean():.1%}, "
              f"反彈={sub['max_reversal'].mean():.1f}pt (N={len(sub)})")

    # === 排斥效應 ===
    rdf = pd.DataFrame(all_repulsion)
    print(f"\n--- 排斥效應 ---")
    rdf["sg"] = pd.cut(rdf["strength"], bins=[0, 1, 2, 3, 100], labels=["1", "2", "3", "4+"])
    for grp, sub in rdf.groupby("sg", observed=True):
        n = len(sub)
        touch_rate = sub["touched"].mean()
        appr = sub[sub["approached"]]
        repulsion = (len(appr) - appr["touched"].sum()) / len(appr) if len(appr) > 0 else 0
        avg_dist = sub["min_dist"].mean()
        print(f"  str={grp}: 觸及率={touch_rate:.1%}, 排斥率={repulsion:.1%}, "
              f"avg_dist={avg_dist:.0f}pt (N={n})")

    corr, p = stats.spearmanr(rdf["strength"], rdf["touched"].astype(int))
    print(f"  Spearman(strength, touched): r={corr:.3f}, p={p:.4f}")

    # === 振幅框住 ===
    rgdf = pd.DataFrame(all_range)
    if not rgdf.empty:
        print(f"\n--- 振幅框住 ---")
        print(f"  交易日: {len(rgdf)}")
        print(f"  突破壓力: {rgdf['broke_res'].mean():.1%}")
        print(f"  跌破支撐: {rgdf['broke_sup'].mean():.1%}")
        both_held = ((~rgdf["broke_res"]) & (~rgdf["broke_sup"])).mean()
        print(f"  兩邊都沒破: {both_held:.1%}")
        print(f"  avg 日振幅: {rgdf['actual_range'].mean():.0f}pt, "
              f"avg S/R 間距: {rgdf['sr_range'].mean():.0f}pt")


def main():
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        # 全部可用交易日（留前 60 天給 lookback）
        all_days = conn.execute("""
            SELECT DISTINCT timestamp::DATE AS td
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ORDER BY td
        """, [SYMBOL]).fetchall()
        all_days = [r[0] for r in all_days]

        # 跳過前 60 天（日K lookback 需要）
        trading_days = all_days[60:]
        print(f"全部資料: {all_days[0]} ~ {all_days[-1]} ({len(all_days)} 天)")
        print(f"分析期間: {trading_days[0]} ~ {trading_days[-1]} ({len(trading_days)} 天)")

        # 方法 A: 原版 30分K
        analyze_one_method(
            conn, trading_days,
            lambda c, d: calc_sr_30m(c, d, lookback_days=30),
            "30分K Swing (30日 lookback, cluster_dist=100)"
        )

        # 方法 B: 日K
        analyze_one_method(
            conn, trading_days,
            lambda c, d: calc_sr_daily(c, d, lookback_days=60),
            "日K Swing (60日 lookback, cluster_dist=150)"
        )

        # 方法 C: 日K + 只看 strength ≥ 3
        def calc_sr_daily_strong(c, d):
            levels = calc_sr_daily(c, d, lookback_days=60)
            if levels is None:
                return None
            strong = [sr for sr in levels if sr["strength"] >= 3]
            return strong if strong else None

        analyze_one_method(
            conn, trading_days,
            calc_sr_daily_strong,
            "日K Swing (strength ≥ 3 only)"
        )


if __name__ == "__main__":
    main()
