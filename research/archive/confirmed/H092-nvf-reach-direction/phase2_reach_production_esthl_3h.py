#!/usr/bin/env python3
"""H092 Phase 2 follow-up — Production EstHL reach, 3-hour window (08:45–11:44).

延伸 phase2_reach_production_esthl.py，把判斷觸擊的時間視窗從 2h 改成 3h，
回答「拉長到三小時觸擊率變多少」的問題。

三個 target 定義 (running-anchored, B definition):
    B-old: running_low + m × EmaHL          (純歷史 EmaHL anchor)
    B-est: running_low + m × EstHL          (動態 EstHL, 無 buffer)
    B-sat: running_low + m × EstHL − EmaHL/8 (S001 production SatZone)

使用方式:
    uv run python research/archive/confirmed/H092-nvf-reach-direction/phase2_reach_production_esthl_3h.py
"""

import sys
from datetime import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from phase2_market_structure import (
    load_data as load_tier_data,
    TIER_LABELS, DB_PATH, SYMBOL,
)
from src.backtest.estimate_hl import compute_estimate_hl_zones

OUT_DIR = Path(__file__).parent / "results"
import os
# MULTIPLES override: env "MULTIPLES" = comma-separated floats.
_default_mult = "0.618,0.75,0.875,1.0,1.2"
MULTIPLES = [float(x) for x in os.environ.get("MULTIPLES", _default_mult).split(",")]
WINDOW_START = time(8, 45)
# Override via env var WINDOW_HOURS; default 3h.
_HOURS = int(os.environ.get("WINDOW_HOURS", "3"))
_end_hour = 8 + _HOURS
_end_min = 45
if _end_hour >= 14:  # cap to day-session close 13:45 inclusive
    _end_hour, _end_min = 14, 0
WINDOW_END = time(_end_hour, _end_min)  # exclusive; 14:00 => includes 13:45 close bar
_MULT_TAG = os.environ.get("MULT_TAG", "")  # e.g. "_mlow" to avoid overwriting baseline files
_TAG = f"{_HOURS}h{_MULT_TAG}"


def load_full_day_bars():
    print("Loading full-day 1m bars (08:45-13:45)...")
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        bars = conn.execute(
            """
            SELECT timestamp,
                   open  AS Open,
                   high  AS High,
                   low   AS Low,
                   close AS Close,
                   volume AS Volume
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ORDER BY timestamp
            """,
            [SYMBOL],
        ).df()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"])
    bars = bars.set_index("timestamp").sort_index()
    print(f"  Total bars: {len(bars)}")
    return bars


