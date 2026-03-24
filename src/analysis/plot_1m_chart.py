"""Generate 1-minute candlestick charts for day session with Bollinger Bands."""

import duckdb
import mplfinance as mpf
import pandas as pd
from pathlib import Path

BB_PERIOD = 15
BB_STD = 2


def plot_day(conn, trade_date: str, output_dir: Path):
    """Plot 1-min candles + BB(15) for a single day session (08:45-13:45)."""
    df = conn.sql(f"""
        SELECT timestamp, open, high, low, close, volume
        FROM ohlcv_1m
        WHERE timestamp::DATE = '{trade_date}'
          AND symbol = 'TX'
          AND timestamp::TIME BETWEEN '08:45:00' AND '13:44:00'
        ORDER BY timestamp
    """).df()

    if df.empty:
        print(f"  {trade_date}: no data, skipping")
        return

    df.set_index("timestamp", inplace=True)
    df.index = pd.DatetimeIndex(df.index)

    # Bollinger Bands
    bb_mid = df["close"].rolling(BB_PERIOD).mean()
    bb_std = df["close"].rolling(BB_PERIOD).std()
    bb_upper = bb_mid + BB_STD * bb_std
    bb_lower = bb_mid - BB_STD * bb_std

    bb_plots = [
        mpf.make_addplot(bb_upper, color="blue", width=0.8, linestyle="--"),
        mpf.make_addplot(bb_mid, color="orange", width=0.8),
        mpf.make_addplot(bb_lower, color="blue", width=0.8, linestyle="--"),
    ]

    # Weekday label
    dt = pd.Timestamp(trade_date)
    wd = dt.strftime("%a")  # Mon, Tue, ...
    title = f"TX 1-min   {trade_date} ({wd})   BB({BB_PERIOD},{BB_STD})"

    out_path = output_dir / f"1m_{trade_date}.png"
    mpf.plot(
        df,
        type="candle",
        style="charles",
        title=title,
        volume=True,
        addplot=bb_plots,
        figsize=(16, 8),
        savefig=dict(fname=str(out_path), dpi=120, bbox_inches="tight"),
    )
    print(f"  {trade_date}: saved → {out_path.name}")


def main():
    dates = [
        # January
        "2025-01-02", "2025-01-10", "2025-01-14", "2025-01-21",
        # February
        "2025-02-03", "2025-02-04", "2025-02-07", "2025-02-14", "2025-02-21",
        # March
        "2025-03-03", "2025-03-04", "2025-03-06", "2025-03-12", "2025-03-13",
        "2025-03-17", "2025-03-18", "2025-03-21", "2025-03-25", "2025-03-27", "2025-03-31",
        # April
        "2025-04-15", "2025-04-16", "2025-04-22", "2025-04-29",
        # June
        "2025-06-02", "2025-06-18", "2025-06-27",
        # October
        "2025-10-15",
        # November
        "2025-11-05", "2025-11-11", "2025-11-14", "2025-11-20", "2025-11-25", "2025-11-27",
    ]

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    conn = duckdb.connect("data/futures.duckdb", read_only=True)
    try:
        for d in dates:
            plot_day(conn, d, output_dir)
    finally:
        conn.close()

    print(f"\nDone: {len(dates)} dates processed.")


if __name__ == "__main__":
    main()
