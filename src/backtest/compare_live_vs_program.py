"""Compare live reversal trades vs programmatic reversal signals.

Find dates where live had profitable reversal trades (>1% of entry price)
but the program did NOT generate a signal.
"""
import pandas as pd
import numpy as np
from backtesting import Backtest
from src.backtest.runner import load_data_for_reversal
from src.strategies.reversal import ReversalStrategy


def load_live_reversal_trades(csv_path):
    """Load live trades, keep only 'reversal' strategy with valid pnl."""
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"])
    # Keep only reversal trades with known pnl
    mask = (df["strategy"] == "reversal") & df["pnl"].notna()
    rev = df[mask].copy()
    rev["pnl"] = pd.to_numeric(rev["pnl"], errors="coerce")
    rev["entry_price"] = pd.to_numeric(rev["entry_price"], errors="coerce")
    rev["pnl_pct"] = rev["pnl"] / rev["entry_price"] * 100
    return rev


def run_program_backtest(start, end):
    """Run reversal strategy backtest, return trades DataFrame."""
    df = load_data_for_reversal(start=start, end=end)
    bt = Backtest(df, ReversalStrategy, cash=200_000,
                  commission=0.0, trade_on_close=True)
    stats = bt.run(vol_ratio=1.2, sl_ema_fraction=0.25, signal_skip=0)
    trades = stats["_trades"].copy()
    trades["entry_date"] = pd.to_datetime(trades["EntryTime"]).dt.normalize()
    trades["pnl_pts"] = trades["ExitPrice"] - trades["EntryPrice"]
    # For shorts, flip sign
    trades.loc[trades["Size"] < 0, "pnl_pts"] = (
        trades.loc[trades["Size"] < 0, "EntryPrice"]
        - trades.loc[trades["Size"] < 0, "ExitPrice"]
    )
    return trades


def main():
    csv_path = "research/archive/confirmed/H044-reversal-live-vs-backtest/data/live_parsed.csv"
    live = load_live_reversal_trades(csv_path)

    # Date range from live data
    start = live["date"].min().strftime("%Y-%m-%d")
    end = live["date"].max().strftime("%Y-%m-%d")
    print(f"Live reversal trades: {len(live)} (from {start} to {end})")
    print(f"  >1% trades: {(live['pnl_pct'].abs() > 1).sum()}")
    print()

    # Run program backtest
    prog = run_program_backtest(start, end)
    prog_dates = set(prog["entry_date"].dt.strftime("%Y-%m-%d"))
    print(f"Program reversal trades: {len(prog)}")
    print()

    # Find live reversal trades > 1% that program missed
    print("=" * 80)
    print("Live reversal trades >1% PnL that program MISSED:")
    print("=" * 80)
    missed = []
    for _, row in live.iterrows():
        date_str = row["date"].strftime("%Y-%m-%d")
        if abs(row["pnl_pct"]) > 1 and date_str not in prog_dates:
            missed.append(row)
            sign = "+" if row["pnl"] > 0 else ""
            exit_p = f"{row['exit_price']:.0f}" if not pd.isna(row["exit_price"]) else "N/A"
            print(f"  {date_str}  {row['direction']}  "
                  f"entry={row['entry_price']:.0f}  exit={exit_p}  "
                  f"pnl={sign}{row['pnl']:.0f} ({sign}{row['pnl_pct']:.2f}%)  "
                  f"exit_strategy={row['exit_strategy']}")

    print(f"\nTotal missed >1%: {len(missed)}")

    # Also show live >1% that program DID capture
    print()
    print("=" * 80)
    print("Live reversal trades >1% PnL that program DID capture:")
    print("=" * 80)
    captured = []
    for _, row in live.iterrows():
        date_str = row["date"].strftime("%Y-%m-%d")
        if abs(row["pnl_pct"]) > 1 and date_str in prog_dates:
            captured.append(row)
            sign = "+" if row["pnl"] > 0 else ""
            prog_match = prog[prog["entry_date"].dt.strftime("%Y-%m-%d") == date_str]
            if len(prog_match) > 0:
                pp = prog_match["pnl_pts"].values[0]
                prog_info = f"prog_pnl={pp:+.0f}"
            else:
                prog_info = "prog_pnl=N/A"
            print(f"  {date_str}  {row['direction']}  "
                  f"live_pnl={sign}{row['pnl']:.0f} ({sign}{row['pnl_pct']:.2f}%)  "
                  f"{prog_info}")

    print(f"\nTotal captured >1%: {len(captured)}")

    # Summary
    total_gt1 = (live["pnl_pct"].abs() > 1).sum()
    print(f"\n{'='*80}")
    print(f"Summary: {len(captured)}/{total_gt1} live >1% reversal trades captured by program")
    print(f"         {len(missed)}/{total_gt1} missed")


if __name__ == "__main__":
    main()
