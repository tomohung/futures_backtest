#!/usr/bin/env python3
"""H044: Analyze why 48 live-only reversal trades didn't trigger in backtest.

For each live-only date, check the backtest data to determine:
- What direction did BC zone + MA allow?
- Did a BB touch + vol_ok setup occur?
- If setup occurred, why didn't trigger fire?

This helps understand the gap between live judgment and programmatic rules.
"""
import csv
import sys
from pathlib import Path
from datetime import time as dtime

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


def load_live_reversal() -> pd.DataFrame:
    rows = []
    with open(LIVE_CSV) as f:
        for r in csv.DictReader(f):
            if r["strategy"] != "reversal":
                continue
            if not r["entry_price"] or not r["exit_price"]:
                continue
            rows.append({
                "date": r["date"],
                "direction": r["direction"],
                "entry_time": r["entry_time"],
                "entry_price": int(r["entry_price"]),
                "pnl": int(r["pnl"]) if r["pnl"] else None,
            })
    return pd.DataFrame(rows)


def run_backtest_dates(start, end):
    df = load_data_for_reversal()
    df = df[(df.index >= start) & (df.index <= end)]
    bt = Backtest(df, ReversalStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**REVERSAL_PARAMS)
    trades = stats["_trades"].copy()
    trades["date"] = pd.to_datetime(trades["EntryTime"]).dt.strftime("%Y-%m-%d")
    return set(trades["date"])


def analyze_live_only(df_data, live_only_trades):
    """For each live-only date, check what the backtest data shows."""
    results = []

    for _, trade in live_only_trades.iterrows():
        date_str = trade["date"]
        live_dir = trade["direction"]
        live_entry_time = trade["entry_time"]
        live_pnl = trade["pnl"]

        # Get day's data
        day_data = df_data[df_data.index.date == pd.Timestamp(date_str).date()]
        if len(day_data) == 0:
            results.append({
                "date": date_str, "live_dir": live_dir, "live_time": live_entry_time,
                "live_pnl": live_pnl, "reason": "NO_DATA",
                "bc_dir": "", "ma_dir": "", "bb_setup": "", "detail": "",
            })
            continue

        first_bar = day_data.iloc[0]
        open_price = float(first_bar["Open"])

        # BC zone direction
        vwap1 = float(first_bar["VWAP1"]) if not np.isnan(first_bar["VWAP1"]) else None
        vwap2 = float(first_bar["VWAP2"]) if not np.isnan(first_bar["VWAP2"]) else None

        if vwap1 is not None and vwap2 is not None:
            bc_lo, bc_hi = min(vwap1, vwap2), max(vwap1, vwap2)
            if open_price > bc_hi:
                bc_dir = "long_only"
            elif open_price < bc_lo:
                bc_dir = "short_only"
            else:
                bc_dir = "inside_follow_ma"
        else:
            bc_dir = "no_bc_data"

        # MA direction (5m 120MA)
        ma5m = float(first_bar["MA5m_120"]) if not np.isnan(first_bar["MA5m_120"]) else None
        ma5m_prev = float(first_bar["MA5m_120_Prev"]) if not np.isnan(first_bar["MA5m_120_Prev"]) else None

        if ma5m is not None and ma5m_prev is not None:
            ma_bullish = ma5m > ma5m_prev
            ma_dir = "bullish" if ma_bullish else "bearish"
        else:
            ma_dir = "no_ma_data"
            ma_bullish = None

        # Determine allowed direction
        if bc_dir == "long_only":
            allowed = "B"
        elif bc_dir == "short_only":
            allowed = "S"
        elif bc_dir == "inside_follow_ma":
            allowed = "B" if ma_bullish else "S"
        else:
            allowed = "?"

        # Check if direction mismatch
        dir_match = (allowed == live_dir)

        # Check BB setup in entry window (09:10-10:05)
        entry_window = day_data[
            (day_data.index.time >= dtime(8, 45)) &
            (day_data.index.time <= dtime(10, 5))
        ]

        bb_long_touch = False
        bb_short_touch = False
        vol_ratio = 1.2

        for idx, bar in entry_window.iterrows():
            close = float(bar["Close"])
            bb_lower = float(bar["BB_Lower"]) if not np.isnan(bar["BB_Lower"]) else None
            bb_upper = float(bar["BB_Upper"]) if not np.isnan(bar["BB_Upper"]) else None
            vol = float(bar["Volume"])
            vol_ma = float(bar["VolMA20"]) if not np.isnan(bar["VolMA20"]) else None

            vol_ok = vol_ma is not None and vol > vol_ratio * vol_ma

            if bb_lower is not None and close <= bb_lower and vol_ok:
                bb_long_touch = True
            if bb_upper is not None and close >= bb_upper and vol_ok:
                bb_short_touch = True

        if live_dir == "B":
            bb_setup = "yes" if bb_long_touch else "no"
        else:
            bb_setup = "yes" if bb_short_touch else "no"

        # Determine reason
        if not dir_match:
            reason = "DIR_BLOCKED"
            detail = f"BC={bc_dir}, MA={ma_dir} → allowed={allowed}, live={live_dir}"
        elif bb_setup == "no":
            reason = "NO_BB_SETUP"
            detail = f"BC={bc_dir}, MA={ma_dir} → dir OK, but no BB touch+vol"
        else:
            reason = "TRIGGER_MISSED"
            detail = f"BC={bc_dir}, MA={ma_dir} → dir OK, BB setup OK, trigger conditions not met"

        results.append({
            "date": date_str, "live_dir": live_dir, "live_time": live_entry_time,
            "live_pnl": live_pnl, "reason": reason,
            "bc_dir": bc_dir, "ma_dir": ma_dir, "allowed": allowed,
            "bb_setup": bb_setup, "detail": detail,
        })

    return pd.DataFrame(results)


