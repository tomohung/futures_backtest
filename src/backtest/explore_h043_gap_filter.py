"""
H043 補充：加入跳空距離條件

條件：open 距離 BC zone > N × EmaHL
  - rebound_short: open > bc_hi + N × EmaHL
  - pullback_long: open < bc_lo - N × EmaHL

測試 N = 0.3, 0.5, 0.7, 1.0 的效果

Usage:
    uv run python src/backtest/explore_h043_gap_filter.py
"""

import sys
from datetime import time as dtime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_for_reversal

_SETUP_START = dtime(9, 5)
_ENTRY_START = dtime(9, 10)
_ENTRY_END = dtime(10, 5)


def build_daily_info(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    dates = sorted(df.index.normalize().unique())

    for d in dates:
        day = df[df.index.normalize() == d]
        if day.empty:
            continue

        open_price = float(day["Open"].iloc[0])
        bc1 = float(day["VWAP1"].iloc[0])
        bc2 = float(day["VWAP2"].iloc[0])
        if np.isnan(bc1) or np.isnan(bc2):
            continue

        bc_lo, bc_hi = min(bc1, bc2), max(bc1, bc2)

        ma5m = float(day["MA5m_120"].iloc[0])
        ma5m_prev = float(day["MA5m_120_Prev"].iloc[0])
        if np.isnan(ma5m) or np.isnan(ma5m_prev):
            continue

        ma_bullish = ma5m > ma5m_prev

        ema_hl = day["EmaHL"].dropna()
        if ema_hl.empty:
            continue
        ema_hl_val = float(ema_hl.iloc[0])
        if ema_hl_val <= 0:
            continue

        # Gap distance from BC zone (in EmaHL units)
        if open_price > bc_hi:
            gap_from_bc = (open_price - bc_hi) / ema_hl_val
            bc_side = "above"
        elif open_price < bc_lo:
            gap_from_bc = (bc_lo - open_price) / ema_hl_val
            bc_side = "below"
        else:
            gap_from_bc = 0
            bc_side = "inside"

        # H043 scenario
        if bc_side == "above" and not ma_bullish:
            scenario = "rebound_short"
        elif bc_side == "below" and ma_bullish:
            scenario = "pullback_long"
        elif bc_side == "above" and ma_bullish:
            scenario = "aligned_long"
        elif bc_side == "below" and not ma_bullish:
            scenario = "aligned_short"
        else:
            scenario = "inside"

        rows.append({
            "date": d.date(),
            "open_price": open_price,
            "bc_lo": bc_lo,
            "bc_hi": bc_hi,
            "bc_side": bc_side,
            "ma_bullish": ma_bullish,
            "scenario": scenario,
            "gap_from_bc": gap_from_bc,
            "ema_hl": ema_hl_val,
        })

    return pd.DataFrame(rows).set_index("date")


def find_bb_setups_with_mfe(df: pd.DataFrame, target_dates: set, direction: str) -> pd.DataFrame:
    """Find BB setups and compute MFE/MAE for a set of target dates."""
    records = []

    for d in sorted(df.index.normalize().unique()):
        d_date = d.date()
        if d_date not in target_dates:
            continue

        day = df[df.index.normalize() == d]
        ema_hl = day["EmaHL"].dropna()
        if ema_hl.empty:
            continue
        ema_hl_val = float(ema_hl.iloc[0])
        if ema_hl_val <= 0:
            continue

        bb_touched = False
        trigger_idx = None
        trigger_price = None

        for idx in day.index:
            t = idx.time()
            if t < _SETUP_START:
                continue
            if t > _ENTRY_END:
                break

            close = float(day.at[idx, "Close"])
            bb_upper = float(day.at[idx, "BB_Upper"])
            bb_lower = float(day.at[idx, "BB_Lower"])
            vol = float(day.at[idx, "Volume"])
            vol_ma = float(day.at[idx, "VolMA20"])
            ma5 = float(day.at[idx, "MA5_1m"])

            if any(np.isnan(v) for v in [bb_upper, bb_lower, vol_ma, ma5]):
                continue

            vol_ok = vol > 1.2 * vol_ma

            if not bb_touched:
                if direction == "short" and close >= bb_upper and vol_ok:
                    bb_touched = True
                elif direction == "long" and close <= bb_lower and vol_ok:
                    bb_touched = True
                continue

            if t >= _ENTRY_START:
                if direction == "long" and close > ma5:
                    trigger_idx = idx
                    trigger_price = close
                    break
                elif direction == "short" and close < ma5:
                    trigger_idx = idx
                    trigger_price = close
                    break

            if direction == "long" and close > ma5:
                bb_touched = False
            if direction == "short" and close < ma5:
                bb_touched = False

        if trigger_idx is None:
            continue

        remaining = day.loc[trigger_idx:]
        if direction == "long":
            mfe = remaining["High"].max() - trigger_price
            mae = trigger_price - remaining["Low"].min()
        else:
            mfe = trigger_price - remaining["Low"].min()
            mae = remaining["High"].max() - trigger_price

        records.append({
            "date": d_date,
            "direction": direction,
            "trigger_price": trigger_price,
            "mfe": mfe,
            "mae": mae,
            "mfe_ratio": mfe / ema_hl_val,
            "mae_ratio": mae / ema_hl_val,
            "mfe_gt_mae": mfe > mae,
        })

    return pd.DataFrame(records)


def main():
    print("載入 Reversal 資料...")
    df = load_data_for_reversal()
    df_analysis = df[df.index >= "2021-01-01"]

    print("建立每日情境...")
    day_info = build_daily_info(df_analysis)

    h043_targets = day_info[day_info["scenario"].isin(["rebound_short", "pullback_long"])]

    print(f"\n{'=' * 78}")
    print(f"  跳空距離條件對 H043 的影響")
    print(f"{'=' * 78}")

    # Gap distribution for H043 targets
    print(f"\n  H043 目標情境的跳空距離分佈（gap_from_bc / EmaHL）：")
    for s in ["rebound_short", "pullback_long"]:
        sub = h043_targets[h043_targets["scenario"] == s]
        arr = sub["gap_from_bc"].values
        pcts = np.percentile(arr, [10, 25, 50, 75, 90])
        print(f"    {s:<20} N={len(sub):>4}  "
              f"P10={pcts[0]:.2f}  P25={pcts[1]:.2f}  P50={pcts[2]:.2f}  "
              f"P75={pcts[3]:.2f}  P90={pcts[4]:.2f}")

    # Test different gap thresholds
    thresholds = [0.0, 0.3, 0.5, 0.7, 1.0]

    print(f"\n  各跳空門檻下的 BB setup MFE/MAE：")
    print(f"  {'Threshold':<10} {'Scenario':<20} {'Days':>5} {'Setups':>7} "
          f"{'MFE/EHL':>8} {'MAE/EHL':>8} {'MFE>MAE':>8} {'Net':>8}")
    print(f"  {'-' * 82}")

    for thresh in thresholds:
        for s, direction in [("rebound_short", "short"), ("pullback_long", "long")]:
            sub = h043_targets[(h043_targets["scenario"] == s) &
                               (h043_targets["gap_from_bc"] >= thresh)]
            n_days = len(sub)
            if n_days == 0:
                print(f"  {thresh:<10.1f} {s:<20} {0:>5} {0:>7}")
                continue

            target_dates = set(sub.index)
            setups = find_bb_setups_with_mfe(df_analysis, target_dates, direction)
            n_setups = len(setups)

            if n_setups == 0:
                print(f"  {thresh:<10.1f} {s:<20} {n_days:>5} {0:>7}")
                continue

            mfe_med = setups["mfe_ratio"].median()
            mae_med = setups["mae_ratio"].median()
            win_pct = setups["mfe_gt_mae"].mean() * 100
            net = mfe_med - mae_med

            print(f"  {thresh:<10.1f} {s:<20} {n_days:>5} {n_setups:>7} "
                  f"{mfe_med:>8.3f} {mae_med:>8.3f} {win_pct:>7.1f}% {net:>+8.3f}")

    # Detailed analysis at gap >= 0.5 and >= 1.0
    for thresh in [0.5, 0.7, 1.0]:
        filtered = h043_targets[h043_targets["gap_from_bc"] >= thresh]
        if filtered.empty:
            continue

        print(f"\n{'=' * 78}")
        print(f"  Gap >= {thresh} × EmaHL 的細部分析")
        print(f"{'=' * 78}")

        for s, direction in [("rebound_short", "short"), ("pullback_long", "long")]:
            sub = filtered[filtered["scenario"] == s]
            if sub.empty:
                continue

            target_dates = set(sub.index)
            setups = find_bb_setups_with_mfe(df_analysis, target_dates, direction)

            if setups.empty:
                print(f"\n  {s}: {len(sub)} 天，0 setups")
                continue

            print(f"\n  {s}（{len(sub)} 天，{len(setups)} setups）：")

            mfe = setups["mfe_ratio"].values
            mae = setups["mae_ratio"].values
            net = mfe - mae
            print(f"    MFE/EmaHL: P25={np.percentile(mfe, 25):.3f}  "
                  f"P50={np.median(mfe):.3f}  P75={np.percentile(mfe, 75):.3f}")
            print(f"    MAE/EmaHL: P25={np.percentile(mae, 25):.3f}  "
                  f"P50={np.median(mae):.3f}  P75={np.percentile(mae, 75):.3f}")
            print(f"    Net:       P25={np.percentile(net, 25):+.3f}  "
                  f"P50={np.median(net):+.3f}  P75={np.percentile(net, 75):+.3f}")
            print(f"    MFE > MAE: {setups['mfe_gt_mae'].mean()*100:.1f}%")

            # Year by year
            setups_copy = setups.copy()
            setups_copy["year"] = [d.year for d in setups_copy["date"]]
            print(f"    逐年：")
            for yr, grp in setups_copy.groupby("year"):
                n = len(grp)
                mfe_m = grp["mfe_ratio"].median()
                mae_m = grp["mae_ratio"].median()
                win = grp["mfe_gt_mae"].mean() * 100
                print(f"      {yr}: N={n:>3}  MFE={mfe_m:.3f}  MAE={mae_m:.3f}  "
                      f"MFE>MAE={win:.0f}%  Net={mfe_m - mae_m:+.3f}")

    print(f"\n{'=' * 78}")
    print(f"  完成")
    print(f"{'=' * 78}")


if __name__ == "__main__":
    main()
