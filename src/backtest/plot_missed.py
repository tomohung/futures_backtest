"""Plot 1m charts for 6 missed reversal dates with key indicators."""
import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from src.backtest.runner import load_data_for_reversal

import matplotlib.font_manager as fm
# Force CJK font
for _f in fm.fontManager.ttflist:
    if _f.name == "Heiti TC":
        matplotlib.rcParams["font.family"] = _f.name
        break
else:
    matplotlib.rcParams["font.sans-serif"] = ["Arial Unicode MS", "Heiti TC", "sans-serif"]

MISSED = [
    ("2024-11-05", "B", 22869, 23105, "No BB touch"),
    ("2025-03-31", "S", 21026, 20753, "CCD wrong dir (2xBB bypass?)"),
    ("2025-04-15", "B", 19565, 19814, "CCD wrong dir"),
    ("2025-04-29", "B", 19982, 20184, "Near-SatZone latch"),
    ("2025-10-15", "B", 26862, 27134, "Near-SatZone latch"),
    ("2025-11-04", "S", 28570, 28241, "BC Zone + MA dir opposite"),
]


def plot_date(df, date_str, live_dir, entry_p, exit_p, reason, ax):
    date = pd.Timestamp(date_str)
    day = df[df.index.normalize() == date]
    if day.empty:
        ax.set_title(f"{date_str} — NO DATA")
        return

    # Limit to 08:45 ~ 11:00 for clarity
    day = day.between_time("08:45", "11:00")
    t = day.index

    # Candlestick-like: plot close as line, shade high-low
    ax.fill_between(t, day["Low"], day["High"], alpha=0.15, color="gray")
    ax.plot(t, day["Close"], color="black", linewidth=0.8, label="Close")

    # BB bands
    ax.plot(t, day["BB_Upper"], color="blue", linewidth=0.5, linestyle="--", alpha=0.6, label="BB Upper")
    ax.plot(t, day["BB_Lower"], color="blue", linewidth=0.5, linestyle="--", alpha=0.6, label="BB Lower")

    # MA5 1m
    ax.plot(t, day["MA5_1m"], color="orange", linewidth=0.7, alpha=0.8, label="MA5_1m")

    # SatZone
    sat_u = day["SatZoneUpper"].dropna()
    sat_l = day["SatZoneLower"].dropna()
    if len(sat_u) > 0:
        ax.axhline(sat_u.iloc[0], color="red", linewidth=0.7, linestyle=":", alpha=0.5, label="SatZone")
    if len(sat_l) > 0:
        ax.axhline(sat_l.iloc[0], color="green", linewidth=0.7, linestyle=":", alpha=0.5)

    # Entry window shading
    entry_start = pd.Timestamp(f"{date_str} 09:10")
    entry_end = pd.Timestamp(f"{date_str} 10:05")
    ax.axvspan(entry_start, entry_end, alpha=0.05, color="yellow")

    # Live entry/exit
    if not np.isnan(entry_p):
        ax.axhline(entry_p, color="purple", linewidth=1, linestyle="-", alpha=0.7)
        ax.text(t[0], entry_p, f" entry {entry_p:.0f}", fontsize=7, color="purple",
                va="bottom" if live_dir == "B" else "top")
    if not np.isnan(exit_p):
        ax.axhline(exit_p, color="darkgreen", linewidth=1, linestyle="-", alpha=0.7)
        ax.text(t[0], exit_p, f" exit {exit_p:.0f}", fontsize=7, color="darkgreen",
                va="bottom" if live_dir == "S" else "top")

    # Direction arrow
    arrow = "↑ Long" if live_dir == "B" else "↓ Short"

    ax.set_title(f"{date_str}  {arrow}  |  blocked: {reason}", fontsize=9, fontweight="bold")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.tick_params(axis="both", labelsize=7)
    ax.grid(True, alpha=0.3)


def main():
    print("Loading data...")
    df = load_data_for_reversal(start="2024-11-01", end="2025-12-31")
    print(f"Loaded {len(df)} bars, plotting...")

    fig, axes = plt.subplots(3, 2, figsize=(16, 14))
    fig.suptitle("Reversal: 6 missed live trades (>1% PnL)", fontsize=13, fontweight="bold")

    for i, (date_str, d, ep, xp, reason) in enumerate(MISSED):
        ax = axes[i // 2][i % 2]
        plot_date(df, date_str, d, ep, xp, reason, ax)

    plt.tight_layout()
    out = "output/missed_reversal_6dates.png"
    plt.savefig(out, dpi=150)
    print(f"Saved → {out}")
    plt.close()


if __name__ == "__main__":
    main()
