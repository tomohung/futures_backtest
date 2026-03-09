"""
Standalone runner for ORBWithEstHLExitStrategy.

Usage:
    uv run python src/backtest/run_orb_est_hl.py --start 2025-01-01
    uv run python src/backtest/run_orb_est_hl.py --start 2022-01-01 --end 2026-03-09
"""

import argparse
from pathlib import Path

from backtesting import Backtest

from src.backtest.runner import load_data_for_orb_est_hl, print_summary
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy

OUTPUT_DIR = Path("output")


def main():
    parser = argparse.ArgumentParser(
        description="Run ORBWithEstHLExitStrategy backtest",
        epilog=(
            "Examples:\n"
            "  uv run python src/backtest/run_orb_est_hl.py --start 2025-01-01\n"
            "  uv run python src/backtest/run_orb_est_hl.py --start 2022-01-01 --end 2026-03-09\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--start", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--end",   default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--sl-fraction", type=float, default=0.25,
                        help="SL = fraction × EmaHL (default 0.25)")
    parser.add_argument("--adx-min", type=float, default=0.0,
                        help="Minimum daily ADX to trade (0 = disabled)")
    parser.add_argument("--bigcost-days", type=int, default=2,
                        help="BigCost lookback days 1–5 (default 2)")
    parser.add_argument("--short", action="store_true",
                        help="Also take short trades (default: long-only)")
    parser.add_argument("--plot", action="store_true",
                        help="Show backtesting.py chart after run")
    args = parser.parse_args()

    print("Loading data...")
    df = load_data_for_orb_est_hl(start=args.start, end=args.end)
    print(f"Loaded {len(df):,} bars  [{df.index[0]} → {df.index[-1]}]")

    bt = Backtest(
        df,
        ORBWithEstHLExitStrategy,
        cash=200_000,
        commission=0.0,
        trade_on_close=True,
    )

    stats = bt.run(sl_ema_fraction=args.sl_fraction,
                   adx_min=args.adx_min,
                   long_only=not args.short,
                   bigcost_days=args.bigcost_days)
    print_summary(stats)

    OUTPUT_DIR.mkdir(exist_ok=True)
    date_part = (args.start or "all")
    if args.end:
        date_part += f"_{args.end}"
    out_path = OUTPUT_DIR / f"orb_est_hl_{date_part}.csv"
    stats["_trades"].to_csv(out_path, index=False)
    print(f"Trades saved → {out_path}")

    if args.plot:
        bt.plot()


if __name__ == "__main__":
    main()
