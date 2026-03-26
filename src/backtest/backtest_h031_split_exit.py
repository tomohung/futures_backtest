#!/usr/bin/env python3
"""
H031 Phase 2: Split exit backtest — partial close at SatZone + trailing stop.

Tests 3 configurations:
  A: 100/0  — baseline (all at SatZone)
  B: 50/50  — 50% SatZone + 50% trailing
  C: 40/60  — 40% SatZone + 60% trailing

Trailing stop: 0.3 × EmaHL (fixed, not optimized).

Judgment criteria:
  - EV (avg PnL%) must be >= baseline in EVERY year 2022–2025
  - In-sample: 2022–2024, OOS: 2025–2026

Usage:
    uv run python src/backtest/backtest_h031_split_exit.py
"""

import sys
from pathlib import Path

import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_for_orb_est_hl
from src.strategies.orb_est_hl_split_exit import ORBWithEstHLSplitExitStrategy

CONFIGS = [
    {"label": "A: 100/0 (baseline)", "satzone_exit_portion": 1.0},
    {"label": "B: 50/50",            "satzone_exit_portion": 0.5},
    {"label": "C: 40/60",            "satzone_exit_portion": 0.4},
]

TRAIL_EMA_FRACTION = 0.3
ENTRY_SIZE = 10  # need >=10 for meaningful partial closes (size=1 rounds to full close)

YEARS = [
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
    ("2025", "2025-01-01", "2025-12-31"),
    ("2026", "2026-01-01", None),
]


def run_config(df: pd.DataFrame, portion: float) -> dict:
    """Run backtest for a single configuration, return stats."""
    bt = Backtest(
        df,
        ORBWithEstHLSplitExitStrategy,
        cash=10_000_000,
        commission=0.0,
        trade_on_close=True,
    )
    stats = bt.run(
        satzone_exit_portion=portion,
        trail_ema_fraction=TRAIL_EMA_FRACTION,
        entry_size=ENTRY_SIZE,
    )
    return stats


def compute_metrics(stats) -> dict:
    """Extract key metrics from backtest stats.

    With split exits, one entry may produce multiple trade records (partial close
    + remainder close). Aggregate by entry time to get per-trade metrics.
    """
    trades = stats["_trades"].copy()
    if len(trades) == 0:
        return {"n": 0, "wr": None, "pf": None, "ev_pts": None, "ev_pct": None, "total": None}

    # Group sub-trades by EntryTime (same entry → same trade)
    trades["EntryDate"] = pd.to_datetime(trades["EntryTime"]).dt.date
    grouped = trades.groupby("EntryDate").agg(
        PnL=("PnL", "sum"),
        Size=("Size", "first"),
        EntryPrice=("EntryPrice", "first"),
    )

    pnl = grouped["PnL"]
    # Normalize PnL to per-contract: divide by entry_size
    pnl_per = pnl / ENTRY_SIZE
    entry_prices = grouped["EntryPrice"]
    pnl_pct = pnl_per / entry_prices * 100

    wins = pnl_per[pnl_per > 0]
    losses = pnl_per[pnl_per < 0]

    return {
        "n": len(grouped),
        "wr": round(len(wins) / len(grouped) * 100, 1),
        "pf": round(wins.sum() / abs(losses.sum()), 2) if len(losses) and losses.sum() != 0 else None,
        "ev_pts": round(pnl_per.mean(), 1),
        "ev_pct": round(pnl_pct.mean(), 3),
        "total": round(pnl_per.sum(), 0),
        "total_pct": round(pnl_pct.sum(), 2),
    }


