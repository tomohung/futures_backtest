"""
H031 補充探索：Untouched 日特徵分析

已知（Phase 1）：
  - HL_ratio 中位數 0.72（actual_hl / ema_hl），振幅壓縮
  - Vol_ratio 正常（~0.94），量無異常
  - EstHL 無法預測

補充分析：
  1. Untouched 日的實際損益分佈（策略有進場的那些天）
  2. Untouched 日最終出場原因（SL / Dow trail / 13:30 force）
  3. 是否有 weekday / 前日特徵的集中

Usage:
    uv run python src/backtest/explore_h031_untouched.py
"""

import sys
from collections import Counter
from datetime import date, time, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.estimate_hl import compute_estimate_hl_zones
from src.backtest.runner import adjust_settlement_volume, load_data_for_orb_est_hl

DB_PATH = "data/futures.duckdb"


def classify_days(df: pd.DataFrame) -> pd.DataFrame:
    """Same classification as explore_h031_breakout.py."""
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
        day_vol = day["Volume"].sum()
        vol_ratio = day_vol / ema_vol

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

        # Additional features
        # Gap size
        gap = float(day["GapSize"].iloc[0]) if "GapSize" in day.columns and not pd.isna(day["GapSize"].iloc[0]) else np.nan

        # How close did price get to SatZone? (as fraction of EmaHL)
        upper_gap = sat_upper_max - s_high  # positive = didn't reach
        lower_gap = s_low - sat_lower_min   # positive = didn't reach
        nearest_gap = min(upper_gap, lower_gap)
        nearest_gap_ratio = nearest_gap / ema_hl

        rows.append({
            "date": d.date() if hasattr(d, "date") else d,
            "weekday": (d.date() if hasattr(d, "date") else d).weekday(),
            "ema_hl": ema_hl,
            "actual_hl": actual_hl,
            "hl_ratio": hl_ratio,
            "vol_ratio": vol_ratio,
            "category": cat,
            "gap_size": gap,
            "nearest_gap": nearest_gap,
            "nearest_gap_ratio": nearest_gap_ratio,
            "session_high": s_high,
            "session_low": s_low,
            "sat_upper_max": sat_upper_max,
            "sat_lower_min": sat_lower_min,
        })

    return pd.DataFrame(rows).set_index("date")


