#!/usr/bin/env python3
"""
H038 Phase 1 v2: BB Touch + Intraday Level Retest Confluence

For each BB touch event:
1. Count how many times the same price level was tested earlier that day
2. Compare retest vs no-retest groups on trigger rate, MFE, profitability
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[3]))
from src.backtest.runner import load_data_for_reversal

# ── Parameters ──────────────────────────────────────────────────────
SETUP_START = "08:45"
SETUP_END   = "10:05"
TRIGGER_WINDOW = 20         # bars after BB touch to look for MA5 cross
MFE_WINDOW = 60             # bars after trigger to measure MFE
TOLERANCES = [10, 20, 30]   # pt range for "same level"
RETEST_THRESHOLDS = [2, 3, 5]  # minimum retest count


def count_intraday_retests(day_df, bb_ts, bb_close, direction, tolerance):
    """Count how many bars before bb_ts tested the same level.

    Long (BB_Lower touch): count bars where Low is within bb_close ± tolerance
    Short (BB_Upper touch): count bars where High is within bb_close ± tolerance
    """
    before = day_df[day_df.index < bb_ts]
    if len(before) == 0:
        return 0

    if direction == "long":
        # How many bars had their Low near this level?
        hits = ((before["Low"] >= bb_close - tolerance) &
                (before["Low"] <= bb_close + tolerance))
    else:
        # How many bars had their High near this level?
        hits = ((before["High"] >= bb_close - tolerance) &
                (before["High"] <= bb_close + tolerance))

    return int(hits.sum())


def find_bb_touch_events(df_day):
    """Find all BB touch events during setup window, first per day per direction."""
    events = []
    for date, day_df in df_day.groupby(df_day.index.normalize()):
        mask = ((day_df.index.time >= pd.Timestamp(SETUP_START).time()) &
                (day_df.index.time <= pd.Timestamp(SETUP_END).time()))
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

            if any(np.isnan(v) for v in [bb_lower, bb_upper, ema_hl, vol_ma]):
                continue
            if vol_ma <= 0:
                continue

            vol_ok = vol > 1.2 * vol_ma

            if not long_found and close <= bb_lower and vol_ok:
                long_found = True
                events.append({
                    "timestamp": ts, "date": date, "direction": "long",
                    "close": close, "ema_hl": ema_hl,
                })

            if not short_found and close >= bb_upper and vol_ok:
                short_found = True
                events.append({
                    "timestamp": ts, "date": date, "direction": "short",
                    "close": close, "ema_hl": ema_hl,
                })

    return pd.DataFrame(events)


def measure_outcomes(df_day, events_df):
    """For each BB touch, measure trigger and MFE."""
    results = []
    for _, ev in events_df.iterrows():
        ts = ev["timestamp"]
        direction = ev["direction"]
        ema_hl = ev["ema_hl"]

        date_mask = df_day.index.normalize() == ev["date"]
        after_mask = df_day.index > ts
        day_after = df_day[date_mask & after_mask]

        # Look for MA5 cross trigger
        triggered = False
        trigger_price = None
        for i, (bar_ts, bar) in enumerate(day_after.iterrows()):
            if i >= TRIGGER_WINDOW:
                break
            ma5 = bar["MA5_1m"]
            if np.isnan(ma5):
                continue
            if direction == "long" and bar["Close"] > ma5:
                triggered = True
                trigger_price = bar["Close"]
                trigger_ts = bar_ts
                break
            elif direction == "short" and bar["Close"] < ma5:
                triggered = True
                trigger_price = bar["Close"]
                trigger_ts = bar_ts
                break

        mfe, mae = 0.0, 0.0
        if triggered:
            post = day_after[day_after.index > trigger_ts].head(MFE_WINDOW)
            if len(post) > 0:
                if direction == "long":
                    mfe = float(post["High"].max() - trigger_price)
                    mae = float(trigger_price - post["Low"].min())
                else:
                    mfe = float(trigger_price - post["Low"].min())
                    mae = float(post["High"].max() - trigger_price)

        results.append({
            "triggered": triggered,
            "trigger_price": trigger_price,
            "mfe": mfe, "mae": mae,
            "mfe_ratio": mfe / ema_hl if ema_hl > 0 else 0,
            "profitable": mfe > mae if triggered else False,
        })

    return pd.DataFrame(results)


def group_stats(subset, label=""):
    """Return summary dict for a group."""
    n = len(subset)
    if n == 0:
        return None
    trig = subset["triggered"]
    prof = subset["profitable"]
    trig_sub = subset[trig]
    return {
        "label": label, "n": n,
        "trig_pct": trig.mean() * 100,
        "prof_pct": prof.mean() * 100,
        "avg_mfe": trig_sub["mfe"].mean() if len(trig_sub) > 0 else 0,
        "avg_mae": trig_sub["mae"].mean() if len(trig_sub) > 0 else 0,
        "avg_mfe_ratio": trig_sub["mfe_ratio"].mean() if len(trig_sub) > 0 else 0,
        "mfe_gt_mae_pct": (trig_sub["mfe"] > trig_sub["mae"]).mean() * 100 if len(trig_sub) > 0 else 0,
        "median_mfe": trig_sub["mfe"].median() if len(trig_sub) > 0 else 0,
    }


def main():
    print("=" * 70)
    print("H038 Phase 1 v2: BB Touch + Intraday Level Retest")
    print("=" * 70)

    print("\n[1/3] Loading 1m data...")
    df_day = load_data_for_reversal()
    print(f"  {len(df_day):,} bars, {df_day.index[0].date()} ~ {df_day.index[-1].date()}")

    print("\n[2/3] Finding BB touch events...")
    events_df = find_bb_touch_events(df_day)
    print(f"  {len(events_df)} events "
          f"(long: {(events_df['direction'] == 'long').sum()}, "
          f"short: {(events_df['direction'] == 'short').sum()})")

    # Pre-group day DataFrames for speed
    day_groups = {date: grp for date, grp in df_day.groupby(df_day.index.normalize())}

    print("\n[3/3] Computing retest counts & outcomes...")

    # Compute retest counts for all tolerance values
    for tol in TOLERANCES:
        col = f"retest_{tol}"
        counts = []
        for _, ev in events_df.iterrows():
            day_df = day_groups.get(ev["date"])
            if day_df is None:
                counts.append(0)
                continue
            counts.append(count_intraday_retests(
                day_df, ev["timestamp"], ev["close"], ev["direction"], tol))
        events_df[col] = counts

    # Outcomes
    outcomes_df = measure_outcomes(df_day, events_df)
    events_df = pd.concat([events_df.reset_index(drop=True),
                           outcomes_df.reset_index(drop=True)], axis=1)

    # ── Results ─────────────────────────────────────────────────────
    n_total = len(events_df)
    n_trig = events_df["triggered"].sum()
    n_prof = events_df["profitable"].sum()
    print(f"\nOverall: {n_total} BB touches, "
          f"{n_trig} triggered ({n_trig/n_total*100:.1f}%), "
          f"{n_prof} profitable ({n_prof/n_total*100:.1f}%)")

    # ── Retest count distribution ───────────────────────────────────
    print(f"\n{'=' * 70}")
    print("RETEST COUNT DISTRIBUTION")
    print(f"{'=' * 70}")
    for tol in TOLERANCES:
        col = f"retest_{tol}"
        vals = events_df[col]
        print(f"\n  Tolerance ±{tol}pt:")
        print(f"    P25={vals.quantile(0.25):.0f}  P50={vals.quantile(0.5):.0f}  "
              f"P75={vals.quantile(0.75):.0f}  P90={vals.quantile(0.9):.0f}  "
              f"Mean={vals.mean():.1f}  Max={vals.max():.0f}")
        for n_min in RETEST_THRESHOLDS:
            cnt = (vals >= n_min).sum()
            print(f"    >= {n_min} retests: {cnt} ({cnt/n_total*100:.1f}%)")

    # ── Sensitivity matrix ──────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("SENSITIVITY: TOLERANCE × RETEST THRESHOLD")
    print(f"{'=' * 70}")
    print(f"{'Tol':>4s} {'N>=':>3s} | {'N_yes':>5s} {'N_no':>5s} | "
          f"{'Prof%_y':>7s} {'Prof%_n':>7s} {'Delta':>7s} | "
          f"{'MFE_y':>6s} {'MFE_n':>6s} {'Delta':>7s} | "
          f"{'MFEr_y':>6s} {'MFEr_n':>6s}")

    for tol in TOLERANCES:
        col = f"retest_{tol}"
        for n_min in RETEST_THRESHOLDS:
            yes = events_df[events_df[col] >= n_min]
            no = events_df[events_df[col] < n_min]
            ny, nn = len(yes), len(no)
            if ny == 0 or nn == 0:
                print(f" ±{tol:2d} {n_min:>3d} | {ny:5d} {nn:5d} | (skip: empty group)")
                continue

            py = yes["profitable"].mean() * 100
            pn = no["profitable"].mean() * 100
            dp = py - pn

            my = yes.loc[yes["triggered"], "mfe"].mean() if yes["triggered"].any() else 0
            mn = no.loc[no["triggered"], "mfe"].mean() if no["triggered"].any() else 0
            dm = my - mn

            mry = yes.loc[yes["triggered"], "mfe_ratio"].mean() if yes["triggered"].any() else 0
            mrn = no.loc[no["triggered"], "mfe_ratio"].mean() if no["triggered"].any() else 0

            print(f" ±{tol:2d} {n_min:>3d} | {ny:5d} {nn:5d} | "
                  f"{py:6.1f}% {pn:6.1f}% {dp:+6.1f}% | "
                  f"{my:5.0f}pt {mn:5.0f}pt {dm:+6.0f}pt | "
                  f"{mry:5.3f} {mrn:5.3f}")

    # ── Detailed breakdown: best tolerance ──────────────────────────
    # Use ±20pt, N>=3 as primary (middle ground)
    PRIMARY_TOL = 20
    PRIMARY_N = 3
    col = f"retest_{PRIMARY_TOL}"
    print(f"\n{'=' * 70}")
    print(f"DETAILED BREAKDOWN @ ±{PRIMARY_TOL}pt, retest >= {PRIMARY_N}")
    print(f"{'=' * 70}")

    for label, subset in [
        ("RETEST", events_df[events_df[col] >= PRIMARY_N]),
        ("NO RETEST", events_df[events_df[col] < PRIMARY_N]),
    ]:
        s = group_stats(subset, label)
        if s is None:
            print(f"\n{label}: N=0")
            continue
        print(f"\n{label}: N={s['n']}")
        print(f"  Trigger rate: {s['trig_pct']:.1f}%")
        print(f"  Profitable rate: {s['prof_pct']:.1f}%")
        print(f"  MFE > MAE: {s['mfe_gt_mae_pct']:.1f}%")
        print(f"  Avg MFE: {s['avg_mfe']:.0f} pt (ratio: {s['avg_mfe_ratio']:.3f})")
        print(f"  Avg MAE: {s['avg_mae']:.0f} pt")
        print(f"  Median MFE: {s['median_mfe']:.0f} pt")

        for d in ["long", "short"]:
            dsub = subset[subset["direction"] == d]
            dn = len(dsub)
            if dn == 0:
                continue
            dp = dsub["profitable"].mean() * 100
            print(f"  {d}: N={dn}, prof={dp:.1f}%")

    # ── Monotonic relationship: retest count vs prof% ───────────────
    print(f"\n{'=' * 70}")
    print(f"RETEST COUNT vs PROFITABILITY (±{PRIMARY_TOL}pt)")
    print(f"{'=' * 70}")
    print(f"{'Retests':>8s} | {'N':>5s} | {'Prof%':>6s} | {'AvgMFE':>7s} | {'MFE/HL':>7s}")

    col = f"retest_{PRIMARY_TOL}"
    max_retest = int(events_df[col].quantile(0.95))
    bins = [0, 1, 2, 3, 5, 10, max(max_retest + 1, 15)]
    for i in range(len(bins) - 1):
        lo, hi = bins[i], bins[i + 1]
        if i == len(bins) - 2:
            sub = events_df[events_df[col] >= lo]
            label = f">= {lo}"
        else:
            sub = events_df[(events_df[col] >= lo) & (events_df[col] < hi)]
            label = f"{lo}-{hi-1}" if hi - lo > 1 else f"{lo}"
        n = len(sub)
        if n == 0:
            continue
        prof = sub["profitable"].mean() * 100
        trig_sub = sub[sub["triggered"]]
        avg_mfe = trig_sub["mfe"].mean() if len(trig_sub) > 0 else 0
        avg_ratio = trig_sub["mfe_ratio"].mean() if len(trig_sub) > 0 else 0
        print(f"  {label:>6s} | {n:5d} | {prof:5.1f}% | {avg_mfe:6.0f}pt | {avg_ratio:6.3f}")

    # ── Year-by-year stability ──────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"YEAR-BY-YEAR STABILITY @ ±{PRIMARY_TOL}pt, retest >= {PRIMARY_N}")
    print(f"{'=' * 70}")
    events_df["year"] = pd.to_datetime(events_df["date"]).dt.year
    print(f"{'Year':>5s} | {'N_y':>5s} {'N_n':>5s} | "
          f"{'Prof%_y':>7s} {'Prof%_n':>7s} | {'Delta':>7s}")
    for year in sorted(events_df["year"].unique()):
        yr = events_df[events_df["year"] == year]
        yes = yr[yr[col] >= PRIMARY_N]
        no = yr[yr[col] < PRIMARY_N]
        ny, nn = len(yes), len(no)
        py = yes["profitable"].mean() * 100 if ny > 0 else 0
        pn = no["profitable"].mean() * 100 if nn > 0 else 0
        delta = py - pn
        print(f"  {year} | {ny:5d} {nn:5d} | {py:6.1f}% {pn:6.1f}% | {delta:+6.1f}%")


if __name__ == "__main__":
    main()
