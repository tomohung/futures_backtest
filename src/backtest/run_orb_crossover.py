"""
Standalone runner for ORB crossover experiments.

Direction A: EstHL entry × ORBLong exit (--direction a)
  uv run python src/backtest/run_orb_crossover.py --direction a --start 2021-01-01

Direction B: ORBLong entry × EstHL exit (--direction b, default)
  uv run python src/backtest/run_orb_crossover.py --start 2021-01-01
"""

import argparse
from pathlib import Path

from backtesting import Backtest

from src.backtest.runner import load_data_for_orb_est_hl, print_summary
from src.strategies.orb_crossover import (
    EstHLEntryORBLongExitStrategy,
    ORBLongWithEstHLExitStrategy,
)

OUTPUT_DIR = Path("output")


def main():
    parser = argparse.ArgumentParser(
        description="Run ORB crossover backtest",
        epilog=(
            "Examples:\n"
            "  uv run python src/backtest/run_orb_crossover.py --direction a --start 2021-01-01\n"
            "  uv run python src/backtest/run_orb_crossover.py --direction b --start 2025-01-01\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--direction", choices=["a", "b"], default="b",
                        help="a=EstHL entry×ORBLong exit, b=ORBLong entry×EstHL exit")
    parser.add_argument("--start", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--end",   default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--sl-fraction", type=float, default=0.25,
                        help="Direction B: SL = fraction × EmaHL (default 0.25)")
    parser.add_argument("--sl-pct", type=float, default=0.004,
                        help="Direction A: fixed SL percentage (default 0.004)")
    parser.add_argument("--tp-multiplier", type=float, default=3.0,
                        help="Direction A: TP = entry + mult × OR width (default 3.0)")
    parser.add_argument("--bigcost-days", type=int, default=2,
                        help="Direction A: BigCost lookback days (default 2)")
    parser.add_argument("--entry-end", type=int, default=15,
                        help="Direction A: entry window end minute past 09:00 (default 15 → 09:15)")
    parser.add_argument("--short", action="store_true",
                        help="Also take short trades (default: long-only)")
    parser.add_argument("--plot", action="store_true",
                        help="Show backtesting.py chart after run")
    args = parser.parse_args()

    print("Loading data...")
    df = load_data_for_orb_est_hl(start=args.start, end=args.end)
    print(f"Loaded {len(df):,} bars  [{df.index[0]} → {df.index[-1]}]")

    if args.direction == "a":
        bt = Backtest(df, EstHLEntryORBLongExitStrategy,
                      cash=200_000, commission=0.0, trade_on_close=True)
        stats = bt.run(sl_pct=args.sl_pct, tp_or_multiplier=args.tp_multiplier,
                       bigcost_days=args.bigcost_days, entry_end_minute=args.entry_end,
                       long_only=not args.short)
        label = "a"
    else:
        bt = Backtest(df, ORBLongWithEstHLExitStrategy,
                      cash=200_000, commission=0.0, trade_on_close=True)
        stats = bt.run(sl_ema_fraction=args.sl_fraction, long_only=not args.short)
        label = "b"

    print_summary(stats)

    OUTPUT_DIR.mkdir(exist_ok=True)
    date_part = (args.start or "all")
    if args.end:
        date_part += f"_{args.end}"
    out_path = OUTPUT_DIR / f"orb_crossover_{label}_{date_part}.csv"
    stats["_trades"].to_csv(out_path, index=False)
    print(f"Trades saved → {out_path}")

    if args.plot:
        bt.plot()


if __name__ == "__main__":
    main()
