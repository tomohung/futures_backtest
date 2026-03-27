"""
H043 Phase 1: Multi-Day Rebound Exhaustion 分佈探索

核心場景：
  A) 開盤在 BC zone 之上（反彈到成本區上方），但 MA 方向仍向下
     → 若出現 BB Upper touch（BB%B > 1），反彈竭盡，做空
  B) 開盤在 BC zone 之下（回調到成本區下方），但 MA 方向仍向上
     → 若出現 BB Lower touch（BB%B < 0），回調竭盡，做多

Phase 1 任務：
  1. 統計 A/B 情境的歷史出現頻率
  2. 這些情境下 BB 極端觸碰的頻率
  3. BB 觸碰後的日內走勢（MFE/MAE）
  4. 對比一般 Reversal setup（方向一致）的 MFE/MAE
  5. 「昨/前日成本」VWAP vs 收盤價的差異

Usage:
    uv run python src/backtest/explore_h043_rebound_exhaustion.py
"""

import sys
from datetime import time as dtime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_for_reversal

DB_PATH = "data/futures.duckdb"

_SETUP_START = dtime(9, 5)
_ENTRY_START = dtime(9, 10)
_ENTRY_END = dtime(10, 5)


def classify_daily_context(df: pd.DataFrame) -> pd.DataFrame:
    """For each trading day, classify the BC zone / MA direction context.

    Returns DataFrame indexed by date with:
      open_price, bc_lo, bc_hi, bc_position (above/below/inside/nan),
      ma_bullish, scenario (rebound_exhaust_short / pullback_exhaust_long / aligned / na)
    """
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
            rows.append({"date": d.date(), "scenario": "na"})
            continue

        bc_lo, bc_hi = min(bc1, bc2), max(bc1, bc2)

        # BC position
        if open_price > bc_hi:
            bc_pos = "above"
        elif open_price < bc_lo:
            bc_pos = "below"
        else:
            bc_pos = "inside"

        # MA direction: 5m 120MA
        ma5m = float(day["MA5m_120"].iloc[0])
        ma5m_prev = float(day["MA5m_120_Prev"].iloc[0])
        if np.isnan(ma5m) or np.isnan(ma5m_prev):
            rows.append({"date": d.date(), "scenario": "na"})
            continue

        ma_bullish = ma5m > ma5m_prev

        # Scenario classification
        if bc_pos == "above" and not ma_bullish:
            scenario = "rebound_exhaust_short"  # H043 target: open > BC but MA down
        elif bc_pos == "below" and ma_bullish:
            scenario = "pullback_exhaust_long"  # H043 target: open < BC but MA up
        elif bc_pos == "above" and ma_bullish:
            scenario = "aligned_long"  # current Reversal: BC + MA both say long
        elif bc_pos == "below" and not ma_bullish:
            scenario = "aligned_short"  # current Reversal: BC + MA both say short
        elif bc_pos == "inside":
            scenario = "inside"
        else:
            scenario = "other"

        # Day stats
        ema_hl = day["EmaHL"].dropna()
        ema_hl_val = float(ema_hl.iloc[0]) if not ema_hl.empty else np.nan

        rows.append({
            "date": d.date(),
            "open_price": open_price,
            "bc_lo": bc_lo,
            "bc_hi": bc_hi,
            "bc_pos": bc_pos,
            "ma_bullish": ma_bullish,
            "scenario": scenario,
            "ema_hl": ema_hl_val,
            "day_high": day["High"].max(),
            "day_low": day["Low"].min(),
        })

    return pd.DataFrame(rows).set_index("date")


