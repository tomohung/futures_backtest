#!/usr/bin/env python3
"""Step 0: Explore relationship between night session range and day session volatility.

Computes per trading day:
  night_range : night session (15:00 prev ~ 05:00 today) high - low
  or_range    : OR period (08:45~09:30) high - low
  day_range   : full day session (08:45~13:45) high - low
  open_gap    : abs(day_open - night_close)

Outputs:
  1. Correlation matrix: night_range vs or_range vs day_range vs open_gap
  2. Phase 2 performance segmented by night_range quartile
  3. Year-by-year night_range stats

Decision gate:
  |r(night, day)| > 0.4 → use night range in TP
  r < 0.4              → OR width is sufficient, skip night complexity

Usage:
    uv run python src/backtest/explore_night_day.py
"""
import datetime
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.backtest.runner import load_data_with_night_ma
from src.strategies.orb import ORBStrategy

DB_PATH = "data/futures.duckdb"

OR_END_TIME = datetime.time(9, 30)   # OR = 08:45~09:30 (range_end_minute=90 → 08:00+90=09:30)

PHASE2_PARAMS = dict(
    range_end_minute=90, entry_end_minute=120,
    sl_pct=0.005, tp_multiplier=1.5,
    trail_activate_minute=45, trend_ma_days=10,
)


