#!/usr/bin/env python3
"""Explore CCD (Cumulative Candle Delta) as a potential entry filter.

Supports two strategies:
  esthl   — ORBWithEstHLExitStrategy  OR window: 8:45–8:57
  orblong — ORBLongStrategy           OR window: 8:45–9:30

For each trading day, compute the CCD value at the end of the OR window.
A positive CCD means more bullish volume during the OR; negative means more bearish.

Hypothesis: trades entered on days with positive OR-window CCD have higher win rates,
suggesting the breakout is volume-confirmed rather than a fake move.

Analysis:
  1. CCD sign (positive vs negative): win%, EV, total PnL
  2. CCD quartile breakdown: finer resolution on the relationship
  3. Year-by-year CCD sign breakdown: check stability across regimes

Usage:
    uv run python src/backtest/explore_ccd.py --strategy esthl --start 2021-01-01
    uv run python src/backtest/explore_ccd.py --strategy orblong --start 2021-01-01
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_for_orb_est_hl, load_data_with_night_ma
from src.indicators.volume import cumulative_candle_delta
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

# OR window end time per strategy
OR_END = {
    "esthl":   "08:57",
    "orblong": "09:30",
}


# ── CCD computation ───────────────────────────────────────────────────────────

def compute_or_ccd(df: pd.DataFrame, or_end: str = "08:57",
                   resample: str | None = None) -> pd.Series:
    """Compute CCD at the end of the OR window for each trading day.

    Parameters
    ----------
    or_end   : upper bound of OR window (e.g. "08:57" or "09:30")
    resample : if given (e.g. "5min"), resample OR bars before computing CCD

    Returns a Series indexed by date with the final accumulated CCD value.
    """
    or_mask = (df.index.time >= pd.Timestamp("08:45").time()) & \
              (df.index.time <= pd.Timestamp(or_end).time())
    df_or = df[or_mask].copy()

    results = {}
    for date, group in df_or.groupby(df_or.index.normalize()):
        if resample:
            group = group.resample(resample).agg(
                Open=("Open", "first"),
                High=("High", "max"),
                Low=("Low", "min"),
                Close=("Close", "last"),
                Volume=("Volume", "sum"),
            ).dropna(subset=["Open"])
        if len(group) == 0:
            continue
        ccd = cumulative_candle_delta(group["Open"], group["Close"], group["Volume"])
        results[date] = float(ccd.iloc[-1])

    return pd.Series(results, name="ccd_or_end")


# ── Formatting helpers ────────────────────────────────────────────────────────

def fv(v, width=8, dec=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—".rjust(width)
    if isinstance(v, float):
        return f"{v:.{dec}f}".rjust(width)
    return str(v).rjust(width)


def print_group_row(label, grp, width=12):
    pnl = grp["PnL"]
    n = len(pnl)
    if n == 0:
        print(f"  {label:<{width}}  {'0':>6}  {'—':>7}  {'—':>8}  {'—':>9}")
        return
    win_pct = (pnl > 0).sum() / n * 100
    avg_pnl = pnl.mean()
    total   = pnl.sum()
    print(f"  {label:<{width}}  {n:>6}  {win_pct:>6.1f}%  {fv(avg_pnl):>8}  {fv(total, dec=0):>9}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=["esthl", "orblong"], default="esthl")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=None)
    parser.add_argument("--resample", default=None,
                        help="Resample OR bars before CCD (e.g. '5min')")
    args = parser.parse_args()

    strat_name  = args.strategy.upper()
    or_end      = OR_END[args.strategy]
    resample    = args.resample
    res_label   = f" resampled to {resample}" if resample else " (1-min bars)"

    print("=" * 68)
    print(f"CCD (Cumulative Candle Delta) — OR Window Analysis for {strat_name}")
    print(f"OR window: 8:45 – {or_end}{res_label}")
    print("=" * 68)

    # ── Load full history for CCD computation (no date filter yet) ──────────
    print("\nLoading full history for CCD computation...", flush=True)
    if args.strategy == "esthl":
        df_full = load_data_for_orb_est_hl()
    else:
        df_full = load_data_with_night_ma(trend_ma_days=10)
    ccd_daily = compute_or_ccd(df_full, or_end=or_end, resample=resample)
    print(f"  {len(ccd_daily):,} trading days  "
          f"{ccd_daily.index[0].date()} ~ {ccd_daily.index[-1].date()}")
    pos = (ccd_daily > 0).sum()
    neg = (ccd_daily < 0).sum()
    zer = (ccd_daily == 0).sum()
    print(f"  CCD > 0: {pos} days ({pos/len(ccd_daily)*100:.1f}%)  "
          f"CCD < 0: {neg} days ({neg/len(ccd_daily)*100:.1f}%)  "
          f"CCD = 0: {zer} days")

    # ── Load date-filtered data for backtest ────────────────────────────────
    print(f"\nLoading backtest data and running {strat_name} strategy...", flush=True)
    if args.strategy == "esthl":
        df_bt     = load_data_for_orb_est_hl(start=args.start, end=args.end)
        strategy  = ORBWithEstHLExitStrategy
        bt_params = EST_HL_PARAMS
    else:
        df_bt     = load_data_with_night_ma(start=args.start, end=args.end, trend_ma_days=10)
        strategy  = ORBLongStrategy
        bt_params = ORBLONG_PARAMS

    bt = Backtest(df_bt, strategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**bt_params)
    trades = stats["_trades"].copy()
    trades["entry_date"] = pd.to_datetime(trades["EntryTime"]).dt.normalize()
    trades["win"]        = (trades["PnL"] > 0).astype(int)
    print(f"  {len(trades)} trades")

    # ── Merge CCD into trades ────────────────────────────────────────────────
    trades = trades.join(ccd_daily, on="entry_date")
    trades["ccd_sign"] = np.sign(trades["ccd_or_end"]).map(
        {1.0: "Positive", -1.0: "Negative", 0.0: "Zero"}
    )

    # ── Section 1: CCD sign breakdown ───────────────────────────────────────
    print("\n" + "=" * 68)
    print(f"1. CCD SIGN AT END OF OR WINDOW (8:45–{or_end})")
    print("=" * 68)
    print(f"  {'Sign':<12}  {'Trades':>6}  {'Win%':>7}  {'Avg PnL':>8}  {'Total PnL':>9}")
    print(f"  {'-'*12}  {'-'*6}  {'-'*7}  {'-'*8}  {'-'*9}")
    for sign in ["Positive", "Negative", "Zero"]:
        grp = trades[trades["ccd_sign"] == sign]
        print_group_row(sign, grp)
    print(f"  {'-'*12}  {'-'*6}  {'-'*7}  {'-'*8}  {'-'*9}")
    print_group_row("ALL", trades)

    # ── Section 2: CCD quartile breakdown ───────────────────────────────────
    print("\n" + "=" * 68)
    print("2. CCD QUARTILE BREAKDOWN")
    print("=" * 68)
    valid = trades[trades["ccd_or_end"].notna()].copy()
    if len(valid) >= 20:
        valid["q"] = pd.qcut(valid["ccd_or_end"], 4,
                              labels=["Q1(most bearish)", "Q2", "Q3", "Q4(most bullish)"])
        print(f"  {'Quartile':<18}  {'Trades':>6}  {'Win%':>7}  {'Avg PnL':>8}  "
              f"{'Total PnL':>9}  {'CCD range':>16}")
        print(f"  {'-'*18}  {'-'*6}  {'-'*7}  {'-'*8}  {'-'*9}  {'-'*16}")
        for q_label, grp in valid.groupby("q", observed=True):
            pnl = grp["PnL"]
            n   = len(pnl)
            win = (pnl > 0).sum() / n * 100
            lo  = grp["ccd_or_end"].min()
            hi  = grp["ccd_or_end"].max()
            print(f"  {str(q_label):<18}  {n:>6}  {win:>6.1f}%  {fv(pnl.mean()):>8}  "
                  f"{fv(pnl.sum(), dec=0):>9}  {lo:>7.0f} ~ {hi:<7.0f}")
    else:
        print("  Insufficient data for quartile analysis (<20 trades)")

    # ── Section 3: Year-by-year CCD sign breakdown ───────────────────────────
    print("\n" + "=" * 68)
    print("3. YEAR-BY-YEAR CCD SIGN BREAKDOWN")
    print("=" * 68)
    print(f"  {'Year':<6}  {'Sign':<10}  {'Trades':>6}  {'Win%':>7}  "
          f"{'Avg PnL':>8}  {'Total PnL':>9}")
    print(f"  {'-'*6}  {'-'*10}  {'-'*6}  {'-'*7}  {'-'*8}  {'-'*9}")
    for yr, start, end in YEARS:
        mask = trades["entry_date"] >= start
        if end:
            mask &= trades["entry_date"] <= end
        yr_trades = trades[mask]
        if len(yr_trades) == 0:
            continue
        for sign in ["Positive", "Negative"]:
            grp = yr_trades[yr_trades["ccd_sign"] == sign]
            if len(grp) == 0:
                continue
            pnl = grp["PnL"]
            win = (pnl > 0).sum() / len(pnl) * 100
            print(f"  {yr:<6}  {sign:<10}  {len(pnl):>6}  {win:>6.1f}%  "
                  f"{fv(pnl.mean()):>8}  {fv(pnl.sum(), dec=0):>9}")
        print(f"  {'':<6}  {'':<10}  {'':<6}")

    # ── Section 4: Hypothetical filter impact ───────────────────────────────
    print("\n" + "=" * 68)
    print("4. HYPOTHETICAL FILTER IMPACT (keep only Positive CCD trades)")
    print("=" * 68)
    filtered = trades[trades["ccd_sign"] == "Positive"]
    print(f"  Original:   {len(trades):>3} trades  "
          f"WR {(trades['PnL']>0).sum()/len(trades)*100:.1f}%  "
          f"EV {trades['PnL'].mean():.1f} pts  "
          f"Total {trades['PnL'].sum():.0f} pts")
    if len(filtered) > 0:
        print(f"  CCD>0 only: {len(filtered):>3} trades  "
              f"WR {(filtered['PnL']>0).sum()/len(filtered)*100:.1f}%  "
              f"EV {filtered['PnL'].mean():.1f} pts  "
              f"Total {filtered['PnL'].sum():.0f} pts")
        print(f"  Retention: {len(filtered)/len(trades)*100:.1f}% of trades kept")
    print()


if __name__ == "__main__":
    main()