def analyze_untouched(day_info: pd.DataFrame):
    ut = day_info[day_info["category"] == "untouched"]
    nm = day_info[day_info["category"] == "normal"]
    bk = day_info[day_info["category"] == "breakout"]

    print(f"\n{'=' * 70}")
    print(f"  Untouched 日特徵分析（N={len(ut)}）")
    print(f"{'=' * 70}")

    # 1. HL ratio distribution
    print(f"\n  1. 振幅壓縮程度（HL_ratio = actual_hl / ema_hl）：")
    for label, grp in [("Untouched", ut), ("Normal", nm), ("Breakout", bk)]:
        arr = grp["hl_ratio"].values
        pcts = np.percentile(arr, [10, 25, 50, 75, 90])
        print(f"    {label:<12} N={len(arr):>4}  "
              f"P10={pcts[0]:.2f}  P25={pcts[1]:.2f}  P50={pcts[2]:.2f}  "
              f"P75={pcts[3]:.2f}  P90={pcts[4]:.2f}")

    # 2. How close to SatZone?
    print(f"\n  2. 最接近 SatZone 的距離（nearest_gap / EmaHL）：")
    arr = ut["nearest_gap_ratio"].values
    pcts = np.percentile(arr, [10, 25, 50, 75, 90])
    print(f"    中位數: {pcts[2]:.3f} × EmaHL")
    print(f"    P10/P25/P75/P90: {pcts[0]:.3f} / {pcts[1]:.3f} / {pcts[3]:.3f} / {pcts[4]:.3f}")

    # Bin by how close
    bins = [0, 0.05, 0.10, 0.15, 0.20, 0.30, 1.0]
    labels_b = ["<0.05", "0.05-0.10", "0.10-0.15", "0.15-0.20", "0.20-0.30", ">0.30"]
    ut_binned = pd.cut(ut["nearest_gap_ratio"], bins=bins, labels=labels_b)
    print(f"    距離分佈：")
    for lbl in labels_b:
        n = (ut_binned == lbl).sum()
        print(f"      {lbl:>10}: {n:>4} ({n/len(ut)*100:.1f}%)")

    # 3. Weekday distribution
    print(f"\n  3. 星期分佈：")
    weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for cat_label, grp in [("Untouched", ut), ("Normal", nm), ("Breakout", bk)]:
        wd_counts = grp["weekday"].value_counts().sort_index()
        total = len(grp)
        parts = []
        for wd in range(5):
            n = wd_counts.get(wd, 0)
            parts.append(f"{weekday_names[wd]}={n}({n/total*100:.0f}%)")
        print(f"    {cat_label:<12}: {' '.join(parts)}")

    # 4. Gap size
    print(f"\n  4. 開盤跳空（GapSize / EmaHL）：")
    for label, grp in [("Untouched", ut), ("Normal", nm), ("Breakout", bk)]:
        valid = grp[grp["gap_size"].notna()]
        if valid.empty:
            continue
        gap_ratio = (valid["gap_size"].abs() / valid["ema_hl"]).values
        pcts = np.percentile(gap_ratio, [25, 50, 75])
        print(f"    {label:<12} N={len(valid):>4}  "
              f"|Gap|/EmaHL P25={pcts[0]:.3f}  P50={pcts[1]:.3f}  P75={pcts[2]:.3f}")

    # 5. Previous day's HL ratio
    print(f"\n  5. 前一日 HL_ratio：")
    all_dates = sorted(day_info.index)
    date_to_idx = {d: i for i, d in enumerate(all_dates)}
    for label, grp in [("Untouched", ut), ("Normal", nm), ("Breakout", bk)]:
        prev_ratios = []
        for d in grp.index:
            idx = date_to_idx.get(d)
            if idx is not None and idx > 0:
                prev_d = all_dates[idx - 1]
                if prev_d in day_info.index:
                    prev_ratios.append(day_info.at[prev_d, "hl_ratio"])
        if prev_ratios:
            arr = np.array(prev_ratios)
            pcts = np.percentile(arr, [25, 50, 75])
            consec_low = (arr < 0.75).mean() * 100
            print(f"    {label:<12} N={len(arr):>4}  "
                  f"P25={pcts[0]:.2f}  P50={pcts[1]:.2f}  P75={pcts[2]:.2f}  "
                  f"prev<0.75: {consec_low:.1f}%")

    # 6. Consecutive untouched days
    print(f"\n  6. 連續 untouched 天數：")
    ut_dates = set(ut.index)
    streaks = []
    cur_streak = 0
    for d in all_dates:
        if d in ut_dates:
            cur_streak += 1
        else:
            if cur_streak > 0:
                streaks.append(cur_streak)
            cur_streak = 0
    if cur_streak > 0:
        streaks.append(cur_streak)
    if streaks:
        arr = np.array(streaks)
        print(f"    總共 {len(streaks)} 段連續 untouched")
        print(f"    1天: {(arr == 1).sum()}  2天: {(arr == 2).sum()}  "
              f"3天: {(arr == 3).sum()}  4+天: {(arr >= 4).sum()}")
        print(f"    最長連續: {arr.max()} 天")

    # 7. Year-by-year untouched rate
    print(f"\n  7. 逐年 untouched 比例：")
    day_info_copy = day_info.copy()
    day_info_copy["year"] = [d.year for d in day_info_copy.index]
    for yr, grp in day_info_copy.groupby("year"):
        total = len(grp)
        ut_n = (grp["category"] == "untouched").sum()
        nm_n = (grp["category"] == "normal").sum()
        bk_n = (grp["category"] == "breakout").sum()
        print(f"    {yr}:  total={total:>3}  "
              f"untouched={ut_n:>3}({ut_n/total*100:.0f}%)  "
              f"normal={nm_n:>3}({nm_n/total*100:.0f}%)  "
              f"breakout={bk_n:>3}({bk_n/total*100:.0f}%)")


def main():
    print("載入資料...")
    df = load_data_for_orb_est_hl()
    df_analysis = df[df.index >= "2022-01-01"]
    print(f"  {len(df_analysis):,} bars, 分析期間 2022~")

    print("分類交易日...")
    day_info = classify_days(df_analysis)

    analyze_untouched(day_info)


if __name__ == "__main__":
    main()
