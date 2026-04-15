#!/usr/bin/env python3
"""
H062 Phase 1: S/R 支撐壓力有效性探索
對歷史每個交易日，用事前資料算 S/R，檢驗當日價格反應。
"""
import duckdb
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.signal import find_peaks
from scipy import stats

DB_PATH = Path(__file__).parents[3] / "data" / "futures.duckdb"
SYMBOL = "TX"
LOOKBACK_MONTHS = 6

# --- Parameters to explore ---
TOUCH_ZONE = 30        # S/R ± N 點算觸及
REACTION_BARS = 10     # 觸及後觀察 M 根 1分K
REACTION_THRESHOLD = 20  # 反轉超過 T 點算有效
N_RANDOM_TRIALS = 100  # 隨機對照組重複次數


def calc_sr_as_of(conn, as_of_date, lookback_days=30, bin_size=50,
                  swing_window=3, cluster_dist=100):
    """計算截至 as_of_date（不含）的 S/R，模擬事前視角。"""
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

    highs = np.array([r[0] for r in bars], dtype=float)
    lows = np.array([r[1] for r in bars], dtype=float)
    vols = np.array([r[2] for r in bars], dtype=float)
    n = len(bars)

    # Swing High/Low
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

    swing_high_clusters = cluster(swing_highs)
    swing_low_clusters = cluster(swing_lows)

    # Volume Profile HVN
    price_min = int(min(lows) // bin_size * bin_size)
    price_max = int(max(highs) // bin_size * bin_size + bin_size)
    bins = np.arange(price_min, price_max + bin_size, bin_size)
    vp = np.zeros(len(bins))

    for i in range(n):
        lo, hi, vol = lows[i], highs[i], vols[i]
        idx = [j for j, b in enumerate(bins) if b < hi and b + bin_size > lo]
        if idx:
            per = vol / len(idx)
            for j in idx:
                vp[j] += per

    peaks, props = find_peaks(vp, prominence=vp.max() * 0.1, distance=2)
    vp_levels = [int(bins[p] + bin_size / 2) for p in peaks]

    sr_levels = []
    for price, count in swing_high_clusters:
        sr_levels.append({"price": price, "type": "swing_high", "strength": count})
    for price, count in swing_low_clusters:
        sr_levels.append({"price": price, "type": "swing_low", "strength": count})
    for i, p in enumerate(peaks):
        sr_levels.append({
            "price": int(bins[p] + bin_size / 2),
            "type": "vp_hvn",
            "strength": float(props["prominences"][i]),
        })

    return sr_levels


def get_day_1m_bars(conn, trade_date):
    """取得某日日盤 1分K（08:46 ~ 13:45）。"""
    rows = conn.execute("""
        SELECT timestamp, open, high, low, close
        FROM ohlcv_1m
        WHERE symbol = ?
          AND timestamp::DATE = ?
          AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
        ORDER BY timestamp
    """, [SYMBOL, trade_date]).fetchall()
    if not rows:
        return None
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])


def check_touches(bars_df, sr_levels, touch_zone, reaction_bars, reaction_threshold):
    """檢查每個 S/R 是否被觸及，以及觸及後的反應。"""
    events = []
    closes = bars_df["close"].values
    highs = bars_df["high"].values
    lows = bars_df["low"].values
    n = len(bars_df)

    for sr in sr_levels:
        price = sr["price"]
        touched = False
        for i in range(n):
            if touched:
                break
            if lows[i] <= price + touch_zone and highs[i] >= price - touch_zone:
                touched = True
                entry_price = closes[i]
                is_from_below = closes[max(0, i - 1)] < price

                # 觀察後續 reaction_bars 根
                end_idx = min(i + reaction_bars, n - 1)
                if i >= n - 1:
                    continue

                future_closes = closes[i + 1:end_idx + 1]
                if len(future_closes) == 0:
                    continue

                if is_from_below:
                    max_reversal = entry_price - min(future_closes)
                    max_continuation = max(future_closes) - entry_price
                else:
                    max_reversal = max(future_closes) - entry_price
                    max_continuation = entry_price - min(future_closes)

                is_effective = max_reversal >= reaction_threshold

                events.append({
                    "sr_price": price,
                    "sr_type": sr["type"],
                    "sr_strength": sr["strength"],
                    "bar_idx": i,
                    "entry_price": entry_price,
                    "from_below": is_from_below,
                    "max_reversal": float(max_reversal),
                    "max_continuation": float(max_continuation),
                    "is_effective": is_effective,
                })
    return events