def main():
    live = load_live_reversal()
    start = live["date"].min()
    end = live["date"].max()

    print("Loading backtest data...")
    df_data = load_data_for_reversal()
    df_data = df_data[(df_data.index >= start) & (df_data.index <= end)]

    print("Running backtest to get trade dates...")
    bt_dates = run_backtest_dates(start, end)
    live_dates = set(live["date"])
    live_only_dates = live_dates - bt_dates

    live_only_trades = live[live["date"].isin(live_only_dates)].copy()
    print(f"\nLive-only trades to analyze: {len(live_only_trades)}")

    results = analyze_live_only(df_data, live_only_trades)

    # Summary by reason
    print("\n" + "=" * 72)
    print("REASON BREAKDOWN (why backtest didn't trade)")
    print("=" * 72)
    from collections import Counter
    reason_counts = Counter(results["reason"])
    for reason, count in reason_counts.most_common():
        subset = results[results["reason"] == reason]
        pnl = subset["live_pnl"].dropna()
        wins = (pnl > 0).sum() if len(pnl) > 0 else 0
        total = pnl.sum() if len(pnl) > 0 else 0
        win_pct = f"{wins / len(pnl) * 100:.0f}%" if len(pnl) > 0 else "—"
        print(f"  {reason:<20} {count:>3} trades, Win {win_pct:>4}, PnL {total:>+6}")

    # DIR_BLOCKED detail
    dir_blocked = results[results["reason"] == "DIR_BLOCKED"]
    if len(dir_blocked) > 0:
        print(f"\n{'=' * 72}")
        print("DIR_BLOCKED DETAIL")
        print(f"{'=' * 72}")
        print(f"  {'Date':>12}  {'Live':>4}  {'Allowed':>7}  {'BC Zone':>20}  {'MA':>8}  {'PnL':>6}")
        print(f"  {'-'*12}  {'-'*4}  {'-'*7}  {'-'*20}  {'-'*8}  {'-'*6}")
        for _, r in dir_blocked.sort_values("date").iterrows():
            print(f"  {r['date']:>12}  {r['live_dir']:>4}  {r['allowed']:>7}  "
                  f"{r['bc_dir']:>20}  {r['ma_dir']:>8}  {r['live_pnl']:>+6}")

        # Win rate when live went against BC zone
        pnl = dir_blocked["live_pnl"].dropna()
        if len(pnl) > 0:
            print(f"\n  Summary: {len(pnl)} trades against BC zone direction")
            print(f"  Win%: {(pnl > 0).sum() / len(pnl) * 100:.1f}%")
            print(f"  Total PnL: {pnl.sum():+d}")
            print(f"  Avg PnL: {pnl.mean():+.1f}")

    # NO_BB_SETUP detail
    no_bb = results[results["reason"] == "NO_BB_SETUP"]
    if len(no_bb) > 0:
        print(f"\n{'=' * 72}")
        print("NO_BB_SETUP DETAIL")
        print(f"{'=' * 72}")
        print(f"  {'Date':>12}  {'Live':>4}  {'Time':>6}  {'BC Zone':>20}  {'MA':>8}  {'PnL':>6}")
        print(f"  {'-'*12}  {'-'*4}  {'-'*6}  {'-'*20}  {'-'*8}  {'-'*6}")
        for _, r in no_bb.sort_values("date").iterrows():
            print(f"  {r['date']:>12}  {r['live_dir']:>4}  {r['live_time']:>6}  "
                  f"{r['bc_dir']:>20}  {r['ma_dir']:>8}  {r['live_pnl']:>+6}")

        pnl = no_bb["live_pnl"].dropna()
        if len(pnl) > 0:
            print(f"\n  Summary: {len(pnl)} trades where BB didn't touch + vol_ok")
            print(f"  Win%: {(pnl > 0).sum() / len(pnl) * 100:.1f}%")
            print(f"  Total PnL: {pnl.sum():+d}")
            print(f"  Avg PnL: {pnl.mean():+.1f}")

    # TRIGGER_MISSED detail
    trigger_missed = results[results["reason"] == "TRIGGER_MISSED"]
    if len(trigger_missed) > 0:
        print(f"\n{'=' * 72}")
        print("TRIGGER_MISSED DETAIL")
        print(f"{'=' * 72}")
        print(f"  {'Date':>12}  {'Live':>4}  {'Time':>6}  {'BC Zone':>20}  {'MA':>8}  {'PnL':>6}")
        print(f"  {'-'*12}  {'-'*4}  {'-'*6}  {'-'*20}  {'-'*8}  {'-'*6}")
        for _, r in trigger_missed.sort_values("date").iterrows():
            print(f"  {r['date']:>12}  {r['live_dir']:>4}  {r['live_time']:>6}  "
                  f"{r['bc_dir']:>20}  {r['ma_dir']:>8}  {r['live_pnl']:>+6}")

        pnl = trigger_missed["live_pnl"].dropna()
        if len(pnl) > 0:
            print(f"\n  Summary: {len(pnl)} trades where setup existed but trigger didn't fire")
            print(f"  Win%: {(pnl > 0).sum() / len(pnl) * 100:.1f}%")
            print(f"  Total PnL: {pnl.sum():+d}")
            print(f"  Avg PnL: {pnl.mean():+.1f}")

    print()


if __name__ == "__main__":
    main()