def main():
    print("=" * 100)
    print("H092 Phase 2 follow-up — Production EstHL reach (3h window 08:45–11:44)")
    print("=" * 100)

    tier_df = load_tier_data()[0]
    print(f"Tier days: {len(tier_df)}")

    bars = load_full_day_bars()

    print("Running production compute_estimate_hl_zones (slot-level dynamic)...")
    bars = compute_estimate_hl_zones(bars)

    bars["trade_date"] = bars.index.normalize()
    bars_by_date = {d: g for d, g in bars.groupby("trade_date", sort=False)}

    rows = []
    skipped = 0
    for d in tier_df.index:
        day_bars = bars_by_date.get(d)
        if day_bars is None or day_bars.empty:
            skipped += 1
            continue
        win = day_bars[(day_bars.index.time >= WINDOW_START)
                       & (day_bars.index.time < WINDOW_END)]
        if win.empty:
            skipped += 1
            continue

        highs = win["High"].values
        lows = win["Low"].values
        ema_hl_arr = win["EmaHL"].values
        est_hl_arr = win["EstHL"].values

        valid_ema = ~np.isnan(ema_hl_arr)
        if not valid_ema.any():
            skipped += 1
            continue
        ema_hl_day = float(ema_hl_arr[valid_ema][0])
        if ema_hl_day <= 0:
            skipped += 1
            continue

        running_low = np.minimum.accumulate(lows)
        running_high = np.maximum.accumulate(highs)
        est_valid = ~np.isnan(est_hl_arr)

        row = {"date": d, "tier": tier_df.at[d, "tier"],
               "year": tier_df.at[d, "year"], "ema_hl": ema_hl_day}

        for m in MULTIPLES:
            target_up_old = running_low + m * ema_hl_day
            target_dn_old = running_high - m * ema_hl_day
            row[f"Bold_up_{m}"] = bool((highs >= target_up_old).any())
            row[f"Bold_dn_{m}"] = bool((lows <= target_dn_old).any())

            target_up_est = running_low + m * est_hl_arr
            target_dn_est = running_high - m * est_hl_arr
            row[f"Best_up_{m}"] = bool(((highs >= target_up_est) & est_valid).any())
            row[f"Best_dn_{m}"] = bool(((lows <= target_dn_est) & est_valid).any())

            target_up_sat = running_low + m * est_hl_arr - ema_hl_day / 8
            target_dn_sat = running_high - m * est_hl_arr + ema_hl_day / 8
            row[f"Bsat_up_{m}"] = bool(((highs >= target_up_sat) & est_valid).any())
            row[f"Bsat_dn_{m}"] = bool(((lows <= target_dn_sat) & est_valid).any())

        rows.append(row)

    df = pd.DataFrame(rows).set_index("date")
    print(f"\nDays processed: {len(df)} (skipped: {skipped})")
    df.to_csv(OUT_DIR / f"reach_production_esthl_{_TAG}_raw.csv")

    def print_section(direction_key, label):
        print("\n" + "─" * 100)
        print(f"Reach probability by tier — {label} side (3h window)")
        print("─" * 100)
        header = f"{'Tier':<12} {'Def':<7} {'N':>4} " + " ".join([f"  m={m:<5}" for m in MULTIPLES])
        print(header)
        print("─" * 100)
        out = []
        for tier in TIER_LABELS:
            sub = df[df["tier"] == tier]
            n = len(sub)
            for defn, prefix in [("B-old", "Bold"), ("B-est", "Best"), ("B-sat", "Bsat")]:
                probs = [sub[f"{prefix}_{direction_key}_{m}"].mean() * 100 for m in MULTIPLES]
                print(f"{tier:<12} {defn:<7} {n:>4} " + " ".join([f"  {p:>5.1f}%" for p in probs]))
                out.append({"tier": tier, "def": defn, "dir": direction_key, "N": n,
                            **{f"p_{m}": p / 100 for m, p in zip(MULTIPLES, probs)}})
            print()
        return out

    summary = print_section("up", "Upper") + print_section("dn", "Lower")
    pd.DataFrame(summary).to_csv(OUT_DIR / f"reach_production_esthl_{_TAG}_summary.csv", index=False)

    print("\n" + "─" * 100)
    print("⭐ S001 SatZone exact (B-sat m=1.0) — upper / lower / either / both (3h)")
    print("─" * 100)
    print(f"{'Tier':<12} {'N':>4} {'upper':>8} {'lower':>8} {'either':>8} {'both':>8}")
    for tier in TIER_LABELS:
        sub = df[df["tier"] == tier]
        n = len(sub)
        up = sub["Bsat_up_1.0"].mean() * 100
        dn = sub["Bsat_dn_1.0"].mean() * 100
        either = ((sub["Bsat_up_1.0"]) | (sub["Bsat_dn_1.0"])).mean() * 100
        both = ((sub["Bsat_up_1.0"]) & (sub["Bsat_dn_1.0"])).mean() * 100
        print(f"{tier:<12} {n:>4} {up:>7.1f}% {dn:>7.1f}% {either:>7.1f}% {both:>7.1f}%")

    print("\n✅ Done. CSVs in", OUT_DIR)


if __name__ == "__main__":
    main()
