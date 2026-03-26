"""
H031 補充：條件機率分析

1. 前一天 untouched → 今天各類機率
2. 連續 N 天 untouched 後的機率
3. 前一天 gap/EmaHL 大小 → 今天 untouched 機率
4. 如果用較小 fraction（0.9, 0.85, 0.8）的 SatZone，touch rate 如何變化

Usage:
    uv run python src/backtest/explore_h031_conditional.py
"""

import sys
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_for_orb_est_hl

DB_PATH = "data/futures.duckdb"


def classify_days(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    dates = sorted(df.index.normalize().unique())

    for d in dates:
        day = df[df.index.normalize() == d]
        if day.empty:
            continue

        ema_hl_vals = day["EmaHL"].dropna()
        ema_vol_vals = day["EmaVol"].dropna()
        if ema_hl_vals.empty or ema_vol_vals.empty:
            continue

        ema_hl = ema_hl_vals.iloc[0]
        ema_vol = ema_vol_vals.iloc[0]
        if ema_hl <= 0 or ema_vol <= 0:
            continue

        s_high = day["High"].max()
        s_low = day["Low"].min()
        actual_hl = s_high - s_low
        hl_ratio = actual_hl / ema_hl

        sat_u = day["SatZoneUpper"].dropna()
        sat_l = day["SatZoneLower"].dropna()
        sat_upper_max = sat_u.max() if not sat_u.empty else np.nan
        sat_lower_min = sat_l.min() if not sat_l.empty else np.nan

        if np.isnan(sat_upper_max) or np.isnan(sat_lower_min):
            continue

        upper_exceeded = s_high - sat_upper_max
        lower_exceeded = sat_lower_min - s_low
        max_exceed = max(upper_exceeded, lower_exceeded)

        if max_exceed > 100:
            cat = "breakout"
        elif s_high < sat_upper_max and s_low > sat_lower_min:
            cat = "untouched"
        else:
            cat = "normal"

        gap = float(day["GapSize"].iloc[0]) if "GapSize" in day.columns and not pd.isna(day["GapSize"].iloc[0]) else np.nan

        # How close to SatZone (as fraction of EmaHL)
        upper_gap = sat_upper_max - s_high
        lower_gap = s_low - sat_lower_min
        nearest_gap = min(upper_gap, lower_gap)
        nearest_gap_ratio = nearest_gap / ema_hl

        # Would it touch with a smaller fraction?
        fractions_touched = {}
        for frac in [1.0, 0.95, 0.90, 0.85, 0.80, 0.75]:
            offset = ema_hl / 8
            adj_upper = s_low + frac * ema_hl - offset  # approximate
            adj_lower = s_high - frac * ema_hl + offset
            touched = (s_high >= adj_upper) or (s_low <= adj_lower)
            fractions_touched[frac] = touched

        rows.append({
            "date": d.date() if hasattr(d, "date") else d,
            "category": cat,
            "hl_ratio": hl_ratio,
            "ema_hl": ema_hl,
            "gap_ratio": abs(gap) / ema_hl if not np.isnan(gap) else np.nan,
            "nearest_gap_ratio": nearest_gap_ratio,
            **{f"touch_{frac}": v for frac, v in fractions_touched.items()},
        })

    return pd.DataFrame(rows).set_index("date")


def main():
    print("載入資料...")
    df = load_data_for_orb_est_hl()
    df_analysis = df[df.index >= "2022-01-01"]

    print("分類交易日...")
    day_info = classify_days(df_analysis)
    all_dates = sorted(day_info.index)
    total = len(day_info)

    # === 1. Conditional probability: prev → today ===
    print(f"\n{'=' * 70}")
    print(f"  1. 條件機率：前一天 → 今天")
    print(f"{'=' * 70}")

    for prev_cat in ["untouched", "normal", "breakout"]:
        counts = {"untouched": 0, "normal": 0, "breakout": 0}
        n = 0
        for i in range(1, len(all_dates)):
            if day_info.at[all_dates[i-1], "category"] == prev_cat:
                today_cat = day_info.at[all_dates[i], "category"]
                counts[today_cat] += 1
                n += 1
        if n > 0:
            print(f"\n  前一天={prev_cat}（N={n}）→ 今天：")
            for cat in ["untouched", "normal", "breakout"]:
                print(f"    {cat:<12}: {counts[cat]:>4} ({counts[cat]/n*100:.1f}%)")

    # === 2. Consecutive untouched → next day ===
    print(f"\n{'=' * 70}")
    print(f"  2. 連續 N 天 untouched 後 → 第 N+1 天")
    print(f"{'=' * 70}")

    for streak_len in [1, 2, 3, 4, 5]:
        counts = {"untouched": 0, "normal": 0, "breakout": 0}
        n = 0
        for i in range(streak_len, len(all_dates)):
            # Check if previous streak_len days are all untouched
            all_ut = all(day_info.at[all_dates[i-j-1], "category"] == "untouched"
                        for j in range(streak_len))
            if all_ut:
                today_cat = day_info.at[all_dates[i], "category"]
                counts[today_cat] += 1
                n += 1
        if n > 0:
            ut_pct = counts["untouched"] / n * 100
            print(f"  連續 {streak_len} 天 untouched 後（N={n}）→ "
                  f"untouched: {ut_pct:.1f}%  "
                  f"normal: {counts['normal']/n*100:.1f}%  "
                  f"breakout: {counts['breakout']/n*100:.1f}%")

    # === 3. Gap size → untouched probability ===
    print(f"\n{'=' * 70}")
    print(f"  3. 開盤跳空大小 → untouched 機率")
    print(f"{'=' * 70}")

    valid = day_info[day_info["gap_ratio"].notna()]
    gap_bins = [0, 0.2, 0.4, 0.6, 0.8, 1.0, 999]
    gap_labels = ["<0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0", ">1.0"]
    valid_copy = valid.copy()
    valid_copy["gap_bin"] = pd.cut(valid_copy["gap_ratio"], bins=gap_bins, labels=gap_labels)

    print(f"  {'Gap/EmaHL':<12} {'N':>5} {'untouched':>12} {'normal':>10} {'breakout':>10}")
    print(f"  {'-' * 52}")
    for lbl in gap_labels:
        grp = valid_copy[valid_copy["gap_bin"] == lbl]
        n = len(grp)
        if n == 0:
            continue
        ut = (grp["category"] == "untouched").sum()
        nm = (grp["category"] == "normal").sum()
        bk = (grp["category"] == "breakout").sum()
        print(f"  {lbl:<12} {n:>5} {ut/n*100:>11.1f}% {nm/n*100:>9.1f}% {bk/n*100:>9.1f}%")

    # === 4. Smaller SatZone fraction → touch rate ===
    print(f"\n{'=' * 70}")
    print(f"  4. SatZone fraction 調降 → touch rate 變化")
    print(f"{'=' * 70}")

    print(f"\n  使用 fraction × EmaHL 作為 SatZone 目標距離：")
    print(f"  {'Fraction':<10} {'Touch Rate':>12} {'Untouched':>12} {'Change':>10}")
    print(f"  {'-' * 48}")

    base_touch = day_info["touch_1.0"].sum()
    for frac in [1.0, 0.95, 0.90, 0.85, 0.80, 0.75]:
        col = f"touch_{frac}"
        touched = day_info[col].sum()
        touch_rate = touched / total * 100
        ut_rate = (1 - touched / total) * 100
        change = touched - base_touch
        print(f"  {frac:<10.2f} {touch_rate:>11.1f}% {ut_rate:>11.1f}% {change:>+10}")

    # === 5. Conditional fraction: after untouched, what fraction needed? ===
    print(f"\n{'=' * 70}")
    print(f"  5. 前一天 untouched 時，今天用不同 fraction 的 touch rate")
    print(f"{'=' * 70}")

    for prev_cat in ["untouched", "normal", "breakout"]:
        indices = []
        for i in range(1, len(all_dates)):
            if day_info.at[all_dates[i-1], "category"] == prev_cat:
                indices.append(all_dates[i])
        sub = day_info.loc[indices]
        n = len(sub)
        if n == 0:
            continue

        print(f"\n  前一天={prev_cat}（N={n}）：")
        print(f"  {'Fraction':<10} {'Touch Rate':>12}")
        print(f"  {'-' * 24}")
        for frac in [1.0, 0.95, 0.90, 0.85, 0.80]:
            col = f"touch_{frac}"
            touched = sub[col].sum()
            print(f"  {frac:<10.2f} {touched/n*100:>11.1f}%")


if __name__ == "__main__":
    main()
