#!/usr/bin/env python3
"""Trade analysis from a saved trades CSV.

Usage:
    uv run python src/backtest/analyze.py output/trades_best_params_2025_2026.csv
    uv run python src/backtest/analyze.py output/trades_best_params_2025_2026.csv --by-year
    uv run python src/backtest/analyze.py output/trades_best_params_2025_2026.csv --by-year --by-direction
"""
import argparse
import sys
from pathlib import Path

import pandas as pd


def compute_metrics(pnl: pd.Series, size: pd.Series | None = None) -> dict:
    if len(pnl) == 0:
        return {}

    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    # Max consecutive losses
    max_consec = cur = 0
    for v in (pnl <= 0).tolist():
        cur = cur + 1 if v else 0
        max_consec = max(max_consec, cur)

    # Max drawdown from cumulative PnL
    equity = pnl.cumsum()
    peak = equity.cummax()
    drawdown = equity - peak
    max_dd = drawdown.min()
    max_dd_idx = drawdown.idxmin()
    peak_idx = equity[:max_dd_idx].idxmax() if max_dd < 0 else None

    return {
        "n_trades":   len(pnl),
        "n_long":     int((size > 0).sum()) if size is not None else None,
        "n_short":    int((size < 0).sum()) if size is not None else None,
        "n_wins":     len(wins),
        "n_losses":   len(losses),
        "win_rate":   len(wins) / len(pnl) * 100,
        "avg_win":    wins.mean() if len(wins) else 0,
        "avg_loss":   losses.mean() if len(losses) else 0,
        "avg_wl":     wins.mean() / abs(losses.mean()) if len(wins) and len(losses) else None,
        "pf":         wins.sum() / abs(losses.sum()) if len(losses) and losses.sum() != 0 else None,
        "expectancy": pnl.mean(),
        "total_pnl":  pnl.sum(),
        "max_dd":     max_dd,
        "max_dd_peak_trade": int(peak_idx) + 1 if peak_idx is not None else None,
        "max_dd_end_trade":  int(max_dd_idx) + 1,
        "max_consec_loss": max_consec,
    }


def print_metrics(m: dict, label: str = "", point_value: int = 200):
    col_w = 22
    sep = "=" * 50

    if label:
        print(f"\n{sep}")
        print(f"  {label}")
    print(sep)

    def row(name, value):
        print(f"  {name:<{col_w}} {value}")

    row("Trades", f"{m['n_trades']}", )
    if m.get("n_long") is not None:
        row("  Long / Short", f"{m['n_long']} / {m['n_short']}")
    row("Win rate", f"{m['win_rate']:.1f}%  ({m['n_wins']}W / {m['n_losses']}L)")

    if m["avg_win"]:
        row("Avg win", f"+{m['avg_win']:.1f} pts  (NT${m['avg_win']*point_value:,.0f})")
    if m["avg_loss"]:
        row("Avg loss", f"{m['avg_loss']:.1f} pts  (NT${m['avg_loss']*point_value:,.0f})")
    if m["avg_wl"] is not None:
        row("Avg W/L ratio", f"{m['avg_wl']:.2f}")
    if m["pf"] is not None:
        row("Profit factor", f"{m['pf']:.2f}")

    row("Expectancy", f"{m['expectancy']:.1f} pts/trade  (NT${m['expectancy']*point_value:,.0f})")
    row("Total PnL", f"{m['total_pnl']:.0f} pts  (NT${m['total_pnl']*point_value:,.0f})")

    if m["max_dd"] < 0:
        dd_str = f"{m['max_dd']:.0f} pts  (NT${m['max_dd']*point_value:,.0f})"
        if m["max_dd_peak_trade"]:
            dd_str += f"  [trade #{m['max_dd_peak_trade']}→#{m['max_dd_end_trade']}]"
        row("Max drawdown", dd_str)
    else:
        row("Max drawdown", "0 (no drawdown)")

    row("Max consec losses", f"{m['max_consec_loss']}")
    print(sep)


def main():
    parser = argparse.ArgumentParser(description="Analyze trades CSV")
    parser.add_argument("csv", help="Path to trades CSV file")
    parser.add_argument("--by-year",      action="store_true", help="Break down metrics by year")
    parser.add_argument("--by-direction", action="store_true", help="Break down by long/short")
    parser.add_argument("--point-value",  type=int, default=200, help="NT$ per point (default 200)")
    args = parser.parse_args()

    path = Path(args.csv)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(path)
    df["EntryTime"] = pd.to_datetime(df["EntryTime"])
    df["ExitTime"]  = pd.to_datetime(df["ExitTime"])
    df["year"] = df["EntryTime"].dt.year

    print(f"\nFile : {path}")
    print(f"Period: {df['EntryTime'].min().date()} ~ {df['ExitTime'].max().date()}")

    # Overall
    m = compute_metrics(df["PnL"], df["Size"])
    print_metrics(m, label="Overall", point_value=args.point_value)

    # By year
    if args.by_year:
        for year, grp in df.groupby("year"):
            m = compute_metrics(grp["PnL"].reset_index(drop=True), grp["Size"].reset_index(drop=True))
            print_metrics(m, label=str(year), point_value=args.point_value)

    # By direction
    if args.by_direction:
        for label, mask in [("Long", df["Size"] > 0), ("Short", df["Size"] < 0)]:
            grp = df[mask]
            if len(grp):
                m = compute_metrics(grp["PnL"].reset_index(drop=True))
                print_metrics(m, label=label, point_value=args.point_value)


if __name__ == "__main__":
    main()
