#!/usr/bin/env python3
"""
H038 Phase 1: BB Touch + Structural Support Confluence

For each BB touch event during the Reversal setup window:
1. Compute lookahead-free S/R (prior 30 days' 30m swing + VP)
2. Measure distance to nearest S/R
3. Track whether reversal trigger (MA5 cross) fires and subsequent MFE
4. Compare confluence vs non-confluence groups
"""
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

sys.path.insert(0, str(Path(__file__).parents[3]))
from src.backtest.runner import load_data_for_reversal

DB_PATH = str(Path(__file__).parents[3] / "data" / "futures.duckdb")
SYMBOL = "TX"

# ── Parameters ──────────────────────────────────────────────────────
SETUP_START = "08:45"
SETUP_END   = "10:05"
ENTRY_START = "09:10"
ENTRY_END   = "10:05"
LOOKBACK_DAYS = 30          # S/R lookback
TRIGGER_WINDOW = 20         # bars after BB touch to look for MA5 cross
MFE_WINDOW = 60             # bars after trigger to measure max favorable excursion
THRESHOLDS = [0.25, 0.33, 0.5, 0.67]  # confluence distance as fraction of EmaHL


def load_30m_bars_all():
    """Load all day-session 30m bars for S/R calculation."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT
                CASE
                    WHEN time_bucket(INTERVAL '30 minutes', timestamp,
                         TIMESTAMP '2000-01-01 08:45:00')::TIME = '13:45:00'
                    THEN time_bucket(INTERVAL '30 minutes', timestamp,
                         TIMESTAMP '2000-01-01 08:45:00') - INTERVAL '30 minutes'
                    ELSE time_bucket(INTERVAL '30 minutes', timestamp,
                         TIMESTAMP '2000-01-01 08:45:00')
                END AS ts,
                MAX(high)::FLOAT AS high,
                MIN(low)::FLOAT  AS low,
                SUM(volume)::FLOAT AS volume
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            GROUP BY ts
            ORDER BY ts
        """, [SYMBOL]).df()
    df["date"] = pd.to_datetime(df["ts"]).dt.date
    return df


