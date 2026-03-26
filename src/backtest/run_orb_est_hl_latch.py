"""
Standalone runner for ORBEstHLLatchStrategy.

Usage:
    uv run python src/backtest/run_orb_est_hl_latch.py --start 2021-01-01
    uv run python src/backtest/run_orb_est_hl_latch.py --start 2021-01-01 --confirm-mode 1
"""

import argparse
from pathlib import Path

from backtesting import Backtest

from src.backtest.runner import load_data_for_orb_est_hl, print_summary
from src.strategies.orb_est_hl_latch import ORBEstHLLatchStrategy

OUTPUT_DIR = Path("output")


def main():
    parser = argparse.ArgumentParser(
        description="Run ORBEstHLLatchStrategy backtest",
        epilog=(
            "Examples:\n"
            "  uv run python src/backtest/run_orb_est_hl_latch.py --start 2021-01-01\n"
            "  uv run python src/backtest/run_orb_est_hl_latch.py --start 2021-01-01 --confirm-mode 1\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--start", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--end",   default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--confirm-mode", type=int, default=0, choices=[0, 1],
                        help="0=any_bar new high, 1=5min candle close new high (default 0)")
    parser.add_argument("--latch-entry-end", type=int, default=630,
                        help="Latch confirmation deadline in minutes since midnight (default 630=10:30)")
    parser.add_argument("--sl-fraction", type=float, default=0.25,
                        help="SL = fraction × EmaHL (default 0.25)")
    parser.add_argument("--adx-min", type=float, default=0.0,
                        help="Minimum daily ADX to trade (0 = disabled)")
    parser.add_argument("--vwap-days", type=int, default=2,
                        help="VWAP lookback days 1–5 (default 2)")
    parser.add_argument("--short", action="store_true",
                        help="Also take short trades (default: long-only)")
    parser.add_argument("--no-skip-thursday", action="store_true",
                        help="Allow trading on Thursdays (default: skip)")
    parser.add_argument("--no-skip-friday", action="store_true",
                        help="Allow trading on Fridays (default: skip)")
    parser.add_argument("--plot", action="store_true",
                        help="Show backtesting.py chart after run")
    args = parser.parse_args()

    print("Loading data...")
    df = load_data_for_orb_est_hl(start=args.start, end=args.end)
    print(f"Loaded {len(df):,} bars  [{df.index[0]} → {df.index[-1]}]")

    mode_name = "any_bar" if args.confirm_mode == 0 else "5min_close"
    print(f"Confirm mode: {mode_name}  |  Latch deadline: {args.latch_entry_end // 60}:{args.latch_entry_end % 60:02d}")

    bt = Backtest(
        df,
        ORBEstHLLatchStrategy,
        cash=200_000,
        commission=0.0,
        trade_on_close=True,
    )

    stats = bt.run(
        sl_ema_fraction=args.sl_fraction,
        adx_min=args.adx_min,
        long_only=not args.short,
        vwap_days=args.vwap_days,
        skip_thursday=not args.no_skip_thursday,
        skip_friday=not args.no_skip_friday,
        confirm_mode=args.confirm_mode,
        latch_entry_end_min=args.latch_entry_end,
    )
    print_summary(stats)

    OUTPUT_DIR.mkdir(exist_ok=True)
    date_part = (args.start or "all")
    if args.end:
        date_part += f"_{args.end}"
    out_path = OUTPUT_DIR / f"orb_est_hl_latch_{mode_name}_{date_part}.csv"
    stats["_trades"].to_csv(out_path, index=False)
    print(f"Trades saved → {out_path}")

    if args.plot:
        bt.plot()


if __name__ == "__main__":
    main()
