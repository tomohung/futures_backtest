"""Generate 1-minute candlestick charts with Reversal strategy indicators.

Indicators plotted:
  Price panel: BB(15,2), MA5(1m), SatZone Upper/Lower, BigCost1/2, VWAP
  Volume panel: VolMA20
  Sub-panel: CCD_5m
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

    # --- Price panel overlays ---
    add_plots = []

    # BB(15,2)
    add_plots.append(mpf.make_addplot(day["BB_Upper"], color="#4488cc", width=0.7, linestyle="--"))
    add_plots.append(mpf.make_addplot(day["BB_Middle"], color="#cc8844", width=0.7))
    add_plots.append(mpf.make_addplot(day["BB_Lower"], color="#4488cc", width=0.7, linestyle="--"))

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

    # BigCost1 / BigCost2
    if "BigCost1" in day.columns and day["BigCost1"].notna().any():
        add_plots.append(mpf.make_addplot(
            day["BigCost1"], color="#ff6600", width=1.0, linestyle="-", alpha=0.7))
    if "BigCost2" in day.columns and day["BigCost2"].notna().any():
        add_plots.append(mpf.make_addplot(
            day["BigCost2"], color="#ff6600", width=1.0, linestyle="--", alpha=0.5))

    # --- Volume panel: VolMA20 ---
    if "VolMA20" in day.columns:
        add_plots.append(mpf.make_addplot(
            day["VolMA20"], panel=1, color="blue", width=0.8, secondary_y=False))

    # --- CCD_5m sub-panel ---
    if "CCD_5m" in day.columns:
        ccd = day["CCD_5m"].copy()
        ccd_colors = np.where(ccd >= 0, "#00aa00", "#cc0000")
        add_plots.append(mpf.make_addplot(
            ccd, panel=2, type="bar", color=list(ccd_colors), width=0.7,
            ylabel="CCD"))

    # Title
    wd = date_ts.strftime("%a")
    title = f"TX Reversal   {trade_date} ({wd})"

    out_path = output_dir / f"1m_{trade_date}.png"
    mpf.plot(
        day,
        type="candle",
        style="charles",
        title=title,
        volume=True,
        addplot=add_plots,
        figsize=(18, 10),
        panel_ratios=(5, 1, 1),
        savefig=dict(fname=str(out_path), dpi=120, bbox_inches="tight"),
    )
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
