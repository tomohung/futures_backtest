import argparse

import duckdb
from backtesting import Backtest

from src.strategies.orb import ORBStrategy

DB_PATH = "data/futures.duckdb"


def load_data(start: str | None = None, end: str | None = None) -> "pd.DataFrame":
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
            "For 1m chart review, limit to ~1–2 weeks:\n"
            "  uv run python src/backtest/runner.py --start 2025-06-01 --end 2025-06-30 --resample 1min"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--start", default=None, metavar="YYYY-MM-DD",
                        help="Start date (inclusive). Default: all available data.")
    parser.add_argument("--end", default=None, metavar="YYYY-MM-DD",
                        help="End date (inclusive). Default: all available data.")
    parser.add_argument("--resample", default=None, metavar="FREQ",
                        help=(
                            "Chart candle size for the plot (e.g. '1min', '5min', '1h', '1D'). "
                            "Use '1min' with a short date range to inspect individual bars. "
                            "Omit to let backtesting.py choose automatically."
                        ))
    args = parser.parse_args()

    # Convert string 'False' / 'false' to bool so --resample False works intuitively
    resample: str | bool | None = args.resample
    if isinstance(resample, str) and resample.lower() == "false":
        resample = False

    print(f"Loading data from {DB_PATH}...")
    df = load_data(start=args.start, end=args.end)
    print(f"Loaded {len(df):,} bars from {df.index[0]} to {df.index[-1]}")

    bt = Backtest(
        df,
        ORBStrategy,
        cash=1_000_000,
        commission=50 / 350_000,  # ~NT$50/lot, contract value ~NT$350,000
        trade_on_close=True,
    )

    stats = bt.run()
    print(stats)

    plot_kwargs = {} if resample is None else {"resample": resample}
    bt.plot(**plot_kwargs)


if __name__ == "__main__":
    main()
