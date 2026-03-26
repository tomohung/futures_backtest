#!/usr/bin/env python3
"""H044: Deep dive into 31 TRIGGER_MISSED trades.

For each date where direction was correct and BB setup existed but
the backtest didn't trigger, analyze bar-by-bar to find:
- Did MA5 cross happen? When?
- Was CCD ever in the right direction?
- Was exhaustion reached?
- Did near-SatZone latch block entry?
- BB touch count
- How close did trigger conditions get?
"""
import csv
import sys
from collections import Counter
from datetime import time as dtime
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.backtest.runner import load_data_for_reversal
from src.strategies.reversal import ReversalStrategy

DATA_DIR = Path(__file__).parent / "data"
LIVE_CSV = DATA_DIR / "live_parsed.csv"

REVERSAL_PARAMS = dict(
    vol_ratio=1.2,
    sl_ema_fraction=0.25,
    exhaust_fraction=0.5,
    signal_skip=0,
)


def load_live_reversal():
    rows = []
    with open(LIVE_CSV) as f:
        for r in csv.DictReader(f):
            if r["strategy"] != "reversal" or not r["entry_price"] or not r["exit_price"]:
                continue
            rows.append({
                "date": r["date"], "direction": r["direction"],
                "entry_time": r["entry_time"],
                "entry_price": int(r["entry_price"]),
                "pnl": int(r["pnl"]) if r["pnl"] else None,
            })
    return pd.DataFrame(rows)