def find_bb_setups(df: pd.DataFrame, day_info: pd.DataFrame) -> pd.DataFrame:
    """Find BB extreme touches within the setup window for each scenario.

    For rebound_exhaust_short: look for BB Upper touch (close >= BB_Upper + vol_ok)
    For pullback_exhaust_long: look for BB Lower touch (close <= BB_Lower + vol_ok)
    Also find setups in aligned scenarios for comparison.

    Returns one row per BB setup found.
    """
    records = []
    dates = sorted(df.index.normalize().unique())

    for d in dates:
        d_date = d.date()
        if d_date not in day_info.index:
            continue

        info = day_info.loc[d_date]
        scenario = info["scenario"]
        if scenario in ("na", "inside"):
            continue

        day = df[df.index.normalize() == d]
        ema_hl = info.get("ema_hl", np.nan)
        if np.isnan(ema_hl) or ema_hl <= 0:
            continue

        # Determine which BB touch to look for based on scenario
        if scenario == "rebound_exhaust_short":
            look_for = "short"  # BB Upper touch → short setup
        elif scenario == "pullback_exhaust_long":
            look_for = "long"   # BB Lower touch → long setup
        elif scenario == "aligned_long":
            look_for = "long"   # normal: BB Lower touch → long
        elif scenario == "aligned_short":
            look_for = "short"  # normal: BB Upper touch → short
        else:
            continue

        # Scan for BB setup in the window
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

            # Step 1: BB latch
            if not bb_touched:
                if look_for == "short" and close >= bb_upper and vol_ok:
                    bb_touched = True
                elif look_for == "long" and close <= bb_lower and vol_ok:
                    bb_touched = True
                continue

            # Step 2: Trigger (MA5 cross)
            if t >= _ENTRY_START:
                if look_for == "long" and close > ma5:
                    trigger_idx = idx
                    trigger_price = close
                    break
                elif look_for == "short" and close < ma5:
                    trigger_idx = idx
                    trigger_price = close
                    break

            # Reset latch on MA5 cross (opportunity passed)
            if look_for == "long" and close > ma5:
                bb_touched = False
            if look_for == "short" and close < ma5:
                bb_touched = False

        if trigger_idx is None:
            continue

        # Compute MFE/MAE from trigger point to end of day
        remaining = day.loc[trigger_idx:]
        if look_for == "long":
            mfe = remaining["High"].max() - trigger_price
            mae = trigger_price - remaining["Low"].min()
        else:
            mfe = trigger_price - remaining["Low"].min()
            mae = remaining["High"].max() - trigger_price

        records.append({
            "date": d_date,
            "scenario": scenario,
            "direction": look_for,
            "trigger_time": trigger_idx.time(),
            "trigger_price": trigger_price,
            "ema_hl": ema_hl,
            "mfe": mfe,
            "mae": mae,
            "mfe_ratio": mfe / ema_hl,
            "mae_ratio": mae / ema_hl,
            "pnl_ratio": (mfe - mae) / ema_hl,  # rough proxy
            "mfe_gt_mae": mfe > mae,
        })

    return pd.DataFrame(records)