def load_daily_ranges() -> pd.DataFrame:
    """Load all bars and compute per-day night/OR/day ranges."""
    print("Loading raw bars from DuckDB...", flush=True)
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp, high, low, close
            FROM ohlcv_1m
            WHERE symbol = 'TX'
            ORDER BY timestamp
        """).df()

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["cal_date"] = df["timestamp"].dt.date
    df["t"] = df["timestamp"].dt.time

    T_DAY_S   = datetime.time(8, 45)
    T_DAY_E   = datetime.time(13, 45)
    T_NIGHT_S = datetime.time(15, 0)
    T_EARLY_E = datetime.time(5, 0)

    day_df = df[(df["t"] >= T_DAY_S) & (df["t"] <= T_DAY_E)].copy()
    trading_days = sorted(day_df["cal_date"].unique())
    print(f"  {len(trading_days)} trading days, {len(df):,} total bars", flush=True)

    rows = []
    for i, trade_date in enumerate(trading_days):
        db = day_df[day_df["cal_date"] == trade_date]
        or_b = db[db["t"] <= OR_END_TIME]

        post_or_b = db[db["t"] > OR_END_TIME]

        day_range    = float(db["high"].max() - db["low"].min())
        day_open     = float(db.iloc[0]["close"])  # first-bar close ≈ day open
        or_range     = float(or_b["high"].max() - or_b["low"].min()) if len(or_b) > 0 else np.nan
        post_or_range = float(post_or_b["high"].max() - post_or_b["low"].min()) if len(post_or_b) > 0 else np.nan

        if i > 0:
            prev_date  = trading_days[i - 1]
            nb_prev    = df[(df["cal_date"] == prev_date) & (df["t"] >= T_NIGHT_S)]
            nb_curr    = df[(df["cal_date"] == trade_date) & (df["t"] <= T_EARLY_E)]
            night_bars = pd.concat([nb_prev, nb_curr]).sort_values("timestamp")

            if len(night_bars) > 0:
                night_range = float(night_bars["high"].max() - night_bars["low"].min())
                night_close = float(night_bars.iloc[-1]["close"])
                open_gap    = abs(day_open - night_close)
            else:
                night_range = open_gap = np.nan
        else:
            night_range = open_gap = np.nan

        rows.append({
            "date":          trade_date,
            "year":          trade_date.year,
            "night_range":   night_range,
            "or_range":      or_range,
            "post_or_range": post_or_range,
            "day_range":     day_range,
            "open_gap":      open_gap,
        })

    return pd.DataFrame(rows).dropna(subset=["night_range", "or_range", "post_or_range"])


def run_phase2_all() -> pd.DataFrame:
    """Run Phase 2 on all years and return trades DataFrame with entry_date."""
    print("Running Phase 2 on full dataset (2021–2026)...", flush=True)
    df = load_data_with_night_ma(start="2021-01-01", trend_ma_days=10)
    bt = Backtest(df, ORBStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**PHASE2_PARAMS)
    trades = stats["_trades"].copy()
    trades["entry_date"] = pd.to_datetime(trades["EntryTime"]).dt.date
    trades["exit_time_t"] = pd.to_datetime(trades["ExitTime"]).dt.time
    trades["is_force"] = trades["exit_time_t"] >= datetime.time(13, 30)
    print(f"  {len(trades)} trades total", flush=True)
    return trades


def fv(v, fmt=".1f"):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "  —"
    return f"{v:{fmt}}"


def main():
    daily = load_daily_ranges()

    # ── 1. Correlation matrix ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("1. CORRELATION MATRIX  (n={})".format(len(daily)))
    print(f"{'='*60}")
    cols = ["night_range", "or_range", "post_or_range", "day_range", "open_gap"]
    corr = daily[cols].corr()
    print(corr.to_string(float_format=lambda x: f"{x:+.3f}"))

    r_night_day     = corr.loc["night_range",   "day_range"]
    r_night_post_or = corr.loc["night_range",   "post_or_range"]
    r_night_or      = corr.loc["night_range",   "or_range"]
    r_or_post_or    = corr.loc["or_range",      "post_or_range"]
    r_or_day        = corr.loc["or_range",      "day_range"]

    print(f"\n  Predictors of post_or_range (09:30–13:45, what TP faces):")
    print(f"    r(night_range, post_or_range) = {r_night_post_or:+.3f}")
    print(f"    r(or_range,    post_or_range) = {r_or_post_or:+.3f}")
    print(f"\n  Predictors of full day_range (08:45–13:45):")
    print(f"    r(night_range, day_range)     = {r_night_day:+.3f}")
    print(f"    r(or_range,    day_range)     = {r_or_day:+.3f}")

    threshold = 0.4
    print(f"\n  Decision gate (|r(night, post_or)| vs {threshold}):")
    if abs(r_night_post_or) > threshold:
        print(f"  → |r|={abs(r_night_post_or):.3f} > {threshold}  night adds signal beyond OR (Plan B/C)")
    else:
        print(f"  → |r|={abs(r_night_post_or):.3f} ≤ {threshold}  OR width sufficient, skip night complexity (Plan A)")

    # ── 2. Phase 2 perf by night_range quartile ────────────────────────────
    print(f"\n{'='*60}")
    print("2. PHASE 2 PERFORMANCE BY NIGHT_RANGE QUARTILE")
    print(f"{'='*60}")
    trades = run_phase2_all()

    daily_q = daily.copy()
    daily_q["quartile"] = pd.qcut(
        daily_q["night_range"], 4,
        labels=["Q1(quiet)", "Q2", "Q3", "Q4(volatile)"]
    )

    t_merged = trades.merge(
        daily_q[["date", "quartile", "night_range"]],
        left_on="entry_date", right_on="date", how="left",
    ).dropna(subset=["quartile"])

    print(f"\n  {'Quartile':<14}  {'n':>5}  {'win%':>6}  {'exp':>6}  "
          f"{'force%':>7}  {'night_rng (med/range)':>22}")
    print(f"  {'-'*14}  {'-'*5}  {'-'*6}  {'-'*6}  {'-'*7}  {'-'*22}")

    for q in ["Q1(quiet)", "Q2", "Q3", "Q4(volatile)"]:
        tq = t_merged[t_merged["quartile"] == q]
        if len(tq) == 0:
            continue
        pnl   = tq["PnL"]
        wins  = pnl[pnl > 0]
        force = tq["is_force"].sum()
        nr    = daily_q[daily_q["quartile"] == q]["night_range"]
        print(f"  {q:<14}  {len(tq):>5}  {len(wins)/len(tq)*100:>5.1f}%  "
              f"{pnl.mean():>6.1f}  {force/len(tq)*100:>6.1f}%  "
              f"{nr.median():>6.0f} ({nr.min():.0f}–{nr.max():.0f})")

    # ── 3. Year-by-year night_range stats ─────────────────────────────────
    print(f"\n{'='*60}")
    print("3. YEAR-BY-YEAR NIGHT_RANGE STATS")
    print(f"{'='*60}")
    print(f"  {'Year':>6}  {'days':>5}  {'median':>7}  {'mean':>7}  "
          f"{'p75':>7}  {'max':>7}")
    print(f"  {'-'*6}  {'-'*5}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*7}")
    for yr, grp in daily.groupby("year"):
        nr = grp["night_range"].dropna()
        print(f"  {yr:>6}  {len(nr):>5}  {nr.median():>7.0f}  {nr.mean():>7.0f}  "
              f"{nr.quantile(0.75):>7.0f}  {nr.max():>7.0f}")

    # ── 4. OR range & day range by year (context) ─────────────────────────
    print(f"\n{'='*60}")
    print("4. OR_RANGE & DAY_RANGE BY YEAR  (context)")
    print(f"{'='*60}")
    print(f"  {'Year':>6}  {'or_med':>7}  {'or_mean':>8}  {'day_med':>8}  "
          f"{'day_mean':>9}  {'night/or':>9}")
    print(f"  {'-'*6}  {'-'*7}  {'-'*8}  {'-'*8}  {'-'*9}  {'-'*9}")
    for yr, grp in daily.groupby("year"):
        g = grp.dropna(subset=["or_range", "night_range"])
        ratio = (g["night_range"].mean() / g["or_range"].mean()
                 if g["or_range"].mean() != 0 else np.nan)
        print(f"  {yr:>6}  {g['or_range'].median():>7.0f}  {g['or_range'].mean():>8.0f}  "
              f"{g['day_range'].median():>8.0f}  {g['day_range'].mean():>9.0f}  "
              f"{ratio:>9.2f}")

    print()


if __name__ == "__main__":
    main()
