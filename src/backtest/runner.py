import argparse
from pathlib import Path

import duckdb
import numpy as np
from backtesting import Backtest

from src.strategies.orb import ORBStrategy

DB_PATH = "data/futures.duckdb"
OUTPUT_DIR = Path("output")


def build_output_path(start, end, params: dict) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    date_part = start or "all"
    if end:
        date_part += f"_{end}"
    param_part = (
        f"re{params['range_end_minute']}"
        f"_ee{params['entry_end_minute']}"
        f"_sl{int(params['sl_pct']*1000)}"
        f"_tp{params['tp_multiplier']}"
        f"_ta{params['trail_activate_minute']}"
    )
    return OUTPUT_DIR / f"orb_{param_part}_{date_part}.csv"


def print_summary(stats):
    trades = stats["_trades"].copy()
    if trades.empty:
        print("沒有交易記錄")
        return

    pnl = trades["PnL"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    # Max consecutive losses
    max_consec = cur = 0
    for v in (pnl <= 0).tolist():
        cur = cur + 1 if v else 0
        max_consec = max(max_consec, cur)

    # Max drawdown from equity curve
    eq = stats["_equity_curve"]["Equity"]
    max_dd_pct = (eq / eq.cummax() - 1).min() * 100

    rows = [
        ("總交易次數",           f"{len(trades)} 筆"),
        ("做多次數",             f"{(trades['Size'] > 0).sum()} 筆"),
        ("做空次數",             f"{(trades['Size'] < 0).sum()} 筆"),
        ("勝率",                f"{len(wins)/len(trades)*100:.1f}%"),
        ("平均獲利",             f"+{wins.mean():.0f} 點  (NT${wins.mean()*200:,.0f})" if len(wins) else "—"),
        ("平均虧損",             f"{losses.mean():.0f} 點  (NT${losses.mean()*200:,.0f})" if len(losses) else "—"),
        ("獲利因子 (PF)",        f"{wins.sum() / abs(losses.sum()):.2f}" if len(losses) else "∞"),
        ("最大連續虧損次數",      f"{max_consec} 筆"),
        ("最大回撤",             f"{max_dd_pct:.2f}%"),
        ("期望值 (每筆平均損益)", f"{pnl.mean():.1f} 點  (NT${pnl.mean()*200:,.0f})"),
    ]

    col_w = max(len(r[0]) for r in rows)
    print()
    print("=" * 42)
    for label, value in rows:
        print(f"  {label:<{col_w}}  {value}")
    print("=" * 42)


def load_data(start=None, end=None):
    import pandas as pd

    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            ORDER BY timestamp
        """).df()

    df = df.set_index("timestamp")
    df.columns = ["Open", "High", "Low", "Close", "Volume"]

    if start:
        df = df[df.index >= start]
    if end:
        df = df[df.index <= end]

    return df


def main():
    parser = argparse.ArgumentParser(
        description="Run ORB backtest on TX futures",
        epilog=(
            "Examples:\n"
            "  uv run python src/backtest/runner.py --start 2025-01-01\n"
            "  uv run python src/backtest/runner.py --start 2025-06-01 --end 2025-06-30 --resample 1min\n"
            "  uv run python src/backtest/runner.py --start 2025-01-01 --entry-end 90"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Date range
    parser.add_argument("--start", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--end",   default=None, metavar="YYYY-MM-DD")
    # Strategy parameters
    parser.add_argument("--range-end",    type=int,   default=60,   metavar="MIN",
                        help="Opening range end (minutes from 08:00, default 60=09:00)")
    parser.add_argument("--entry-end",    type=int,   default=75,   metavar="MIN",
                        help="Entry cutoff (minutes from 08:00, default 75=09:15)")
    parser.add_argument("--sl",           type=float, default=0.005, metavar="PCT",
                        help="Stop-loss %% (default 0.005)")
    parser.add_argument("--tp",           type=float, default=2.0,  metavar="MULT",
                        help="Take-profit multiplier (default 2.0)")
    parser.add_argument("--trail-after",  type=int,   default=45,   metavar="MIN",
                        help="Trailing stop activation (minutes from 09:00, default 45=09:45)")
    # Chart
    parser.add_argument("--resample", default=None, metavar="FREQ",
                        help="Chart candle size (e.g. '1min', '1h', '1D')")
    args = parser.parse_args()

    strategy_params = {
        "range_end_minute":    args.range_end,
        "entry_end_minute":    args.entry_end,
        "sl_pct":              args.sl,
        "tp_multiplier":       args.tp,
        "trail_activate_minute": args.trail_after,
    }

    resample: str | bool | None = args.resample
    if isinstance(resample, str) and resample.lower() == "false":
        resample = False

    print(f"Loading data from {DB_PATH}...")
    df = load_data(start=args.start, end=args.end)
    print(f"Loaded {len(df):,} bars from {df.index[0]} to {df.index[-1]}")

    bt = Backtest(
        df,
        ORBStrategy,
        cash=200_000,
        commission=0.0,
        trade_on_close=True,
    )

    stats = bt.run(**strategy_params)
    print_summary(stats)

    out_path = build_output_path(args.start, args.end, strategy_params)
    stats["_trades"].to_csv(out_path, index=False)
    print(f"Trades saved → {out_path}")

    plot_kwargs = {} if resample is None else {"resample": resample}
    bt.plot(**plot_kwargs)


if __name__ == "__main__":
    main()
