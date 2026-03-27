"""Diagnose why reversal strategy missed 6 live trades >1%.

For each missed date, check which gate failed:
- BC zone (VWAP1/VWAP2 vs open → allow_long/allow_short)
- MA direction (5m 120MA bullish/bearish)
- BB touch + volume (close <= BB_Lower or >= BB_Upper, vol > vol_ratio * VolMA20)
- CCD gate (CCD_5m direction)
- Near-SatZone latch
"""
import pandas as pd
import numpy as np
from src.backtest.runner import load_data_for_reversal

MISSED_DATES = [
    ("2024-11-05", "B"),
    ("2025-03-31", "S"),
    ("2025-04-15", "B"),
    ("2025-04-29", "B"),
    ("2025-10-15", "B"),
    ("2025-11-04", "S"),
]


def diagnose_date(df, date_str, live_dir):
    date = pd.Timestamp(date_str)
    day = df[df.index.normalize() == date]
    if day.empty:
        print(f"  !! No data for {date_str}")
        return

    first = day.iloc[0]
    open_price = first["Open"]
    vwap1 = first["VWAP1"]
    vwap2 = first["VWAP2"]

    # BC zone
    if np.isnan(vwap1) or np.isnan(vwap2):
        bc_result = "SKIP (NaN)"
        allow_long = False
        allow_short = False
    else:
        bc_lo, bc_hi = min(vwap1, vwap2), max(vwap1, vwap2)
        if open_price > bc_hi:
            bc_result = f"ABOVE → long only (open={open_price:.0f} > bc_hi={bc_hi:.0f})"
            allow_long, allow_short = True, False
        elif open_price < bc_lo:
            bc_result = f"BELOW → short only (open={open_price:.0f} < bc_lo={bc_lo:.0f})"
            allow_long, allow_short = False, True
        else:
            bc_result = f"INSIDE → follow MA (open={open_price:.0f}, bc=[{bc_lo:.0f}, {bc_hi:.0f}])"
            allow_long, allow_short = None, None  # depends on MA

    # MA direction at entry window
    entry_window = day.between_time("09:05", "10:05")
    if entry_window.empty:
        print(f"  !! No bars in entry window")
        return

    ma5m_vals = entry_window["MA5m_120"].dropna()
    ma5m_prev_vals = entry_window["MA5m_120_Prev"].dropna()
    if len(ma5m_vals) > 0 and len(ma5m_prev_vals) > 0:
        bullish_first = ma5m_vals.iloc[0] > ma5m_prev_vals.iloc[0]
        ma_dir = "BULLISH" if bullish_first else "BEARISH"
    else:
        ma_dir = "N/A"
        bullish_first = None

    # Resolve BC inside
    if allow_long is None:
        if bullish_first:
            allow_long, allow_short = True, False
            bc_result += f" → MA {ma_dir} → long"
        else:
            allow_long, allow_short = False, True
            bc_result += f" → MA {ma_dir} → short"

    # Direction match?
    if live_dir == "B":
        dir_allowed = allow_long
        dir_label = "long"
    else:
        dir_allowed = allow_short
        dir_label = "short"

    # BB touches in setup window (09:05-10:05)
    setup_window = day.between_time("09:05", "10:05")
    vol_ratio = 1.2
    bb_long_touches = 0
    bb_short_touches = 0
    for _, bar in setup_window.iterrows():
        vol_ok = bar["Volume"] > vol_ratio * bar["VolMA20"] if not np.isnan(bar["VolMA20"]) else False
        if bar["Close"] <= bar["BB_Lower"] and vol_ok:
            bb_long_touches += 1
        if bar["Close"] >= bar["BB_Upper"] and vol_ok:
            bb_short_touches += 1

    bb_touches = bb_long_touches if live_dir == "B" else bb_short_touches
    bb_label = "BB_Lower" if live_dir == "B" else "BB_Upper"

    # CCD in entry window
    ccd_vals = entry_window["CCD_5m"].dropna()
    if len(ccd_vals) > 0:
        ccd_range = f"[{ccd_vals.min():.0f}, {ccd_vals.max():.0f}]"
        if live_dir == "B":
            ccd_ok = (ccd_vals > 0).any()
        else:
            ccd_ok = (ccd_vals < 0).any()
    else:
        ccd_range = "N/A"
        ccd_ok = False

    # Near SatZone check
    sat_upper = entry_window["SatZoneUpper"].dropna()
    sat_lower = entry_window["SatZoneLower"].dropna()
    ema_hl = entry_window["EmaHL"].dropna()
    day_high = day["High"].cummax()
    day_low = day["Low"].cummin()
    near_sat = False
    if len(sat_upper) > 0 and len(ema_hl) > 0:
        margin = ema_hl.iloc[0] / 8
        # Check if extremes got close to SatZone during entry window
        for idx in entry_window.index:
            h = day_high.loc[:idx].iloc[-1]
            l = day_low.loc[:idx].iloc[-1]
            su = entry_window.loc[idx, "SatZoneUpper"]
            sl_val = entry_window.loc[idx, "SatZoneLower"]
            if not np.isnan(su) and su - h <= margin:
                near_sat = True
            if not np.isnan(sl_val) and l - sl_val <= margin:
                near_sat = True

    # Print diagnosis
    print(f"\n{'='*70}")
    print(f"  {date_str}  Live: {live_dir}  (want {dir_label})")
    print(f"{'='*70}")
    print(f"  1. BC Zone:     {bc_result}")
    print(f"     → {dir_label} allowed: {'YES' if dir_allowed else 'NO ← BLOCKED'}")
    print(f"  2. MA Direction: {ma_dir} (5m 120MA)")
    match_dir = (live_dir == "B" and bullish_first) or (live_dir == "S" and not bullish_first)
    print(f"     → matches live dir: {'YES' if match_dir else 'NO ← BLOCKED'}")
    print(f"  3. BB Touch:    {bb_label} touches with vol_ok = {bb_touches}")
    print(f"     → {'YES' if bb_touches > 0 else 'NO ← BLOCKED'}")
    print(f"  4. CCD:         range = {ccd_range}")
    print(f"     → ok for {dir_label}: {'YES' if ccd_ok else 'NO (but can bypass with 2nd BB or exhaustion)'}")
    print(f"  5. Near-SatZone: {'YES ← may block' if near_sat else 'NO (clear)'}")


def main():
    print("Loading data...")
    df = load_data_for_reversal(start="2024-11-01", end="2025-12-31")
    print(f"Loaded {len(df)} bars")

    for date_str, live_dir in MISSED_DATES:
        diagnose_date(df, date_str, live_dir)


if __name__ == "__main__":
    main()
