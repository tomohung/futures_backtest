#!/usr/bin/env python3
"""Plot intraday 1-min charts for the 8 live Thu/Fri short trades."""
import duckdb
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

# The 8 live Thu/Fri short trades
TRADES = [
    {"date": "2025-02-14", "wd": "Fri", "entry_time": "08:58", "entry_price": 23262, "exit_time": "09:47", "exit_price": 23202, "pnl": 60},
    {"date": "2025-05-22", "wd": "Thu", "entry_time": "09:18", "entry_price": 21492, "exit_time": None, "exit_price": 21415, "pnl": 77},
    {"date": "2025-06-19", "wd": "Thu", "entry_time": "09:04", "entry_price": 21791, "exit_time": "10:05", "exit_price": 21739, "pnl": 52},
    {"date": "2025-06-20", "wd": "Fri", "entry_time": "09:04", "entry_price": 21733, "exit_time": "09:59", "exit_price": 21522, "pnl": 211},
    {"date": "2025-09-26", "wd": "Fri", "entry_time": "09:01", "entry_price": 25926, "exit_time": "10:00", "exit_price": 25565, "pnl": 361},
    {"date": "2025-11-14", "wd": "Fri", "entry_time": "08:59", "entry_price": 27440, "exit_time": None, "exit_price": 27520, "pnl": -80},
    {"date": "2026-01-09", "wd": "Fri", "entry_time": "09:01", "entry_price": 30354, "exit_time": "09:32", "exit_price": 30078, "pnl": 276},
    {"date": "2026-01-30", "wd": "Fri", "entry_time": "09:02", "entry_price": 32423, "exit_time": "09:44", "exit_price": 32237, "pnl": 186},
]

DB_PATH = "data/futures.duckdb"
OUT_PATH = Path("research/active/H045-esthl-live-vs-backtest/results/thu_fri_short_charts.png")


def load_day_bars(conn, date_str):
    """Load day session 1-min bars for a given date."""
    df = conn.execute("""
        SELECT timestamp, open, high, low, close, volume
        FROM ohlcv_1m
        WHERE timestamp::DATE = ?
          AND timestamp::TIME >= '08:45'
          AND timestamp::TIME <= '13:45'
          AND symbol = 'TX'
        ORDER BY timestamp
    """, [date_str]).df()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def main():
    conn = duckdb.connect(DB_PATH, read_only=True)

    fig, axes = plt.subplots(4, 2, figsize=(16, 20))
    fig.suptitle("H045: Thu/Fri Short — 8 Live Trades Intraday", fontsize=14, fontweight="bold")

    for i, trade in enumerate(TRADES):
        ax = axes[i // 2, i % 2]
        bars = load_day_bars(conn, trade["date"])

        if len(bars) == 0:
            ax.set_title(f"{trade['date']} — no data")
            continue

        # Plot candlestick-like using close line + high/low range
        ax.plot(bars["timestamp"], bars["close"], color="black", linewidth=0.8, alpha=0.8)
        ax.fill_between(bars["timestamp"], bars["low"], bars["high"], alpha=0.15, color="gray")

        # Entry marker
        entry_ts = pd.Timestamp(f"{trade['date']} {trade['entry_time']}")
        ax.axhline(trade["entry_price"], color="red", linestyle="--", alpha=0.5, linewidth=0.8)
        ax.plot(entry_ts, trade["entry_price"], marker="v", color="red", markersize=10, zorder=5)

        # Exit marker
        if trade["exit_time"]:
            exit_ts = pd.Timestamp(f"{trade['date']} {trade['exit_time']}")
            ax.plot(exit_ts, trade["exit_price"], marker="^", color="blue", markersize=10, zorder=5)

        # Color based on win/loss
        pnl_color = "green" if trade["pnl"] > 0 else "red"
        title = (f"{trade['date']} ({trade['wd']})  S@{trade['entry_price']}  "
                 f"PnL={trade['pnl']:+d}")
        ax.set_title(title, fontsize=11, color=pnl_color, fontweight="bold")

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.tick_params(axis="x", rotation=30)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PATH, dpi=120, bbox_inches="tight")
    print(f"Chart saved → {OUT_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