def main():
    print("載入資料（全期間，含 EMA 暖機）...")
    df_full = load_data_for_orb_est_hl()
    print(f"  {len(df_full):,} bars, {df_full.index[0].date()} ~ {df_full.index[-1].date()}")

    # Results: config → year → metrics
    all_results = {}

    for cfg in CONFIGS:
        label = cfg["label"]
        portion = cfg["satzone_exit_portion"]
        all_results[label] = {}

        print(f"\n{'=' * 70}")
        print(f"  {label}  (trail={TRAIL_EMA_FRACTION}×EmaHL)")
        print(f"{'=' * 70}")

        for yr_label, start, end in YEARS:
            df_yr = df_full[df_full.index >= start]
            if end:
                df_yr = df_yr[df_yr.index <= end]

            if df_yr.empty:
                continue

            stats = run_config(df_yr, portion)
            m = compute_metrics(stats)
            all_results[label][yr_label] = m

            wr_s = f"{m['wr']:.1f}%" if m['wr'] is not None else "—"
            pf_s = f"{m['pf']:.2f}" if m['pf'] is not None else "—"
            ev_s = f"{m['ev_pts']:+.1f}" if m['ev_pts'] is not None else "—"
            evp_s = f"{m['ev_pct']:+.3f}%" if m['ev_pct'] is not None else "—"
            tot_s = f"{m['total']:+.0f}" if m['total'] is not None else "—"

            print(f"  {yr_label}:  N={m['n']:>3}  WR={wr_s:>6}  PF={pf_s:>5}  "
                  f"EV={ev_s:>7} pts ({evp_s:>8})  Total={tot_s:>6} pts")

    # Comparison table
    print(f"\n\n{'=' * 78}")
    print("  逐年 EV% 比較（分批出場 vs baseline）")
    print(f"{'=' * 78}")

    baseline_label = CONFIGS[0]["label"]
    header = f"  {'Year':<6}"
    for cfg in CONFIGS:
        header += f"  {cfg['label']:>20}"
    header += "  │  B vs A   C vs A"
    print(header)
    print(f"  {'-' * 78}")

    # Track per-year dominance
    yearly_wins = {cfg["label"]: 0 for cfg in CONFIGS[1:]}

    for yr_label, _, _ in YEARS:
        row = f"  {yr_label:<6}"
        baseline_ev = all_results[baseline_label].get(yr_label, {}).get("ev_pct")

        evs = []
        for cfg in CONFIGS:
            m = all_results[cfg["label"]].get(yr_label, {})
            ev = m.get("ev_pct")
            evs.append(ev)
            if ev is not None:
                row += f"  {ev:>+20.3f}%"
            else:
                row += f"  {'—':>20}"

        # Diff vs baseline
        row += "  │"
        for i, cfg in enumerate(CONFIGS[1:], 1):
            if evs[i] is not None and evs[0] is not None:
                diff = evs[i] - evs[0]
                sign = "✓" if diff >= 0 else "✗"
                row += f"  {diff:>+.3f} {sign}"
                if diff >= 0:
                    yearly_wins[cfg["label"]] += 1
            else:
                row += f"  {'—':>8}"

        print(row)

    # Verdict
    print(f"\n  判定標準：每年 EV% >= baseline")
    is_years = [y for y, _, _ in YEARS if y <= "2024"]
    oos_years = [y for y, _, _ in YEARS if y >= "2025"]
    print(f"  In-sample: {', '.join(is_years)}")
    print(f"  Out-of-sample: {', '.join(oos_years)}")

    for cfg in CONFIGS[1:]:
        label = cfg["label"]
        # Check IS years
        is_pass = True
        for yr in is_years:
            baseline_ev = all_results[baseline_label].get(yr, {}).get("ev_pct")
            test_ev = all_results[label].get(yr, {}).get("ev_pct")
            if baseline_ev is not None and test_ev is not None:
                if test_ev < baseline_ev:
                    is_pass = False
                    break
            else:
                is_pass = False
                break

        oos_pass = True
        for yr in oos_years:
            baseline_ev = all_results[baseline_label].get(yr, {}).get("ev_pct")
            test_ev = all_results[label].get(yr, {}).get("ev_pct")
            if baseline_ev is not None and test_ev is not None:
                if test_ev < baseline_ev:
                    oos_pass = False
                    break

        is_s = "PASS" if is_pass else "FAIL"
        oos_s = "PASS" if oos_pass else "FAIL"
        print(f"\n  {label}:")
        print(f"    In-sample:  {is_s}")
        print(f"    OOS:        {oos_s}")
        verdict = "CONFIRMED" if is_pass and oos_pass else "REJECTED"
        print(f"    Verdict:    {verdict}")


if __name__ == "__main__":
    main()