def analyze_trigger_missed(df_data, live_only_trades):
    """Bar-by-bar analysis of why trigger didn't fire."""
    results = []

    for _, trade in live_only_trades.iterrows():
        date_str = trade["date"]
        live_dir = trade["direction"]
        live_time = trade["entry_time"]
        live_pnl = trade["pnl"]

        day_data = df_data[df_data.index.date == pd.Timestamp(date_str).date()]
        if len(day_data) == 0:
            continue

        first_bar = day_data.iloc[0]

        # BC zone
        vwap1 = float(first_bar["VWAP1"]) if not np.isnan(first_bar["VWAP1"]) else None
        vwap2 = float(first_bar["VWAP2"]) if not np.isnan(first_bar["VWAP2"]) else None
        open_price = float(first_bar["Open"])

        if vwap1 is not None and vwap2 is not None:
            bc_lo, bc_hi = min(vwap1, vwap2), max(vwap1, vwap2)
            if open_price > bc_hi:
                bc_dir = "long_only"
            elif open_price < bc_lo:
                bc_dir = "short_only"
            else:
                bc_dir = "inside"
        else:
            bc_dir = "no_data"

        # MA direction
        ma5m = float(first_bar["MA5m_120"])
        ma5m_prev = float(first_bar["MA5m_120_Prev"])
        if np.isnan(ma5m) or np.isnan(ma5m_prev):
            continue
        bullish = ma5m > ma5m_prev
        ma_dir = "bullish" if bullish else "bearish"

        # Determine if direction is allowed
        if bc_dir == "long_only":
            allowed_long, allowed_short = True, False
        elif bc_dir == "short_only":
            allowed_long, allowed_short = False, True
        elif bc_dir == "inside":
            allowed_long = bullish
            allowed_short = not bullish
        else:
            continue

        is_long = (live_dir == "B")
        if is_long and not allowed_long:
            continue  # DIR_BLOCKED, not TRIGGER_MISSED
        if not is_long and not allowed_short:
            continue

        # Scan entry window bar by bar
        entry_window = day_data[
            (day_data.index.time >= dtime(8, 45)) &
            (day_data.index.time <= dtime(10, 5))
        ]

        vol_ratio = 1.2
        exhaust_fraction = 0.5

        bb_touch_count = 0
        bb_touched = False
        ccd_ever_ok = False
        exhaustion_reached = False
        ma5_cross_ever = False
        ma5_cross_while_setup = False
        near_sat_latch = False

        day_low = float(day_data.iloc[0]["Low"])
        day_high = float(day_data.iloc[0]["High"])

        # Track state
        setup_bars = 0  # bars where setup was active
        trigger_block_reasons = Counter()

        for idx, bar in entry_window.iterrows():
            t = idx.time()
            close = float(bar["Close"])
            high = float(bar["High"])
            low = float(bar["Low"])
            vol = float(bar["Volume"])

            bb_upper = float(bar["BB_Upper"]) if not np.isnan(bar["BB_Upper"]) else None
            bb_lower = float(bar["BB_Lower"]) if not np.isnan(bar["BB_Lower"]) else None
            vol_ma = float(bar["VolMA20"]) if not np.isnan(bar["VolMA20"]) else None
            ccd = float(bar["CCD_5m"]) if not np.isnan(bar["CCD_5m"]) else 0
            ma5 = float(bar["MA5_1m"]) if not np.isnan(bar["MA5_1m"]) else None
            ema_hl = float(bar["EmaHL"]) if not np.isnan(bar["EmaHL"]) else None

            day_low = min(day_low, low)
            day_high = max(day_high, high)

            vol_ok = vol_ma is not None and vol > vol_ratio * vol_ma

            # BB touch
            if is_long and bb_lower is not None and close <= bb_lower and vol_ok:
                if not bb_touched:
                    bb_touch_count += 1
                    bb_touched = True
            if not is_long and bb_upper is not None and close >= bb_upper and vol_ok:
                if not bb_touched:
                    bb_touch_count += 1
                    bb_touched = True

            # Reset BB latch on MA5 cross (same as strategy)
            if ma5 is not None:
                if is_long and close > ma5:
                    bb_touched = False
                if not is_long and close < ma5:
                    bb_touched = False

            # CCD check
            if is_long and ccd > 0:
                ccd_ever_ok = True
            if not is_long and ccd < 0:
                ccd_ever_ok = True

            # Exhaustion
            if ema_hl is not None and ema_hl > 0:
                if is_long and close <= day_high - ema_hl * exhaust_fraction:
                    exhaustion_reached = True
                if not is_long and close >= day_low + ema_hl * exhaust_fraction:
                    exhaustion_reached = True

            # MA5 cross
            if ma5 is not None:
                if is_long and close > ma5:
                    ma5_cross_ever = True
                if not is_long and close < ma5:
                    ma5_cross_ever = True

            # Near-SatZone check
            sat_upper = float(bar["SatZoneUpper"]) if not np.isnan(bar["SatZoneUpper"]) else None
            sat_lower = float(bar["SatZoneLower"]) if not np.isnan(bar["SatZoneLower"]) else None
            if ema_hl is not None and ema_hl > 0:
                margin = ema_hl / 8
                if sat_upper is not None and day_high is not None:
                    if sat_upper - day_high <= margin:
                        near_sat_latch = True
                if sat_lower is not None and day_low is not None:
                    if day_low - sat_lower <= margin:
                        near_sat_latch = True

            # Check what's blocking trigger in entry window (09:10+)
            if t >= dtime(9, 10):
                has_bb = bb_touched or bb_touch_count >= 1
                ccd_ok_now = (is_long and ccd > 0) or (not is_long and ccd < 0)
                gate_ok = ccd_ok_now or exhaustion_reached or bb_touch_count >= 2
                ma5_ok = ma5 is not None and ((is_long and close > ma5) or (not is_long and close < ma5))

                if has_bb and ma5_ok:
                    if gate_ok:
                        if near_sat_latch:
                            setup_bars += 1
                            trigger_block_reasons["near_sat_latch"] += 1
                    else:
                        setup_bars += 1
                        trigger_block_reasons["no_ccd_exhaust_bb2"] += 1
                elif has_bb and gate_ok:
                    if not ma5_ok:
                        setup_bars += 1
                        trigger_block_reasons["no_ma5_cross"] += 1
                elif has_bb:
                    setup_bars += 1
                    reasons = []
                    if not gate_ok:
                        reasons.append("no_gate")
                    if not ma5_ok:
                        reasons.append("no_ma5")
                    trigger_block_reasons["+".join(reasons) if reasons else "unknown"] += 1

        # Determine primary block reason
        if near_sat_latch and trigger_block_reasons.get("near_sat_latch", 0) > 0:
            primary_block = "NEAR_SATZONE"
        elif bb_touch_count == 0:
            primary_block = "NO_BB_TOUCH"
        elif trigger_block_reasons:
            primary_block = trigger_block_reasons.most_common(1)[0][0].upper()
        else:
            primary_block = "NO_SETUP_IN_WINDOW"

        results.append({
            "date": date_str,
            "live_dir": live_dir,
            "live_time": live_time,
            "live_pnl": live_pnl,
            "bc_dir": bc_dir,
            "ma_dir": ma_dir,
            "bb_touches": bb_touch_count,
            "ccd_ever_ok": ccd_ever_ok,
            "exhaustion": exhaustion_reached,
            "ma5_cross_ever": ma5_cross_ever,
            "near_sat": near_sat_latch,
            "primary_block": primary_block,
            "block_detail": dict(trigger_block_reasons),
        })

    return pd.DataFrame(results)


