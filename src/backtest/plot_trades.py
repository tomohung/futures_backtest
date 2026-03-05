#!/usr/bin/env python3
"""Plot Ph4 Long-only trades on an interactive candlestick chart.

Usage:
    uv run python src/backtest/plot_trades.py                    # 2026 YTD
    uv run python src/backtest/plot_trades.py --year 2025
    uv run python src/backtest/plot_trades.py --start 2025-06-01 --end 2025-06-30
    uv run python src/backtest/plot_trades.py --year 2025 --resample 5min
"""
import argparse
import sys
from pathlib import Path

from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_with_night_ma
from src.strategies.orb import ORBLongStrategy

STRATEGY_PARAMS = dict(
    tp_or_multiplier=1.5,
    sl_pct=0.004,
    long_only=1,
)

YEAR_RANGES = {
    "2021": ("2021-01-01", "2021-12-31"),
    "2022": ("2022-01-01", "2022-12-31"),
    "2023": ("2023-01-01", "2023-12-31"),
    "2024": ("2024-01-01", "2024-12-31"),
    "2025": ("2025-01-01", "2025-12-31"),
    "2026": ("2026-01-01", None),
}


def main():
    parser = argparse.ArgumentParser(description="Plot Ph4 Long-only trades")
    parser.add_argument("--year",  default=None, choices=YEAR_RANGES.keys())
    parser.add_argument("--start", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--end",   default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--resample", default="5min", metavar="FREQ",
                        help="Candle size for chart (default: 5min)")
    args = parser.parse_args()

    if args.year:
        start, end = YEAR_RANGES[args.year]
    elif args.start:
        start, end = args.start, args.end
    else:
        start, end = "2026-01-01", None  # YTD default

    print(f"Loading data {start} ~ {end or 'latest'}...")
    df = load_data_with_night_ma(start=start, end=end, trend_ma_days=10)
    print(f"  {len(df):,} bars  {df.index[0].date()} ~ {df.index[-1].date()}")

    bt = Backtest(df, ORBLongStrategy,
                  cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**STRATEGY_PARAMS)

    trades = stats["_trades"]
    pnl = trades["PnL"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    print(f"\n  Trades: {len(trades)}  Win: {len(wins)/len(trades)*100:.1f}%  "
          f"PF: {wins.sum()/abs(losses.sum()):.2f}  "
          f"Total: {pnl.sum():+.0f} pts")
    print(f"\nOpening chart ({args.resample} candles)...")
    bt.plot(resample=args.resample, superimpose=False)


if __name__ == "__main__":
    main()
