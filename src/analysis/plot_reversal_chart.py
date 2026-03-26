"""Generate 1-minute candlestick charts with Reversal strategy indicators.

Indicators plotted:
  Price panel: MA5(1m), SatZone Upper/Lower, VWAP1/2, VWAP
  Volume panel: VolMA20
  Sub-panels: BB%(15,2), CCD_5m
"""

import mplfinance as mpf
import numpy as np
import pandas as pd
from pathlib import Path


DATES = [
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


def compute_vwap(day_df):
    """Compute intraday VWAP (cumulative)."""
    cum_vol = day_df["Volume"].cumsum()
    cum_pv = (day_df["Close"] * day_df["Volume"]).cumsum()
    vwap = cum_pv / cum_vol
    vwap[cum_vol == 0] = np.nan
    return vwap


def plot_day(df_all, trade_date: str, output_dir: Path):
    """Plot 1-min candles with full Reversal indicators for one day."""
    date_ts = pd.Timestamp(trade_date)
    mask = df_all.index.normalize() == date_ts
    day = df_all.loc[mask].copy()

    if day.empty:
        print(f"  {trade_date}: no data, skipping")
        return

    # Trim to 08:45 - 13:44 for display
    day = day.between_time("08:45", "13:44")
    if day.empty:
        return

    # VWAP (computed per day from raw close/volume)
    vwap = compute_vwap(day)

    # BB% = (Close - BB_Lower) / (BB_Upper - BB_Lower)
    bb_width = day["BB_Upper"] - day["BB_Lower"]
    bb_pct = (day["Close"] - day["BB_Lower"]) / bb_width
    bb_pct[bb_width == 0] = np.nan

    # --- Price panel overlays ---
    add_plots = []

    # MA5(1m)
    add_plots.append(mpf.make_addplot(day["MA5_1m"], color="#e040e0", width=0.8, alpha=0.8))

    # VWAP
    add_plots.append(mpf.make_addplot(vwap, color="#00aa00", width=1.0, linestyle="-."))

    # SatZone Upper / Lower
    if "SatZoneUpper" in day.columns:
        add_plots.append(mpf.make_addplot(
            day["SatZoneUpper"], color="red", width=1.2, linestyle=":", alpha=0.9))
    if "SatZoneLower" in day.columns:
        add_plots.append(mpf.make_addplot(
            day["SatZoneLower"], color="red", width=1.2, linestyle=":", alpha=0.9))

    # VWAP1 / VWAP2
    if "VWAP1" in day.columns and day["VWAP1"].notna().any():
        add_plots.append(mpf.make_addplot(
            day["VWAP1"], color="#ff6600", width=1.0, linestyle="-", alpha=0.7))
    if "VWAP2" in day.columns and day["VWAP2"].notna().any():
        add_plots.append(mpf.make_addplot(
            day["VWAP2"], color="#ff6600", width=1.0, linestyle="--", alpha=0.5))

    # --- Volume panel: VolMA20 ---
    if "VolMA20" in day.columns:
        add_plots.append(mpf.make_addplot(
            day["VolMA20"], panel=1, color="blue", width=0.8, secondary_y=False))

    # --- BB% sub-panel (panel 2) ---
    add_plots.append(mpf.make_addplot(
        bb_pct, panel=2, color="#4488cc", width=1.0,
        secondary_y=False, ylabel="BB%"))

    # --- CCD_5m sub-panel (panel 3) ---
    if "CCD_5m" in day.columns:
        ccd = day["CCD_5m"].copy()
        ccd_colors = np.where(ccd >= 0, "red", "green")
        add_plots.append(mpf.make_addplot(
            ccd, panel=3, type="bar", color=list(ccd_colors), width=0.7,
            ylabel="CCD"))

    # Title
    wd = date_ts.strftime("%a")
    title = f"TX Reversal   {trade_date} ({wd})"

    # Taiwan convention: up=red, down=green
    mc = mpf.make_marketcolors(
        up="red", down="green", edge="inherit", wick="inherit",
        volume={"up": "red", "down": "green"},
    )
    style = mpf.make_mpf_style(marketcolors=mc)

    out_path = output_dir / f"1m_{trade_date}.png"
    fig, axes = mpf.plot(
        day,
        type="candle",
        style=style,
        title=title,
        volume=True,
        addplot=add_plots,
        figsize=(18, 10),
        panel_ratios=(5, 1, 2, 1.5),
        returnfig=True,
    )

    # Draw BB% reference lines; hide spurious right y-axis
    # axes layout: [price, price_right, vol, vol_right, bb%, bb%_right, ccd, ccd_right]
    bb_ax = axes[4]
    bb_ax.axhline(0.0, color="gray", linewidth=0.5, linestyle="--")
    bb_ax.axhline(1.0, color="gray", linewidth=0.5, linestyle="--")
    axes[5].set_yticks([])  # hide BB% right y-axis

    fig.savefig(str(out_path), dpi=120, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)
    print(f"  {trade_date}: saved")


def main():
    from src.backtest.runner import load_data_for_reversal

    # Load full dataset with all pre-computed indicators
    print("Loading reversal indicators...")
    df = load_data_for_reversal(start="2025-01-01", end="2025-12-31")
    print(f"  Loaded {len(df):,} bars, columns: {list(df.columns)}")

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    for d in DATES:
        plot_day(df, d, output_dir)

    print(f"\nDone: {len(DATES)} dates processed.")


if __name__ == "__main__":
    main()