def main():
    print("載入 Reversal 資料...")
    df = load_data_for_reversal()
    df_analysis = df[df.index >= "2021-01-01"]
    print(f"  {len(df_analysis):,} bars, {df_analysis.index[0].date()} ~ {df_analysis.index[-1].date()}")

    # === Task 1: 分類每日情境 ===
    print("\n分類每日 BC zone / MA direction 情境...")
    day_info = classify_daily_context(df_analysis)

    print(f"\n{'=' * 70}")
    print(f"  Task 1: 情境出現頻率")
    print(f"{'=' * 70}")

    total = len(day_info[day_info["scenario"] != "na"])
    scenario_counts = day_info["scenario"].value_counts()
    for s in ["rebound_exhaust_short", "pullback_exhaust_long",
              "aligned_long", "aligned_short", "inside", "na"]:
        n = scenario_counts.get(s, 0)
        pct = n / total * 100 if total > 0 else 0
        marker = " ← H043 target" if s in ("rebound_exhaust_short", "pullback_exhaust_long") else ""
        print(f"  {s:<30} {n:>4} ({pct:5.1f}%){marker}")

    h043_n = scenario_counts.get("rebound_exhaust_short", 0) + scenario_counts.get("pullback_exhaust_long", 0)
    print(f"\n  H043 目標情境合計: {h043_n} 天 ({h043_n/total*100:.1f}%)")

    # Year by year
    print(f"\n  逐年分佈：")
    day_info_copy = day_info[day_info["scenario"] != "na"].copy()
    day_info_copy["year"] = [d.year for d in day_info_copy.index]
    for yr, grp in day_info_copy.groupby("year"):
        n_tot = len(grp)
        n_reb = (grp["scenario"] == "rebound_exhaust_short").sum()
        n_pull = (grp["scenario"] == "pullback_exhaust_long").sum()
        n_al = ((grp["scenario"] == "aligned_long") | (grp["scenario"] == "aligned_short")).sum()
        print(f"    {yr}: total={n_tot:>3}  "
              f"rebound_short={n_reb:>3}({n_reb/n_tot*100:.0f}%)  "
              f"pullback_long={n_pull:>3}({n_pull/n_tot*100:.0f}%)  "
              f"aligned={n_al:>3}({n_al/n_tot*100:.0f}%)")

    # === Task 2+3: BB setups and MFE/MAE ===
    print(f"\n{'=' * 70}")
    print(f"  Task 2+3: BB Setup 頻率與 MFE/MAE")
    print(f"{'=' * 70}")

    print("\n掃描 BB 極端觸碰...")
    setups = find_bb_setups(df_analysis, day_info)
    print(f"  找到 {len(setups)} 個 BB setup")

    if setups.empty:
        print("  沒有找到 BB setup，無法繼續分析。")
        return

    # Setup rate per scenario
    print(f"\n  各情境的 BB setup 觸發率：")
    for s in ["rebound_exhaust_short", "pullback_exhaust_long",
              "aligned_long", "aligned_short"]:
        n_days = scenario_counts.get(s, 0)
        n_setups = len(setups[setups["scenario"] == s])
        rate = n_setups / n_days * 100 if n_days > 0 else 0
        print(f"    {s:<30} {n_setups:>4}/{n_days:>4} ({rate:5.1f}%)")

    # MFE/MAE comparison
    print(f"\n  MFE/MAE 比較（以 EmaHL 標準化）：")
    print(f"  {'Scenario':<30} {'N':>4} {'MFE/EmaHL':>10} {'MAE/EmaHL':>10} "
          f"{'MFE>MAE%':>9} {'MFE-MAE':>8}")
    print(f"  {'-' * 75}")

    for s in ["rebound_exhaust_short", "pullback_exhaust_long",
              "aligned_long", "aligned_short"]:
        sub = setups[setups["scenario"] == s]
        if sub.empty:
            continue
        mfe_med = sub["mfe_ratio"].median()
        mae_med = sub["mae_ratio"].median()
        win_pct = sub["mfe_gt_mae"].mean() * 100
        net = mfe_med - mae_med
        print(f"  {s:<30} {len(sub):>4} {mfe_med:>10.3f} {mae_med:>10.3f} "
              f"{win_pct:>8.1f}% {net:>+8.3f}")

    # H043 targets combined
    h043_setups = setups[setups["scenario"].isin(
        ["rebound_exhaust_short", "pullback_exhaust_long"])]
    aligned_setups = setups[setups["scenario"].isin(
        ["aligned_long", "aligned_short"])]

    if not h043_setups.empty:
        print(f"\n  H043 目標（合計 N={len(h043_setups)}）：")
        print(f"    MFE/EmaHL: P25={h043_setups['mfe_ratio'].quantile(0.25):.3f}  "
              f"P50={h043_setups['mfe_ratio'].median():.3f}  "
              f"P75={h043_setups['mfe_ratio'].quantile(0.75):.3f}")
        print(f"    MAE/EmaHL: P25={h043_setups['mae_ratio'].quantile(0.25):.3f}  "
              f"P50={h043_setups['mae_ratio'].median():.3f}  "
              f"P75={h043_setups['mae_ratio'].quantile(0.75):.3f}")
        print(f"    MFE > MAE: {h043_setups['mfe_gt_mae'].mean()*100:.1f}%")

    if not aligned_setups.empty:
        print(f"\n  一般 Reversal aligned（合計 N={len(aligned_setups)}）：")
        print(f"    MFE/EmaHL: P25={aligned_setups['mfe_ratio'].quantile(0.25):.3f}  "
              f"P50={aligned_setups['mfe_ratio'].median():.3f}  "
              f"P75={aligned_setups['mfe_ratio'].quantile(0.75):.3f}")
        print(f"    MAE/EmaHL: P25={aligned_setups['mae_ratio'].quantile(0.25):.3f}  "
              f"P50={aligned_setups['mae_ratio'].median():.3f}  "
              f"P75={aligned_setups['mae_ratio'].quantile(0.75):.3f}")
        print(f"    MFE > MAE: {aligned_setups['mfe_gt_mae'].mean()*100:.1f}%")

    # === Task 4: MFE/MAE distribution detail ===
    print(f"\n{'=' * 70}")
    print(f"  Task 4: H043 MFE/MAE 細部分佈")
    print(f"{'=' * 70}")

    for s in ["rebound_exhaust_short", "pullback_exhaust_long"]:
        sub = setups[setups["scenario"] == s]
        if sub.empty:
            continue

        print(f"\n  {s}（N={len(sub)}）：")

        # MFE distribution
        mfe = sub["mfe_ratio"].values
        mae = sub["mae_ratio"].values
        net = mfe - mae

        print(f"    MFE/EmaHL: {np.percentile(mfe, [10, 25, 50, 75, 90])}")
        print(f"    MAE/EmaHL: {np.percentile(mae, [10, 25, 50, 75, 90])}")
        print(f"    Net (MFE-MAE)/EmaHL: P25={np.percentile(net, 25):+.3f}  "
              f"P50={np.median(net):+.3f}  P75={np.percentile(net, 75):+.3f}")

        # Year-by-year
        sub_copy = sub.copy()
        sub_copy["year"] = [d.year for d in sub_copy["date"]]
        print(f"    逐年：")
        for yr, grp in sub_copy.groupby("year"):
            n = len(grp)
            mfe_m = grp["mfe_ratio"].median()
            mae_m = grp["mae_ratio"].median()
            win = grp["mfe_gt_mae"].mean() * 100
            print(f"      {yr}: N={n:>3}  MFE={mfe_m:.3f}  MAE={mae_m:.3f}  "
                  f"MFE>MAE={win:.0f}%")

    # === Task 5: VWAP vs Close as "cost" ===
    print(f"\n{'=' * 70}")
    print(f"  Task 5: 前日成本定義（VWAP vs Close）")
    print(f"{'=' * 70}")

    # Re-classify using previous day close instead of VWAP
    dates = sorted(df_analysis.index.normalize().unique())
    close_rows = []
    for i, d in enumerate(dates):
        day = df_analysis[df_analysis.index.normalize() == d]
        if day.empty:
            continue
        d_date = d.date()

        open_price = float(day["Open"].iloc[0])
        # Get prev-day close from data
        if i == 0:
            continue
        prev_day = df_analysis[df_analysis.index.normalize() == dates[i-1]]
        if prev_day.empty:
            continue
        prev_close = float(prev_day["Close"].iloc[-1])

        ma5m = float(day["MA5m_120"].iloc[0])
        ma5m_prev = float(day["MA5m_120_Prev"].iloc[0])
        if np.isnan(ma5m) or np.isnan(ma5m_prev):
            continue
        ma_bullish = ma5m > ma5m_prev

        if open_price > prev_close and not ma_bullish:
            close_scenario = "rebound_short"
        elif open_price < prev_close and ma_bullish:
            close_scenario = "pullback_long"
        else:
            close_scenario = "other"

        close_rows.append({
            "date": d_date,
            "close_scenario": close_scenario,
        })

    close_df = pd.DataFrame(close_rows).set_index("date")
    vwap_target = set(day_info[day_info["scenario"].isin(
        ["rebound_exhaust_short", "pullback_exhaust_long"])].index)
    close_target = set(close_df[close_df["close_scenario"].isin(
        ["rebound_short", "pullback_long"])].index)

    overlap = vwap_target & close_target
    vwap_only = vwap_target - close_target
    close_only = close_target - vwap_target

    print(f"  VWAP 定義: {len(vwap_target)} 天")
    print(f"  Close 定義: {len(close_target)} 天")
    print(f"  重疊: {len(overlap)} 天")
    print(f"  VWAP only: {len(vwap_only)} 天")
    print(f"  Close only: {len(close_only)} 天")
    print(f"  → VWAP 作為 BC zone 已內建 2 天歷史，比單日 close 更穩定。建議沿用 VWAP。")

    print(f"\n{'=' * 70}")
    print(f"  H043 Phase 1 探索完成")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
