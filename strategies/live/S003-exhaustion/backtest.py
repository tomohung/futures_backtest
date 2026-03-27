#!/usr/bin/env python3
"""S003 Exhaustion — 可重跑回測腳本。

使用 ExhaustionStrategy，參數對應 spec.md 的 live 設定。

Usage:
    uv run python strategies/live/S003-exhaustion/backtest.py
    uv run python strategies/live/S003-exhaustion/backtest.py --start 2025-01-01
    uv run python strategies/live/S003-exhaustion/backtest.py --start 2021-01-01 --end 2024-12-31
"""

import argparse
from pathlib import Path

from backtesting import Backtest

from src.backtest.runner import load_data_for_exhaustion, print_summary
from src.strategies.exhaustion import ExhaustionStrategy

OUTPUT_DIR = Path("output")

# Live 參數（from spec.md）
LIVE_PARAMS = dict(
    sl_fraction=0.25,
    min_orb_pct=0.25,
    skip_wed=True,
    skip_thu=True,
)


def main():
    parser = argparse.ArgumentParser(description="S003 Exhaustion backtest")
    parser.add_argument("--start", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--end",   default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--plot",  action="store_true")
    args = parser.parse_args()

    print("Loading data...")
    df = load_data_for_exhaustion(start=args.start, end=args.end)
    print(f"Loaded {len(df):,} bars  [{df.index[0]} → {df.index[-1]}]")

    bt = Backtest(df, ExhaustionStrategy,
                  cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**LIVE_PARAMS)
    print_summary(stats)

    OUTPUT_DIR.mkdir(exist_ok=True)
    date_part = (args.start or "all")
    if args.end:
        date_part += f"_{args.end}"
    out_path = OUTPUT_DIR / f"s003_exhaustion_{date_part}.csv"
    stats["_trades"].to_csv(out_path, index=False)
    print(f"Trades saved → {out_path}")

    if args.plot:
        bt.plot()


if __name__ == "__main__":
    main()
