import argparse

import duckdb
from backtesting import Backtest

from src.strategies.orb import ORBStrategy

DB_PATH = "data/futures.duckdb"


def load_data(start: str | None = None) -> "pd.DataFrame":
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

    return df


def main():
    parser = argparse.ArgumentParser(description="Run ORB backtest on TX futures")
    parser.add_argument(
        "--start",
        default=None,
        metavar="YYYY-MM-DD",
        help="Start date filter (inclusive). Default: use all available data.",
    )
    args = parser.parse_args()

    print(f"Loading data from {DB_PATH}...")
    df = load_data(start=args.start)
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
    bt.plot()


if __name__ == "__main__":
    main()