def calc_sr_for_date(bars_30m, target_date, lookback_days=30,
                     swing_window=3, cluster_dist=100, bin_size=50):
    """Calculate S/R levels using 30m bars from prior `lookback_days` days (no lookahead)."""
    cutoff = pd.Timestamp(target_date)
    bars = bars_30m[pd.to_datetime(bars_30m["ts"]) < cutoff]
    # Keep only last lookback_days trading days
    unique_dates = sorted(bars["date"].unique())
    if len(unique_dates) > lookback_days:
        unique_dates = unique_dates[-lookback_days:]
        bars = bars[bars["date"].isin(set(unique_dates))]

    if len(bars) < 20:
        return []

    highs = bars["high"].values
    lows = bars["low"].values
    vols = bars["volume"].values
    n = len(bars)

    # Swing High/Low
    levels = []
    for i in range(swing_window, n - swing_window):
        window_h = highs[i - swing_window:i + swing_window + 1]
        window_l = lows[i - swing_window:i + swing_window + 1]
        if highs[i] == max(window_h):
            levels.append(float(highs[i]))
        if lows[i] == min(window_l):
            levels.append(float(lows[i]))

    # Cluster
    def cluster(lvls):
        if not lvls:
            return []
        lvls = sorted(lvls)
        groups = [[lvls[0]]]
        for lv in lvls[1:]:
            if lv - groups[-1][-1] <= cluster_dist:
                groups[-1].append(lv)
            else:
                groups.append([lv])
        return [np.mean(g) for g in groups]

    swing_levels = cluster(levels)

    # Volume Profile HVN
    price_min = int(min(lows) // bin_size * bin_size)
    price_max = int(max(highs) // bin_size * bin_size + bin_size)
    bins = np.arange(price_min, price_max + bin_size, bin_size)
    vp = np.zeros(len(bins))

    for i in range(n):
        lo, hi, vol = lows[i], highs[i], vols[i]
        idx = [j for j, b in enumerate(bins) if b < hi and b + bin_size > lo]
        if idx:
            per = vol / len(idx)
            for j in idx:
                vp[j] += per

    vp_levels = []
    if vp.max() > 0:
        peaks, _ = find_peaks(vp, prominence=vp.max() * 0.1, distance=2)
        vp_levels = [float(bins[p] + bin_size / 2) for p in peaks]

    return sorted(set(swing_levels + vp_levels))


def nearest_sr_distance(price, sr_levels):
    """Return distance to nearest S/R level."""
    if not sr_levels:
        return np.inf
    return min(abs(price - lv) for lv in sr_levels)


def find_bb_touch_events(df_day):
    """Find all BB touch events during setup window, one per day per direction."""
    events = []
    for date, day_df in df_day.groupby(df_day.index.normalize()):
        # Filter to setup window
        mask = (day_df.index.time >= pd.Timestamp(SETUP_START).time()) & \
               (day_df.index.time <= pd.Timestamp(SETUP_END).time())
        setup_df = day_df[mask]

        long_found = False
        short_found = False

        for ts, row in setup_df.iterrows():
            close = row["Close"]
            bb_lower = row["BB_Lower"]
            bb_upper = row["BB_Upper"]
            ema_hl = row["EmaHL"]
            vol = row["Volume"]
            vol_ma = row["VolMA20"]

            if np.isnan(bb_lower) or np.isnan(bb_upper) or np.isnan(ema_hl):
                continue
            if np.isnan(vol_ma) or vol_ma <= 0:
                continue

            vol_ok = vol > 1.2 * vol_ma  # same as strategy

            # Long BB touch: close <= BB_Lower + vol_ok
            if not long_found and close <= bb_lower and vol_ok:
                long_found = True
                events.append({
                    "timestamp": ts,
                    "date": date,
                    "direction": "long",
                    "close": close,
                    "ema_hl": ema_hl,
                    "bb_lower": bb_lower,
                    "bb_upper": bb_upper,
                })

            # Short BB touch: close >= BB_Upper + vol_ok
            if not short_found and close >= bb_upper and vol_ok:
                short_found = True
                events.append({
                    "timestamp": ts,
                    "date": date,
                    "direction": "short",
                    "close": close,
                    "ema_hl": ema_hl,
                    "bb_lower": bb_lower,
                    "bb_upper": bb_upper,
                })

    return pd.DataFrame(events)


def measure_outcomes(df_day, events_df):
    """For each BB touch event, measure trigger and MFE."""
    results = []

    for _, ev in events_df.iterrows():
        ts = ev["timestamp"]
        direction = ev["direction"]
        ema_hl = ev["ema_hl"]

        # Get bars after the BB touch on same day
        date_mask = df_day.index.normalize() == ev["date"]
        after_mask = df_day.index > ts
        day_after = df_day[date_mask & after_mask]

        # Look for MA5 cross within TRIGGER_WINDOW bars
        triggered = False
        trigger_ts = None
        trigger_price = None

        for i, (bar_ts, bar) in enumerate(day_after.iterrows()):
            if i >= TRIGGER_WINDOW:
                break
            ma5 = bar["MA5_1m"]
            if np.isnan(ma5):
                continue

            if direction == "long" and bar["Close"] > ma5:
                triggered = True
                trigger_ts = bar_ts
                trigger_price = bar["Close"]
                break
            elif direction == "short" and bar["Close"] < ma5:
                triggered = True
                trigger_ts = bar_ts
                trigger_price = bar["Close"]
                break

        # MFE after trigger
        mfe = 0.0
        mae = 0.0
        if triggered and trigger_ts is not None:
            post_trigger = day_after[day_after.index > trigger_ts].head(MFE_WINDOW)
            if len(post_trigger) > 0:
                if direction == "long":
                    mfe = float(post_trigger["High"].max() - trigger_price)
                    mae = float(trigger_price - post_trigger["Low"].min())
                else:
                    mfe = float(trigger_price - post_trigger["Low"].min())
                    mae = float(post_trigger["High"].max() - trigger_price)

        results.append({
            "triggered": triggered,
            "trigger_price": trigger_price,
            "mfe": mfe,
            "mae": mae,
            "mfe_ratio": mfe / ema_hl if ema_hl > 0 else 0,
            "profitable": mfe > mae if triggered else False,
        })

    return pd.DataFrame(results)


def main():
    print("=" * 70)
    print("H038 Phase 1: BB Touch + Structural Support Confluence")
    print("=" * 70)

    # Step 1: Load data
    print("\n[1/4] Loading 1m data with reversal indicators...")
    df_day = load_data_for_reversal()
    print(f"  Loaded {len(df_day):,} bars, "
          f"{df_day.index[0].date()} ~ {df_day.index[-1].date()}")

    print("\n[2/4] Loading 30m bars for S/R calculation...")
    bars_30m = load_30m_bars_all()
    print(f"  Loaded {len(bars_30m):,} 30m bars")

    # Step 2: Find BB touch events
    print("\n[3/4] Finding BB touch events...")
    events_df = find_bb_touch_events(df_day)
    print(f"  Found {len(events_df)} BB touch events "
          f"(long: {(events_df['direction'] == 'long').sum()}, "
          f"short: {(events_df['direction'] == 'short').sum()})")

    if len(events_df) == 0:
        print("No BB touch events found. Exiting.")
        return

    # Step 3: Compute S/R and confluence for each event
    print("\n[4/4] Computing S/R confluence for each event...")
    sr_cache = {}  # date -> sr_levels
    distances = []

    for _, ev in events_df.iterrows():
        d = ev["date"]
        if d not in sr_cache:
            sr_cache[d] = calc_sr_for_date(bars_30m, d, LOOKBACK_DAYS)
        sr_levels = sr_cache[d]
        dist = nearest_sr_distance(ev["close"], sr_levels)
        distances.append(dist)

    events_df["sr_distance"] = distances

    # Step 4: Measure outcomes
    print("  Measuring trigger and MFE outcomes...")
    outcomes_df = measure_outcomes(df_day, events_df)
    events_df = pd.concat([events_df.reset_index(drop=True),
                           outcomes_df.reset_index(drop=True)], axis=1)

    # ── Analysis ────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    # Overall stats
    n_total = len(events_df)
    n_triggered = events_df["triggered"].sum()
    n_profitable = events_df["profitable"].sum()
    print(f"\nOverall: {n_total} BB touches, "
          f"{n_triggered} triggered ({n_triggered/n_total*100:.1f}%), "
          f"{n_profitable} profitable ({n_profitable/n_total*100:.1f}%)")

    # By direction
    for d in ["long", "short"]:
        sub = events_df[events_df["direction"] == d]
        n = len(sub)
        trig = sub["triggered"].sum()
        prof = sub["profitable"].sum()
        avg_mfe = sub.loc[sub["triggered"], "mfe_ratio"].mean() if trig > 0 else 0
        print(f"  {d:5s}: N={n}, triggered={trig} ({trig/n*100:.1f}%), "
              f"profitable={prof} ({prof/n*100:.1f}%), avg MFE/EmaHL={avg_mfe:.3f}")

    # Threshold sensitivity analysis
    print("\n" + "-" * 70)
    print("CONFLUENCE THRESHOLD SENSITIVITY")
    print("-" * 70)
    print(f"{'Threshold':>10s} | {'N_conf':>6s} {'N_none':>6s} | "
          f"{'Trig%_c':>7s} {'Trig%_n':>7s} | "
          f"{'Prof%_c':>7s} {'Prof%_n':>7s} | "
          f"{'MFE_c':>7s} {'MFE_n':>7s} | "
          f"{'AvgMFE_c':>8s} {'AvgMFE_n':>8s}")

    for thresh in THRESHOLDS:
        conf_mask = events_df["sr_distance"] <= events_df["ema_hl"] * thresh
        conf = events_df[conf_mask]
        none_ = events_df[~conf_mask]

        nc, nn = len(conf), len(none_)
        if nc == 0 or nn == 0:
            print(f"  {thresh:.2f} EmaHL | {nc:6d} {nn:6d} | (skip: empty group)")
            continue

        trig_c = conf["triggered"].mean() * 100
        trig_n = none_["triggered"].mean() * 100
        prof_c = conf["profitable"].mean() * 100
        prof_n = none_["profitable"].mean() * 100

        # Avg MFE (points) among triggered
        mfe_c = conf.loc[conf["triggered"], "mfe"].mean() if conf["triggered"].any() else 0
        mfe_n = none_.loc[none_["triggered"], "mfe"].mean() if none_["triggered"].any() else 0
        mfer_c = conf.loc[conf["triggered"], "mfe_ratio"].mean() if conf["triggered"].any() else 0
        mfer_n = none_.loc[none_["triggered"], "mfe_ratio"].mean() if none_["triggered"].any() else 0

        print(f"  {thresh:.2f} EmaHL | {nc:6d} {nn:6d} | "
              f"{trig_c:6.1f}% {trig_n:6.1f}% | "
              f"{prof_c:6.1f}% {prof_n:6.1f}% | "
              f"{mfe_c:6.0f}pt {mfe_n:6.0f}pt | "
              f"{mfer_c:7.3f} {mfer_n:7.3f}")

    # Detailed breakdown at 0.5 EmaHL (primary threshold)
    PRIMARY = 0.5
    print(f"\n{'=' * 70}")
    print(f"DETAILED BREAKDOWN @ {PRIMARY} EmaHL threshold")
    print(f"{'=' * 70}")

    conf_mask = events_df["sr_distance"] <= events_df["ema_hl"] * PRIMARY
    for label, subset in [("CONFLUENCE", events_df[conf_mask]),
                          ("NO CONFLUENCE", events_df[~conf_mask])]:
        n = len(subset)
        if n == 0:
            print(f"\n{label}: N=0")
            continue
        trig = subset["triggered"]
        prof = subset["profitable"]
        trig_sub = subset[trig]

        print(f"\n{label}: N={n}")
        print(f"  Trigger rate: {trig.mean()*100:.1f}%")
        print(f"  Profitable rate: {prof.mean()*100:.1f}%")
        if len(trig_sub) > 0:
            print(f"  Triggered trades (N={len(trig_sub)}):")
            print(f"    Avg MFE: {trig_sub['mfe'].mean():.0f} pt "
                  f"(ratio: {trig_sub['mfe_ratio'].mean():.3f})")
            print(f"    Avg MAE: {trig_sub['mae'].mean():.0f} pt")
            print(f"    MFE > MAE: {(trig_sub['mfe'] > trig_sub['mae']).mean()*100:.1f}%")
            print(f"    Median MFE: {trig_sub['mfe'].median():.0f} pt")
            print(f"    MFE P25/P75: {trig_sub['mfe'].quantile(0.25):.0f} / "
                  f"{trig_sub['mfe'].quantile(0.75):.0f} pt")

        # By direction
        for d in ["long", "short"]:
            dsub = subset[subset["direction"] == d]
            dn = len(dsub)
            if dn == 0:
                continue
            dt = dsub["triggered"].sum()
            dp = dsub["profitable"].sum()
            print(f"  {d}: N={dn}, trig={dt} ({dt/dn*100:.1f}%), "
                  f"prof={dp} ({dp/dn*100:.1f}%)")

    # Year-by-year stability
    print(f"\n{'=' * 70}")
    print("YEAR-BY-YEAR STABILITY @ 0.5 EmaHL")
    print(f"{'=' * 70}")
    events_df["year"] = pd.to_datetime(events_df["date"]).dt.year
    print(f"{'Year':>5s} | {'N_c':>5s} {'N_n':>5s} | "
          f"{'Prof%_c':>7s} {'Prof%_n':>7s} | {'Delta':>7s}")
    for year in sorted(events_df["year"].unique()):
        yr = events_df[events_df["year"] == year]
        c = yr[yr["sr_distance"] <= yr["ema_hl"] * PRIMARY]
        n_ = yr[yr["sr_distance"] > yr["ema_hl"] * PRIMARY]
        nc, nn = len(c), len(n_)
        pc = c["profitable"].mean() * 100 if nc > 0 else 0
        pn = n_["profitable"].mean() * 100 if nn > 0 else 0
        delta = pc - pn
        print(f"  {year} | {nc:5d} {nn:5d} | {pc:6.1f}% {pn:6.1f}% | {delta:+6.1f}%")

    # S/R distance distribution
    print(f"\n{'=' * 70}")
    print("S/R DISTANCE DISTRIBUTION (as fraction of EmaHL)")
    print(f"{'=' * 70}")
    ratio = events_df["sr_distance"] / events_df["ema_hl"]
    for pct in [10, 25, 50, 75, 90]:
        print(f"  P{pct:2d}: {ratio.quantile(pct/100):.3f}")
    print(f"  Mean: {ratio.mean():.3f}")
    print(f"  Inf (no S/R): {(ratio == np.inf).sum()}")


if __name__ == "__main__":
    main()
