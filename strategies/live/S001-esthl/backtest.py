#!/usr/bin/env python3
"""S001 EstHL — 可重跑回測腳本。

使用 ORBWithEstHLExitStrategy，參數對應 spec.md 的 live 設定。

Usage:
    uv run python strategies/live/S001-esthl/backtest.py
    uv run python strategies/live/S001-esthl/backtest.py --start 2025-01-01
    uv run python strategies/live/S001-esthl/backtest.py --start 2021-01-01 --end 2024-12-31
"""

import argparse
from pathlib import Path

from backtesting import Backtest

from src.backtest.runner import load_data_for_orb_est_hl, print_summary
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy

OUTPUT_DIR = Path("output")

# Live 參數（from spec.md）
LIVE_PARAMS = dict(
    sl_ema_fraction=0.25,
    adx_min=0.0,
    long_only=True,       # long-only
    vwap_days=2,
    skip_thursday=True,
    skip_friday=True,
)


def main():
    parser = argparse.ArgumentParser(description="S001 EstHL backtest")
    parser.add_argument("--start", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--end",   default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--plot",  action="store_true")
    args = parser.parse_args()

    print("Loading data...")
    df = load_data_for_orb_est_hl(start=args.start, end=args.end)
    print(f"Loaded {len(df):,} bars  [{df.index[0]} → {df.index[-1]}]")

    bt = Backtest(df, ORBWithEstHLExitStrategy,
                  cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**LIVE_PARAMS)
    print_summary(stats)

    OUTPUT_DIR.mkdir(exist_ok=True)
    date_part = (args.start or "all")
    if args.end:
        date_part += f"_{args.end}"
    out_path = OUTPUT_DIR / f"s001_esthl_{date_part}.csv"
    stats["_trades"].to_csv(out_path, index=False)
    print(f"Trades saved → {out_path}")

    if args.plot:
        bt.plot()


if __name__ == "__main__":
    main()