def main():
    live = load_live_reversal()
    start, end = live["date"].min(), live["date"].max()

    print("Loading data...")
    df_data = load_data_for_reversal()
    df_data = df_data[(df_data.index >= start) & (df_data.index <= end)]

    print("Finding live-only dates...")
    bt_dates = set()
    bt = Backtest(df_data, ReversalStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**REVERSAL_PARAMS)
    for _, t in stats["_trades"].iterrows():
        bt_dates.add(pd.to_datetime(t["EntryTime"]).strftime("%Y-%m-%d"))

    live_only = live[~live["date"].isin(bt_dates)].copy()
    print(f"Live-only: {len(live_only)} trades")

    results = analyze_trigger_missed(df_data, live_only)
    # Filter to actual TRIGGER_MISSED (not DIR_BLOCKED)
    print(f"Trigger-missed candidates analyzed: {len(results)}")

    if len(results) == 0:
        print("No trigger-missed trades found.")
        return

    # ── Summary by primary block reason ──
    print(f"\n{'=' * 72}")
    print("PRIMARY BLOCK REASON (why trigger didn't fire)")
    print(f"{'=' * 72}")
    reason_counts = Counter(results["primary_block"])
    for reason, count in reason_counts.most_common():
        subset = results[results["primary_block"] == reason]
        pnl = subset["live_pnl"].dropna()
        wins = (pnl > 0).sum()
        total = pnl.sum()
        win_pct = f"{wins / len(pnl) * 100:.0f}%" if len(pnl) > 0 else "—"
        print(f"  {reason:<25} {count:>3} trades, Win {win_pct:>4}, PnL {total:>+6}")

    # ── Feature summary ──
    print(f"\n{'=' * 72}")
    print("FEATURE SUMMARY (across all trigger-missed)")
    print(f"{'=' * 72}")
    print(f"  BB touch count distribution:")
    for n, cnt in sorted(Counter(results["bb_touches"]).items()):
        print(f"    {n} touches: {cnt} trades")
    print(f"  CCD ever correct:    {results['ccd_ever_ok'].sum()} / {len(results)}")
    print(f"  Exhaustion reached:  {results['exhaustion'].sum()} / {len(results)}")
    print(f"  MA5 cross ever:      {results['ma5_cross_ever'].sum()} / {len(results)}")
    print(f"  Near-SatZone latch:  {results['near_sat'].sum()} / {len(results)}")

    # ── Detail table ──
    print(f"\n{'=' * 72}")
    print("DETAIL TABLE")
    print(f"{'=' * 72}")
    print(f"  {'Date':>12}  {'Dir':>3}  {'Time':>5}  {'PnL':>6}  "
          f"{'BB#':>3}  {'CCD':>3}  {'Exh':>3}  {'MA5':>3}  {'Sat':>3}  {'Block Reason'}")
    print(f"  {'-'*12}  {'-'*3}  {'-'*5}  {'-'*6}  "
          f"{'-'*3}  {'-'*3}  {'-'*3}  {'-'*3}  {'-'*3}  {'-'*25}")

    for _, r in results.sort_values("date").iterrows():
        print(f"  {r['date']:>12}  {r['live_dir']:>3}  {r['live_time']:>5}  {r['live_pnl']:>+6}  "
              f"{r['bb_touches']:>3}  {'✓' if r['ccd_ever_ok'] else '✗':>3}  "
              f"{'✓' if r['exhaustion'] else '✗':>3}  "
              f"{'✓' if r['ma5_cross_ever'] else '✗':>3}  "
              f"{'✓' if r['near_sat'] else '✗':>3}  {r['primary_block']}")

    # ── Timing analysis ──
    print(f"\n{'=' * 72}")
    print("LIVE ENTRY TIME DISTRIBUTION (trigger-missed)")
    print(f"{'=' * 72}")
    times = results["live_time"].dropna()
    buckets = Counter()
    for t in times:
        if t:
            h, m = t.split(":")
            bucket = f"{h}:{int(m) // 10 * 10:02d}"
            buckets[bucket] += 1
    for bucket, count in sorted(buckets.items()):
        bar = "█" * count
        print(f"  {bucket}  {bar} {count}")

    # ── BC zone distribution ──
    print(f"\n{'=' * 72}")
    print("BC ZONE DISTRIBUTION (trigger-missed)")
    print(f"{'=' * 72}")
    for bc, count in Counter(results["bc_dir"]).most_common():
        subset = results[results["bc_dir"] == bc]
        pnl = subset["live_pnl"].dropna()
        total = pnl.sum()
        print(f"  {bc:<20} {count:>3} trades, PnL {total:>+6}")

    print()


if __name__ == "__main__":
    main()
