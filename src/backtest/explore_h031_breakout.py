"""
H031 Phase 1: EstimateHL 趨勢爆發日與未觸及日探索分析

三個待完成任務：
  1. 放量係數（cum_vol / expected_vol）最佳 slot 分析
  2. 趨勢爆發日觸及 SatZone 後繼續走的比例（50/100/200 點）
  3. EstHL 何時可靠預測低振幅日

Usage:
    uv run python src/backtest/explore_h031_breakout.py
"""

import sys
from datetime import date, time, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.estimate_hl import (
    TIME_FACTORS,
    _SLOT_TIMES,
    _get_slot,
    compute_estimate_hl_zones,
)
from src.backtest.runner import adjust_settlement_volume

DB_PATH = "data/futures.duckdb"


def load_day_session() -> pd.DataFrame:
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY timestamp
        """).df()
    df = df.set_index("timestamp")
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    return df


def classify_days(df: pd.DataFrame) -> pd.DataFrame:
    """Classify each trading day into breakout / normal / untouched.

    Returns a DataFrame indexed by date with columns:
      session_high, session_low, ema_hl, ema_vol,
      actual_hl, hl_ratio, sat_upper_max, sat_lower_min,
      day_vol, vol_ratio, category
    """
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
        vol_ratio = day_vol / ema_vol if ema_vol > 0 else np.nan

        # SatZone extremes during the day
        sat_u = day["SatZoneUpper"].dropna()
        sat_l = day["SatZoneLower"].dropna()
        sat_upper_max = sat_u.max() if not sat_u.empty else np.nan
        sat_lower_min = sat_l.min() if not sat_l.empty else np.nan

        # Classify
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

        rows.append({
            "date": d.date() if hasattr(d, "date") else d,
            "session_high": s_high,
            "session_low": s_low,
            "ema_hl": ema_hl,
            "ema_vol": ema_vol,
            "actual_hl": actual_hl,
            "hl_ratio": hl_ratio,
            "sat_upper_max": sat_upper_max,
            "sat_lower_min": sat_lower_min,
            "day_vol": day_vol,
            "vol_ratio": vol_ratio,
            "category": cat,
            "upper_exceed": upper_exceeded,
            "lower_exceed": lower_exceeded,
        })

    return pd.DataFrame(rows).set_index("date")


def task1_vol_ratio_by_slot(df: pd.DataFrame, day_info: pd.DataFrame):
    """Task 1: 放量係數（cum_vol / expected_vol）最佳 slot 分析

    At each 15-min slot boundary, compute cum_vol / (cum_factor * ema_vol).
    Compare breakout vs normal vs untouched groups.
    """
    print("\n" + "=" * 78)
    print("  Task 1: 放量係數 by slot（cum_vol / expected_vol）")
    print("=" * 78)

    breakout_dates = set(day_info[day_info["category"] == "breakout"].index)
    normal_dates = set(day_info[day_info["category"] == "normal"].index)
    untouched_dates = set(day_info[day_info["category"] == "untouched"].index)

    # Collect per-slot vol_ratio for each category
    slot_data = {cat: {} for cat in ["breakout", "normal", "untouched"]}
    dates = sorted(df.index.normalize().unique())

    for d in dates:
        d_date = d.date() if hasattr(d, "date") else d
        if d_date in breakout_dates:
            cat = "breakout"
        elif d_date in normal_dates:
            cat = "normal"
        elif d_date in untouched_dates:
            cat = "untouched"
        else:
            continue

        day = df[df.index.normalize() == d]
        ema_vol_vals = day["EmaVol"].dropna()
        if ema_vol_vals.empty:
            continue
        ema_vol = ema_vol_vals.iloc[0]
        if ema_vol <= 0:
            continue

        cum_vol = 0.0
        cum_factor = 0.0
        prev_slot = None

        for idx in day.index:
            t = idx.time()
            slot = _get_slot(t)
            vol = day.at[idx, "Volume"]

            if slot != prev_slot:
                if prev_slot is not None and cum_factor > 0:
                    vol_ratio = cum_vol / (cum_factor * ema_vol)
                    if prev_slot not in slot_data[cat]:
                        slot_data[cat][prev_slot] = []
                    slot_data[cat][prev_slot].append(vol_ratio)
                if prev_slot is None:
                    cum_factor = TIME_FACTORS.get(slot, 0.0)
                else:
                    cum_factor += TIME_FACTORS.get(slot, 0.0)

            cum_vol += vol
            prev_slot = slot

        # Final slot
        if prev_slot is not None and cum_factor > 0:
            vol_ratio = cum_vol / (cum_factor * ema_vol)
            if prev_slot not in slot_data[cat]:
                slot_data[cat][prev_slot] = []
            slot_data[cat][prev_slot].append(vol_ratio)

    # Print table
    slots_to_show = [s for s in _SLOT_TIMES if s >= time(9, 0)]

    print(f"\n  {'Slot':<8} {'breakout':>12} {'normal':>12} {'untouched':>12}  "
          f"{'BK-NM diff':>10}  {'Separation':>10}")
    print(f"  {'-' * 70}")

    best_sep = 0.0
    best_slot = None

    for slot in slots_to_show:
        vals = {}
        for cat in ["breakout", "normal", "untouched"]:
            arr = slot_data[cat].get(slot, [])
            vals[cat] = np.median(arr) if arr else np.nan

        diff = vals["breakout"] - vals["normal"] if not np.isnan(vals["breakout"]) else 0
        # Separation: diff / pooled std
        bk_arr = np.array(slot_data["breakout"].get(slot, []))
        nm_arr = np.array(slot_data["normal"].get(slot, []))
        if len(bk_arr) > 1 and len(nm_arr) > 1:
            pooled_std = np.sqrt((bk_arr.std() ** 2 + nm_arr.std() ** 2) / 2)
            sep = diff / pooled_std if pooled_std > 0 else 0
        else:
            sep = 0

        if sep > best_sep:
            best_sep = sep
            best_slot = slot

        print(f"  {str(slot):<8} {vals['breakout']:>12.3f} {vals['normal']:>12.3f} "
              f"{vals['untouched']:>12.3f}  {diff:>+10.3f}  {sep:>10.3f}")

    print(f"\n  最佳區分 slot: {best_slot}（separation = {best_sep:.3f}）")

    # Show distribution at best slot
    if best_slot:
        print(f"\n  {best_slot} slot 放量係數分佈：")
        for cat in ["breakout", "normal", "untouched"]:
            arr = np.array(slot_data[cat].get(best_slot, []))
            if len(arr) > 0:
                pcts = np.percentile(arr, [25, 50, 75])
                above_12 = (arr > 1.2).mean() * 100
                print(f"    {cat:<12}  N={len(arr):>4}  "
                      f"P25={pcts[0]:.3f}  P50={pcts[1]:.3f}  P75={pcts[2]:.3f}  "
                      f">1.2: {above_12:.1f}%")


def task2_post_satzone_continuation(df: pd.DataFrame, day_info: pd.DataFrame):
    """Task 2: 趨勢爆發日觸及 SatZone 後繼續走的比例

    For breakout days, find the first bar that touches SatZone (upper or lower),
    then measure how much further price moves beyond that touch point.
    Uses normalized metrics: cont/touch_price (%) and cont/EmaHL (ratio).
    """
    print("\n" + "=" * 78)
    print("  Task 2: 趨勢爆發日觸及 SatZone 後的續行（標準化）")
    print("=" * 78)

    breakout_dates = day_info[day_info["category"] == "breakout"].index
    # Each record: (cont_points, cont_pct, cont_emahl_ratio, touch_time, side)
    records = []

    for d_date in breakout_dates:
        d = pd.Timestamp(d_date)
        day = df[df.index.normalize() == d]
        if day.empty:
            continue

        ema_hl_vals = day["EmaHL"].dropna()
        if ema_hl_vals.empty:
            continue
        ema_hl = ema_hl_vals.iloc[0]
        if ema_hl <= 0:
            continue

        sat_u = day["SatZoneUpper"].dropna()
        sat_l = day["SatZoneLower"].dropna()
        if sat_u.empty and sat_l.empty:
            continue

        # Check upper touch
        if not sat_u.empty:
            for idx in day.index:
                su = day.at[idx, "SatZoneUpper"]
                if pd.isna(su):
                    continue
                if day.at[idx, "High"] >= su:
                    remaining = day.loc[idx:]
                    max_after = remaining["High"].max()
                    cont_pts = max_after - su
                    records.append({
                        "cont_pts": cont_pts,
                        "cont_pct": cont_pts / su * 100,
                        "cont_emahl": cont_pts / ema_hl,
                        "touch_time": idx.time(),
                        "touch_price": su,
                        "ema_hl": ema_hl,
                        "side": "upper",
                    })
                    break

        # Check lower touch
        if not sat_l.empty:
            for idx in day.index:
                sl = day.at[idx, "SatZoneLower"]
                if pd.isna(sl):
                    continue
                if day.at[idx, "Low"] <= sl:
                    remaining = day.loc[idx:]
                    min_after = remaining["Low"].min()
                    cont_pts = sl - min_after
                    records.append({
                        "cont_pts": cont_pts,
                        "cont_pct": cont_pts / sl * 100,
                        "cont_emahl": cont_pts / ema_hl,
                        "touch_time": idx.time(),
                        "touch_price": sl,
                        "ema_hl": ema_hl,
                        "side": "lower",
                    })
                    break

    rec_df = pd.DataFrame(records)

    print(f"\n  爆發日 SatZone 觸及後續行情分析（N={len(breakout_dates)} 天，{len(rec_df)} 次觸及）：")

    for label, mask in [("上方觸及", rec_df["side"] == "upper"),
                         ("下方觸及", rec_df["side"] == "lower"),
                         ("合計", rec_df["side"].notna())]:
        sub = rec_df[mask]
        if sub.empty:
            continue

        print(f"\n  {label}（N={len(sub)}）：")

        # 續行點數 / 觸及價（%）
        pct = sub["cont_pct"].values
        print(f"    續行%（cont/touch_price）：")
        print(f"      中位數: {np.median(pct):.2f}%")
        print(f"      P25/P75: {np.percentile(pct, 25):.2f}% / {np.percentile(pct, 75):.2f}%")

        # 續行點數 / EmaHL（ratio）
        ratio = sub["cont_emahl"].values
        print(f"    續行/EmaHL ratio：")
        print(f"      中位數: {np.median(ratio):.3f}")
        print(f"      P25/P75: {np.percentile(ratio, 25):.3f} / {np.percentile(ratio, 75):.3f}")

        # Threshold analysis using EmaHL ratio
        emahl_thresholds = [0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
        print(f"    續走（以 EmaHL 為基準）：")
        for t in emahl_thresholds:
            pct_above = (ratio >= t).mean() * 100
            print(f"      >= {t:.1f} × EmaHL: {pct_above:5.1f}%  ({(ratio >= t).sum()}/{len(ratio)})")

        # Also show % thresholds
        pct_thresholds = [0.3, 0.5, 0.7, 1.0, 1.5]
        print(f"    續走（以觸及價%）：")
        for t in pct_thresholds:
            pct_above = (pct >= t).mean() * 100
            print(f"      >= {t:.1f}%: {pct_above:5.1f}%  ({(pct >= t).sum()}/{len(pct)})")

    # Touch timing
    if not rec_df.empty:
        all_times = rec_df["touch_time"].tolist()
        print(f"\n  觸及時間分佈：")
        time_bins = [time(9, 0), time(9, 30), time(10, 0), time(10, 30),
                     time(11, 0), time(11, 30), time(12, 0), time(13, 0)]
        for i, tb in enumerate(time_bins[:-1]):
            count = sum(1 for t in all_times if tb <= t < time_bins[i + 1])
            print(f"    {tb.strftime('%H:%M')}~{time_bins[i+1].strftime('%H:%M')}: "
                  f"{count} 次 ({count/len(all_times)*100:.1f}%)")

    # Year-by-year comparison to check for base-price distortion
    if not rec_df.empty:
        print(f"\n  逐年比較（確認標準化後穩定性）：")
        rec_df["year"] = [d_date.year if hasattr(d_date, 'year')
                          else pd.Timestamp(d_date).year
                          for d_date in breakout_dates
                          for _ in range(len(rec_df))
                          ][:len(rec_df)]  # rough, redo properly
        # Redo year assignment from touch dates in day_info
        rec_df_with_year = rec_df.copy()
        # Extract year from breakout_dates aligned to records
        year_list = []
        idx = 0
        for d_date in breakout_dates:
            d = pd.Timestamp(d_date)
            day = df[df.index.normalize() == d]
            if day.empty:
                continue
            ema_hl_vals = day["EmaHL"].dropna()
            if ema_hl_vals.empty:
                continue
            ema_hl = ema_hl_vals.iloc[0]
            if ema_hl <= 0:
                continue
            sat_u = day["SatZoneUpper"].dropna()
            sat_l = day["SatZoneLower"].dropna()
            if sat_u.empty and sat_l.empty:
                continue
            if not sat_u.empty:
                for bar_idx in day.index:
                    su = day.at[bar_idx, "SatZoneUpper"]
                    if pd.isna(su):
                        continue
                    if day.at[bar_idx, "High"] >= su:
                        year_list.append(d_date.year if hasattr(d_date, "year") else d.year)
                        break
            if not sat_l.empty:
                for bar_idx in day.index:
                    sl = day.at[bar_idx, "SatZoneLower"]
                    if pd.isna(sl):
                        continue
                    if day.at[bar_idx, "Low"] <= sl:
                        year_list.append(d_date.year if hasattr(d_date, "year") else d.year)
                        break
        rec_df_with_year = rec_df.iloc[:len(year_list)].copy()
        rec_df_with_year["year"] = year_list[:len(rec_df_with_year)]

        print(f"  {'Year':<6} {'N':>4} {'cont% P50':>10} {'cont/EmaHL P50':>15} {'touch_price P50':>16}")
        print(f"  {'-' * 55}")
        for yr, grp in rec_df_with_year.groupby("year"):
            print(f"  {yr:<6} {len(grp):>4} {grp['cont_pct'].median():>10.2f}% "
                  f"{grp['cont_emahl'].median():>14.3f} "
                  f"{grp['touch_price'].median():>15.0f}")


def task3_esthl_predict_low_vol(df: pd.DataFrame, day_info: pd.DataFrame):
    """Task 3: EstHL 何時可靠預測低振幅日

    For untouched days (HL_ratio < 0.75), check at each slot boundary whether
    EstHL / EmaHL < threshold can predict the day is low-volatility.
    Compare with normal/breakout days for false positive rate.
    """
    print("\n" + "=" * 78)
    print("  Task 3: EstHL 盤中預測低振幅日的可行性")
    print("=" * 78)

    # Per-slot EstHL / EmaHL ratios for each category
    slot_ratios = {cat: {} for cat in ["breakout", "normal", "untouched"]}
    dates = sorted(df.index.normalize().unique())

    breakout_dates = set(day_info[day_info["category"] == "breakout"].index)
    normal_dates = set(day_info[day_info["category"] == "normal"].index)
    untouched_dates = set(day_info[day_info["category"] == "untouched"].index)

    for d in dates:
        d_date = d.date() if hasattr(d, "date") else d
        if d_date in breakout_dates:
            cat = "breakout"
        elif d_date in normal_dates:
            cat = "normal"
        elif d_date in untouched_dates:
            cat = "untouched"
        else:
            continue

        day = df[df.index.normalize() == d]
        ema_hl_vals = day["EmaHL"].dropna()
        if ema_hl_vals.empty:
            continue
        ema_hl = ema_hl_vals.iloc[0]
        if ema_hl <= 0:
            continue

        prev_slot = None
        for idx in day.index:
            t = idx.time()
            slot = _get_slot(t)

            if slot != prev_slot and prev_slot is not None:
                est_hl = day.at[idx, "EstHL"]
                if not pd.isna(est_hl):
                    ratio = est_hl / ema_hl
                    if prev_slot not in slot_ratios[cat]:
                        slot_ratios[cat][prev_slot] = []
                    slot_ratios[cat][prev_slot].append(ratio)

            prev_slot = slot

    # Analyze thresholds at each slot
    thresholds = [0.60, 0.65, 0.70, 0.75, 0.80]
    slots_to_show = [s for s in _SLOT_TIMES if s >= time(9, 15)]

    print(f"\n  各 slot 的 EstHL/EmaHL 中位數：")
    print(f"  {'Slot':<8} {'breakout':>10} {'normal':>10} {'untouched':>10}")
    print(f"  {'-' * 42}")

    for slot in slots_to_show:
        vals = {}
        for cat in ["breakout", "normal", "untouched"]:
            arr = slot_ratios[cat].get(slot, [])
            vals[cat] = np.median(arr) if arr else np.nan
        print(f"  {str(slot):<8} {vals['breakout']:>10.3f} {vals['normal']:>10.3f} "
              f"{vals['untouched']:>10.3f}")

    # For each slot x threshold, compute precision and recall for "untouched" prediction
    print(f"\n  低振幅日預測（EstHL/EmaHL < threshold 時預測為低振幅）：")
    print(f"  {'Slot':<8} {'Thresh':>6} {'Precision':>10} {'Recall':>8} "
          f"{'F1':>6}  {'TP':>4} {'FP':>4} {'FN':>4}")
    print(f"  {'-' * 58}")

    best_f1 = 0
    best_combo = None

    for slot in [s for s in slots_to_show if s <= time(11, 0)]:
        for thresh in thresholds:
            ut_arr = np.array(slot_ratios["untouched"].get(slot, []))
            nm_arr = np.array(slot_ratios["normal"].get(slot, []))
            bk_arr = np.array(slot_ratios["breakout"].get(slot, []))

            if len(ut_arr) == 0:
                continue

            tp = (ut_arr < thresh).sum()
            fn = (ut_arr >= thresh).sum()
            fp = (nm_arr < thresh).sum() + (bk_arr < thresh).sum()

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

            if f1 > best_f1:
                best_f1 = f1
                best_combo = (slot, thresh)

            print(f"  {str(slot):<8} {thresh:>6.2f} {precision:>10.3f} {recall:>8.3f} "
                  f"{f1:>6.3f}  {tp:>4} {fp:>4} {fn:>4}")

    if best_combo:
        print(f"\n  最佳組合: slot={best_combo[0]}, threshold={best_combo[1]:.2f}"
              f"（F1={best_f1:.3f}）")

    # Additional: cumulative HL by time for untouched vs normal
    print(f"\n  盤中振幅累積（cum_hl / ema_hl）by slot：")
    print(f"  {'Slot':<8} {'breakout':>10} {'normal':>10} {'untouched':>10}")
    print(f"  {'-' * 42}")

    cum_hl_data = {cat: {} for cat in ["breakout", "normal", "untouched"]}

    for d in dates:
        d_date = d.date() if hasattr(d, "date") else d
        if d_date in breakout_dates:
            cat = "breakout"
        elif d_date in normal_dates:
            cat = "normal"
        elif d_date in untouched_dates:
            cat = "untouched"
        else:
            continue

        day = df[df.index.normalize() == d]
        ema_hl_vals = day["EmaHL"].dropna()
        if ema_hl_vals.empty:
            continue
        ema_hl = ema_hl_vals.iloc[0]
        if ema_hl <= 0:
            continue

        s_high = -np.inf
        s_low = np.inf
        prev_slot = None

        for idx in day.index:
            t = idx.time()
            slot = _get_slot(t)
            s_high = max(s_high, day.at[idx, "High"])
            s_low = min(s_low, day.at[idx, "Low"])

            if slot != prev_slot and prev_slot is not None:
                cum_hl = (s_high - s_low) / ema_hl
                if prev_slot not in cum_hl_data[cat]:
                    cum_hl_data[cat][prev_slot] = []
                cum_hl_data[cat][prev_slot].append(cum_hl)

            prev_slot = slot

    for slot in slots_to_show:
        vals = {}
        for cat in ["breakout", "normal", "untouched"]:
            arr = cum_hl_data[cat].get(slot, [])
            vals[cat] = np.median(arr) if arr else np.nan
        print(f"  {str(slot):<8} {vals['breakout']:>10.3f} {vals['normal']:>10.3f} "
              f"{vals['untouched']:>10.3f}")


def main():
    print("載入日盤資料...")
    df = load_day_session()
    print(f"  {len(df):,} bars, {df.index[0].date()} ~ {df.index[-1].date()}")

    # Adjust settlement volume
    adjust_settlement_volume(df)

    # Compute EstHL zones
    print("計算 EstHL zones...")
    df = compute_estimate_hl_zones(df)

    # Filter to analysis period (need warmup, so filter after compute)
    df_analysis = df[df.index >= "2022-01-01"]

    # Classify days
    print("分類交易日...")
    day_info = classify_days(df_analysis)
    cats = day_info["category"].value_counts()
    total = len(day_info)
    print(f"\n  總交易日: {total}")
    for cat in ["breakout", "normal", "untouched"]:
        n = cats.get(cat, 0)
        print(f"  {cat:<12}: {n:>4} ({n/total*100:.1f}%)")

    # Run tasks
    task1_vol_ratio_by_slot(df_analysis, day_info)
    task2_post_satzone_continuation(df_analysis, day_info)
    task3_esthl_predict_low_vol(df_analysis, day_info)

    print("\n" + "=" * 78)
    print("  H031 Phase 1 探索完成")
    print("=" * 78)


if __name__ == "__main__":
    main()
