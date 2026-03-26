#!/usr/bin/env python3
"""H041: Reversal Skip After Breakout — Phase 1 Distribution Research.

Compare Reversal performance on days when EstHL triggered vs didn't trigger.
EstHL trigger = close > OR High during 08:58–09:15 (without applying VWAP/MA filters,
just the raw ORB breakout event).

Usage:
    uv run python src/backtest/explore_h041_skip_after_breakout.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_for_orb_est_hl, load_data_for_reversal
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy
from src.strategies.reversal import ReversalStrategy


# ── Helpers ──────────────────────────────────────────────────────────────────

def compute_pf(pnl: pd.Series) -> float:
    wins = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl < 0].sum())
    return wins / losses if losses > 0 else float("inf")


def fv(v, width=8, dec=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—".rjust(width)
    if isinstance(v, float):
        return f"{v:.{dec}f}".rjust(width)
    return str(v).rjust(width)


def print_group_stats(label, trades_df):
    """Print summary stats for a group of trades."""
    if trades_df.empty:
        print(f"  {label}: 0 trades")
        return
    pnl = trades_df["PnL"]
    n = len(pnl)
    wr = (pnl > 0).sum() / n * 100
    pf = compute_pf(pnl)
    avg = pnl.mean()
    total = pnl.sum()
    print(f"  {label}: N={n:>4}  WR={wr:5.1f}%  PF={pf:5.2f}  "
          f"AvgPnL={avg:+7.1f}  Total={total:+8.0f}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("H041: Reversal Skip After Breakout — Phase 1 Distribution")
    print("=" * 72)

    # ── Step 1: Run EstHL to get trigger dates ──
    print("\n[1/3] Running EstHL backtest to identify trigger dates...")
    df_esthl = load_data_for_orb_est_hl()
    bt_esthl = Backtest(df_esthl, ORBWithEstHLExitStrategy,
                        cash=200_000, commission=0.0, trade_on_close=True)
    stats_esthl = bt_esthl.run(
        sl_ema_fraction=0.25, vwap_days=2, long_only=True,
        skip_thursday=True, skip_friday=True,
    )
    esthl_trades = stats_esthl["_trades"].copy()
    esthl_trades["entry_date"] = pd.to_datetime(esthl_trades["EntryTime"]).dt.normalize()
    esthl_dates = set(esthl_trades["entry_date"].dt.date)
    print(f"  EstHL triggered on {len(esthl_dates)} days")

    # ── Step 2: Run Reversal to get all trades ──
    print("\n[2/3] Running Reversal backtest...")
    df_rev = load_data_for_reversal()
    bt_rev = Backtest(df_rev, ReversalStrategy,
                      cash=200_000, commission=0.0, trade_on_close=True)
    stats_rev = bt_rev.run()
    rev_trades = stats_rev["_trades"].copy()
    rev_trades["entry_date"] = pd.to_datetime(rev_trades["EntryTime"]).dt.normalize()
    rev_trades["entry_date_d"] = rev_trades["entry_date"].dt.date
    rev_trades["direction"] = rev_trades["Size"].apply(lambda x: "long" if x > 0 else "short")
    rev_trades["year"] = pd.to_datetime(rev_trades["EntryTime"]).dt.year
    print(f"  Reversal total trades: {len(rev_trades)}")

    # ── Step 3: Split and compare ──
    print("\n[3/3] Comparing Reversal on EstHL-trigger vs non-trigger days...")
    mask_trigger = rev_trades["entry_date_d"].isin(esthl_dates)
    rev_trigger = rev_trades[mask_trigger]
    rev_no_trigger = rev_trades[~mask_trigger]

    print("\n" + "=" * 72)
    print("Overall Comparison")
    print("=" * 72)
    print_group_stats("EstHL triggered day  ", rev_trigger)
    print_group_stats("EstHL NOT triggered  ", rev_no_trigger)
    print_group_stats("All Reversal trades  ", rev_trades)

    # ── By direction ──
    print("\n" + "-" * 72)
    print("By Direction (EstHL trigger day)")
    print("-" * 72)
    for d in ["long", "short"]:
        subset = rev_trigger[rev_trigger["direction"] == d]
        print_group_stats(f"  Trigger + {d:>5}", subset)
    print()
    print("By Direction (EstHL NOT trigger day)")
    print("-" * 72)
    for d in ["long", "short"]:
        subset = rev_no_trigger[rev_no_trigger["direction"] == d]
        print_group_stats(f"  No-trig + {d:>5}", subset)

    # ── By year ──
    print("\n" + "-" * 72)
    print("Year-by-Year Comparison")
    print("-" * 72)
    header = f"{'Year':>6}  {'':>2}  {'N(trig)':>7}  {'WR(t)':>6}  {'PnL(t)':>8}  " \
             f"{'N(no)':>7}  {'WR(n)':>6}  {'PnL(n)':>8}  {'Δ WR':>6}"
    print(header)
    print("-" * len(header))

    for year in sorted(rev_trades["year"].unique()):
        yr_all = rev_trades[rev_trades["year"] == year]
        yr_trig = yr_all[yr_all["entry_date_d"].isin(esthl_dates)]
        yr_no = yr_all[~yr_all["entry_date_d"].isin(esthl_dates)]

        n_t = len(yr_trig)
        n_n = len(yr_no)
        wr_t = (yr_trig["PnL"] > 0).sum() / n_t * 100 if n_t > 0 else float("nan")
        wr_n = (yr_no["PnL"] > 0).sum() / n_n * 100 if n_n > 0 else float("nan")
        pnl_t = yr_trig["PnL"].sum() if n_t > 0 else 0
        pnl_n = yr_no["PnL"].sum() if n_n > 0 else 0
        delta_wr = wr_n - wr_t if n_t > 0 and n_n > 0 else float("nan")

        print(f"{year:>6}  {'':>2}  {fv(n_t, 7, 0)}  {fv(wr_t, 6)}%  {fv(pnl_t, 8, 0)}  "
              f"{fv(n_n, 7, 0)}  {fv(wr_n, 6)}%  {fv(pnl_n, 8, 0)}  {fv(delta_wr, 6)}%")

    # ── Simulated filter: skip Reversal on EstHL-trigger days ──
    print("\n" + "=" * 72)
    print("Simulated Filter: Skip Reversal on EstHL-trigger days")
    print("=" * 72)
    print_group_stats("Original Reversal     ", rev_trades)
    print_group_stats("Filtered (skip trigger)", rev_no_trigger)

    orig_pnl = rev_trades["PnL"].sum()
    filt_pnl = rev_no_trigger["PnL"].sum()
    improvement = filt_pnl - orig_pnl
    print(f"\n  PnL change: {improvement:+.0f} pts "
          f"({'improvement' if improvement > 0 else 'regression'})")
    removed_pnl = rev_trigger["PnL"].sum()
    print(f"  Removed trades contributed: {removed_pnl:+.0f} pts")

    # ── Also check: ORB breakout days (broader definition) ──
    # Detect any day where price broke OR High in 08:58-09:15 window
    # (without VWAP/MA filters — raw breakout event)
    print("\n" + "=" * 72)
    print("Broader Check: ORB Breakout Days (raw, no filters)")
    print("=" * 72)
    print("Computing raw ORB breakout days from 1m data...")

    orb_breakout_dates = set()
    df_esthl_data = df_esthl.copy()
    df_esthl_data["date"] = df_esthl_data.index.date
    df_esthl_data["time"] = df_esthl_data.index.time

    from datetime import time as dtime
    for date, day_df in df_esthl_data.groupby("date"):
        # OR period: 08:45-08:57
        or_bars = day_df[(day_df["time"] >= dtime(8, 45)) & (day_df["time"] <= dtime(8, 57))]
        if or_bars.empty:
            continue
        or_high = or_bars["High"].max()
        or_low = or_bars["Low"].min()

        # Entry window: 08:58-09:15
        entry_bars = day_df[(day_df["time"] >= dtime(8, 58)) & (day_df["time"] <= dtime(9, 15))]
        if entry_bars.empty:
            continue

        # Check if close broke OR High (upward) OR OR Low (downward)
        if (entry_bars["Close"] > or_high).any() or (entry_bars["Close"] < or_low).any():
            orb_breakout_dates.add(date)

    print(f"  Raw ORB breakout days: {len(orb_breakout_dates)}")

    mask_orb = rev_trades["entry_date_d"].isin(orb_breakout_dates)
    rev_orb = rev_trades[mask_orb]
    rev_no_orb = rev_trades[~mask_orb]

    print_group_stats("ORB breakout day     ", rev_orb)
    print_group_stats("No ORB breakout      ", rev_no_orb)

    # Year breakdown for raw ORB filter
    print("\n  Year breakdown (raw ORB filter):")
    for year in sorted(rev_trades["year"].unique()):
        yr_all = rev_trades[rev_trades["year"] == year]
        yr_orb = yr_all[yr_all["entry_date_d"].isin(orb_breakout_dates)]
        yr_no_orb_y = yr_all[~yr_all["entry_date_d"].isin(orb_breakout_dates)]
        n_o = len(yr_orb)
        n_no = len(yr_no_orb_y)
        wr_o = (yr_orb["PnL"] > 0).sum() / n_o * 100 if n_o > 0 else float("nan")
        wr_no = (yr_no_orb_y["PnL"] > 0).sum() / n_no * 100 if n_no > 0 else float("nan")
        pnl_o = yr_orb["PnL"].sum()
        pnl_no = yr_no_orb_y["PnL"].sum()
        print(f"    {year}: ORB day N={n_o:>3} WR={wr_o:5.1f}% PnL={pnl_o:+7.0f}  |  "
              f"No-ORB N={n_no:>3} WR={wr_no:5.1f}% PnL={pnl_no:+7.0f}")

    print("\n" + "=" * 72)
    print("Done.")


if __name__ == "__main__":
    main()
