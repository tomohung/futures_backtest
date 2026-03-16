#!/usr/bin/env python3
"""Breakout timing analysis: does the exact entry minute affect win rate?

Supports two strategies:
  esthl   — ORBWithEstHLExitStrategy  entry window: ~08:55–09:15
  orblong — ORBLongStrategy           entry window: 09:30–11:00

For each strategy, extracts the precise entry timestamp from backtesting.py
trades and analyzes win rate by minute, 5-min bucket, key periods, and year.

Usage:
    uv run python src/backtest/explore_breakout_timing.py --strategy esthl
    uv run python src/backtest/explore_breakout_timing.py --strategy orblong
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_for_orb_est_hl, load_data_with_night_ma
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy
from src.strategies.orb import ORBLongStrategy

YEARS = [
    ("2021", "2021-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", None),
]

EST_HL_PARAMS = dict(
    sl_ema_fraction=0.25,
    bigcost_days=2,
    long_only=True,
    skip_thursday=True,
    skip_friday=True,
)

ORBLONG_PARAMS = dict(
    range_end_minute=90, entry_end_minute=120,
    sl_pct=0.004, tp_or_multiplier=1.5, or_min_width=20.0,
    tp_multiplier=1.5, trail_activate_minute=45, trend_ma_days=10,
    min_rolling_or=0.0,
)

# Key period definitions per strategy
KEY_PERIODS = {
    "esthl": [
        ("Before 09:00", lambda t: t < "09:00"),
        ("09:00",        lambda t: t == "09:00"),
        ("After 09:00",  lambda t: t > "09:00"),
    ],
    "orblong": [
        ("Early (09:31-09:45)",  lambda t: "09:31" <= t <= "09:45"),
        ("Mid (09:46-10:15)",    lambda t: "09:46" <= t <= "10:15"),
        ("Late (10:16-11:00)",   lambda t: "10:16" <= t <= "11:00"),
    ],
}


# ── Formatting helpers ────────────────────────────────────────────────────────

def fv(v, width=8, dec=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—".rjust(width)
    if isinstance(v, float):
        return f"{v:.{dec}f}".rjust(width)
    return str(v).rjust(width)


def compute_pf(pnl: pd.Series) -> str:
    wins = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl < 0].sum())
    if losses == 0:
        return "∞" if wins > 0 else "—"
    return f"{wins / losses:.2f}"


def print_stat_row(label, pnl, label_width=20):
    n = len(pnl)
    if n == 0:
        print(f"  {label:<{label_width}}  {'0':>6}  {'—':>7}  {'—':>8}  {'—':>9}  {'—':>6}")
        return
    win_pct = (pnl > 0).sum() / n * 100
    avg = pnl.mean()
    total = pnl.sum()
    pf = compute_pf(pnl)
    print(f"  {label:<{label_width}}  {n:>6}  {win_pct:>6.1f}%  {fv(avg):>8}  {fv(total, dec=0):>9}  {pf:>6}")


def print_header(label_width=20):
    print(f"  {'':>{label_width}}  {'Trades':>6}  {'Win%':>7}  {'Avg PnL':>8}  {'Total PnL':>9}  {'PF':>6}")
    print(f"  {'-'*label_width}  {'-'*6}  {'-'*7}  {'-'*8}  {'-'*9}  {'-'*6}")


def make_5min_bucket(entry_time: str) -> str:
    """Round HH:MM down to 5-min bucket, e.g. 09:07 -> 09:05."""
    h, m = entry_time.split(":")
    m5 = int(m) // 5 * 5
    return f"{h}:{m5:02d}"


# ── Main ──────────────────────────────────────────────────────────────────────

def run_backtest(strategy_name: str) -> pd.DataFrame:
    """Run backtest and return trades with entry_minute and win columns."""
    print(f"\nLoading data and running {strategy_name.upper()} strategy...", flush=True)
    if strategy_name == "esthl":
        df = load_data_for_orb_est_hl()
        strategy = ORBWithEstHLExitStrategy
        params = EST_HL_PARAMS
    else:
        df = load_data_with_night_ma(trend_ma_days=10)
        strategy = ORBLongStrategy
        params = ORBLONG_PARAMS

    bt = Backtest(df, strategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**params)
    trades = stats["_trades"].copy()
    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["entry_minute"] = trades["EntryTime"].dt.strftime("%H:%M")
    trades["entry_bucket"] = trades["entry_minute"].apply(make_5min_bucket)
    trades["win"] = (trades["PnL"] > 0).astype(int)
    trades["year"] = trades["EntryTime"].dt.year.astype(str)
    print(f"  {len(trades)} trades  "
          f"{trades['EntryTime'].dt.date.min()} ~ {trades['EntryTime'].dt.date.max()}")
    return trades


def section_per_minute(trades: pd.DataFrame):
    """Section 1: per-minute statistics."""
    print("\n" + "=" * 72)
    print("1. PER-MINUTE ENTRY STATISTICS (full period)")
    print("=" * 72)
    print_header(label_width=8)
    for minute, grp in trades.groupby("entry_minute"):
        print_stat_row(minute, grp["PnL"], label_width=8)
    print(f"  {'-'*8}  {'-'*6}  {'-'*7}  {'-'*8}  {'-'*9}  {'-'*6}")
    print_stat_row("ALL", trades["PnL"], label_width=8)


def section_5min_bucket(trades: pd.DataFrame):
    """Section 2: 5-minute bucket statistics."""
    print("\n" + "=" * 72)
    print("2. 5-MINUTE BUCKET STATISTICS (full period)")
    print("=" * 72)
    print_header(label_width=12)
    for bucket, grp in trades.groupby("entry_bucket"):
        print_stat_row(bucket, grp["PnL"], label_width=12)
    print(f"  {'-'*12}  {'-'*6}  {'-'*7}  {'-'*8}  {'-'*9}  {'-'*6}")
    print_stat_row("ALL", trades["PnL"], label_width=12)


def section_key_periods(trades: pd.DataFrame, strategy_name: str):
    """Section 3: key period comparison."""
    print("\n" + "=" * 72)
    print("3. KEY PERIOD COMPARISON")
    print("=" * 72)
    periods = KEY_PERIODS[strategy_name]
    lw = max(len(p[0]) for p in periods)
    print_header(label_width=lw)
    for label, fn in periods:
        mask = trades["entry_minute"].apply(fn)
        print_stat_row(label, trades.loc[mask, "PnL"], label_width=lw)
    print(f"  {'-'*lw}  {'-'*6}  {'-'*7}  {'-'*8}  {'-'*9}  {'-'*6}")
    print_stat_row("ALL", trades["PnL"], label_width=lw)


def section_yearly_stability(trades: pd.DataFrame):
    """Section 4: 5-min bucket × year win rate cross table."""
    print("\n" + "=" * 72)
    print("4. YEARLY STABILITY (Win% by 5-min bucket × year)")
    print("=" * 72)

    buckets = sorted(trades["entry_bucket"].unique())
    years = sorted(trades["year"].unique())

    # Header
    header = f"  {'Bucket':<8}"
    for yr in years:
        header += f"  {yr:>10}"
    header += f"  {'ALL':>10}"
    print(header)
    print(f"  {'-'*8}" + f"  {'-'*10}" * (len(years) + 1))

    for bucket in buckets:
        row = f"  {bucket:<8}"
        b_trades = trades[trades["entry_bucket"] == bucket]
        for yr in years:
            yr_b = b_trades[b_trades["year"] == yr]
            if len(yr_b) == 0:
                row += f"  {'—':>10}"
            else:
                wr = yr_b["win"].mean() * 100
                row += f"  {f'{wr:.0f}% ({len(yr_b)})':>10}"
        # ALL column
        wr_all = b_trades["win"].mean() * 100
        row += f"  {f'{wr_all:.0f}% ({len(b_trades)})':>10}"
        print(row)


def section_histogram(trades: pd.DataFrame):
    """Section 5: ASCII histogram of entry time distribution."""
    print("\n" + "=" * 72)
    print("5. ENTRY TIME DISTRIBUTION (histogram)")
    print("=" * 72)

    buckets = sorted(trades["entry_bucket"].unique())
    counts = trades.groupby("entry_bucket").size()
    max_count = counts.max()
    bar_width = 40

    for bucket in buckets:
        n = counts.get(bucket, 0)
        bar_len = int(n / max_count * bar_width) if max_count > 0 else 0
        bar = "█" * bar_len
        print(f"  {bucket}  {bar} {n}")


def main():
    parser = argparse.ArgumentParser(
        description="Breakout timing analysis: entry minute vs win rate")
    parser.add_argument("--strategy", choices=["esthl", "orblong"], default="esthl")
    args = parser.parse_args()

    strat = args.strategy
    print("=" * 72)
    print(f"BREAKOUT TIMING ANALYSIS — {strat.upper()}")
    print("=" * 72)

    trades = run_backtest(strat)

    section_per_minute(trades)
    section_5min_bucket(trades)
    section_key_periods(trades, strat)
    section_yearly_stability(trades)
    section_histogram(trades)

    print()


if __name__ == "__main__":
    main()