def generate_random_levels(day_low, day_high, n_levels):
    """在當日價格範圍內隨機產生 n_levels 個價位。"""
    return np.random.randint(int(day_low), int(day_high) + 1, size=n_levels).tolist()


def main():
    rng = np.random.default_rng(42)

    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        # 取得近 N 個月的交易日
        trading_days = conn.execute("""
            SELECT DISTINCT timestamp::DATE AS td
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
              AND timestamp::DATE >= CURRENT_DATE - ? * INTERVAL '1 month'
            ORDER BY td
        """, [SYMBOL, LOOKBACK_MONTHS]).fetchall()
        trading_days = [r[0] for r in trading_days]

        print(f"分析期間: {trading_days[0]} ~ {trading_days[-1]} ({len(trading_days)} 天)")

        all_sr_events = []
        all_random_events = []
        days_with_sr = 0
        total_sr_levels = 0

        for td in trading_days:
            sr_levels = calc_sr_as_of(conn, td)
            if sr_levels is None:
                continue

            bars_df = get_day_1m_bars(conn, td)
            if bars_df is None or len(bars_df) < 30:
                continue

            days_with_sr += 1
            total_sr_levels += len(sr_levels)

            # 只保留當日價格範圍內 ± 200 點的 S/R
            day_low = bars_df["low"].min()
            day_high = bars_df["high"].max()
            margin = 200
            relevant_sr = [
                sr for sr in sr_levels
                if day_low - margin <= sr["price"] <= day_high + margin
            ]

            sr_events = check_touches(
                bars_df, relevant_sr, TOUCH_ZONE, REACTION_BARS, REACTION_THRESHOLD
            )
            for e in sr_events:
                e["trade_date"] = td
            all_sr_events.extend(sr_events)

            # 隨機對照組
            if relevant_sr:
                n_random = len(relevant_sr)
                for _ in range(N_RANDOM_TRIALS):
                    rand_prices = rng.integers(
                        int(day_low - margin), int(day_high + margin) + 1,
                        size=n_random
                    ).tolist()
                    rand_levels = [
                        {"price": p, "type": "random", "strength": 0}
                        for p in rand_prices
                    ]
                    rand_events = check_touches(
                        bars_df, rand_levels, TOUCH_ZONE, REACTION_BARS,
                        REACTION_THRESHOLD
                    )
                    for e in rand_events:
                        e["trade_date"] = td
                    all_random_events.extend(rand_events)

    # --- 分析結果 ---
    print(f"\n{'='*60}")
    print(f"S/R 有效性分析")
    print(f"{'='*60}")
    print(f"交易日數: {days_with_sr}")
    print(f"平均每日 S/R 數: {total_sr_levels / days_with_sr:.1f}")

    sr_df = pd.DataFrame(all_sr_events)
    rand_df = pd.DataFrame(all_random_events)

    if sr_df.empty:
        print("\n沒有觸及事件，無法分析。")
        return

    print(f"\nS/R 觸及事件: {len(sr_df)}")
    print(f"隨機觸及事件: {len(rand_df)} (×{N_RANDOM_TRIALS} trials)")

    # 整體命中率
    sr_hit_rate = sr_df["is_effective"].mean()
    rand_hit_rate = rand_df["is_effective"].mean() if not rand_df.empty else 0

    print(f"\n--- 整體命中率 ---")
    print(f"S/R 命中率:  {sr_hit_rate:.1%} (N={len(sr_df)})")
    print(f"隨機命中率:  {rand_hit_rate:.1%} (N={len(rand_df)})")

    # 統計檢定
    if not rand_df.empty:
        contingency = [
            [sr_df["is_effective"].sum(), (~sr_df["is_effective"]).sum()],
            [rand_df["is_effective"].sum(), (~rand_df["is_effective"]).sum()],
        ]
        chi2, p_value, _, _ = stats.chi2_contingency(contingency)
        print(f"Chi-squared: {chi2:.2f}, p-value: {p_value:.4f}")
        print(f"{'*** 顯著 ***' if p_value < 0.05 else '不顯著'}")

    # 平均反彈幅度
    sr_reversal = sr_df["max_reversal"].mean()
    rand_reversal = rand_df["max_reversal"].mean() if not rand_df.empty else 0
    print(f"\n--- 平均最大反彈幅度 ---")
    print(f"S/R:  {sr_reversal:.1f} 點 (N={len(sr_df)})")
    print(f"隨機: {rand_reversal:.1f} 點 (N={len(rand_df)})")

    if not rand_df.empty:
        t_stat, t_p = stats.ttest_ind(
            sr_df["max_reversal"], rand_df["max_reversal"], equal_var=False
        )
        print(f"t-test: t={t_stat:.2f}, p={t_p:.4f}")

    # 按 S/R 類型分析
    print(f"\n--- 按 S/R 類型 ---")
    for sr_type in ["swing_high", "swing_low", "vp_hvn"]:
        subset = sr_df[sr_df["sr_type"] == sr_type]
        if subset.empty:
            continue
        hit = subset["is_effective"].mean()
        rev = subset["max_reversal"].mean()
        print(f"{sr_type:12s}: 命中率={hit:.1%}, 平均反彈={rev:.1f}點 (N={len(subset)})")

    # 按 strength 分組（swing 類型）
    swing_df = sr_df[sr_df["sr_type"].isin(["swing_high", "swing_low"])]
    if not swing_df.empty:
        print(f"\n--- Swing S/R 按 strength 分組 ---")
        swing_df = swing_df.copy()
        swing_df["strength_group"] = pd.cut(
            swing_df["sr_strength"], bins=[0, 1, 2, 3, 100],
            labels=["1", "2", "3", "4+"]
        )
        for grp, sub in swing_df.groupby("strength_group", observed=True):
            if sub.empty:
                continue
            hit = sub["is_effective"].mean()
            rev = sub["max_reversal"].mean()
            print(f"  strength={grp}: 命中率={hit:.1%}, 平均反彈={rev:.1f}點 (N={len(sub)})")

    # 反彈 vs 續行比
    print(f"\n--- 反彈 vs 續行 ---")
    sr_ratio = sr_df["max_reversal"].mean() / max(sr_df["max_continuation"].mean(), 0.01)
    rand_ratio = rand_df["max_reversal"].mean() / max(rand_df["max_continuation"].mean(), 0.01) if not rand_df.empty else 0
    print(f"S/R  反彈/續行比: {sr_ratio:.2f}")
    print(f"隨機 反彈/續行比: {rand_ratio:.2f}")

    # 每日彙總
    print(f"\n--- 每日觸及統計 ---")
    daily = sr_df.groupby("trade_date").agg(
        touches=("is_effective", "count"),
        hits=("is_effective", "sum"),
        avg_reversal=("max_reversal", "mean"),
    )
    daily["hit_rate"] = daily["hits"] / daily["touches"]
    print(f"每日平均觸及數: {daily['touches'].mean():.1f}")
    print(f"每日命中率中位數: {daily['hit_rate'].median():.1%}")
    print(f"每日命中率 std: {daily['hit_rate'].std():.1%}")


if __name__ == "__main__":
    main()
