#!/usr/bin/env python3
"""H092 Phase 2 follow-up — Lag scan on production SatZone (B-sat m=1.0).

Lag 含義：anchor 不用「當下」running_low/high，而是 k 分鐘前的 running min/max。
公式：
    target_up[t] = lagged(running_low, k)[t] + 1.0 × EstHL[t] − EmaHL/8
    target_dn[t] = lagged(running_high, k)[t] − 1.0 × EstHL[t] + EmaHL/8

掃描 lag ∈ {0, 5, 10, 15} × window ∈ {2h, 3h, 4h, 5h} × tier。

使用方式:
    uv run python research/archive/confirmed/H092-nvf-reach-direction/phase2_reach_lag_satzone.py
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
M = 1.0
LAGS = [0, 5, 10, 15]
WINDOWS_HOURS = [2, 3, 4, 5]


def lagged_arr(arr, lag):
    if lag == 0 or len(arr) == 0:
        return arr.copy()
    out = np.empty_like(arr)
    out[:lag] = arr[0]
    out[lag:] = arr[: len(arr) - lag]
    return out


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
    return bars


def window_end_time(hours):
    end_hour = 8 + hours
    end_min = 45
    if end_hour >= 14:
        end_hour, end_min = 14, 0
    return time(end_hour, end_min)


def main():
    print("=" * 100)
    print("H092 Phase 2 follow-up — Lag scan × B-sat (m=1.0, production SatZone)")
    print("=" * 100)

    tier_df = load_tier_data()[0]
    print(f"Tier days: {len(tier_df)}")

    bars = load_full_day_bars()
    print(f"Computing production compute_estimate_hl_zones...")
    bars = compute_estimate_hl_zones(bars)
    bars["trade_date"] = bars.index.normalize()
    bars_by_date = {d: g for d, g in bars.groupby("trade_date", sort=False)}

    summary_rows = []
    WIN_START = time(8, 45)

    for hours in WINDOWS_HOURS:
        win_end = window_end_time(hours)
        print(f"\n>>> Window: 08:45 – {win_end.strftime('%H:%M')} ({hours}h)")

        rows = []
        for d in tier_df.index:
            day_bars = bars_by_date.get(d)
            if day_bars is None or day_bars.empty:
                continue
            win = day_bars[(day_bars.index.time >= WIN_START)
                           & (day_bars.index.time < win_end)]
            if win.empty:
                continue

            highs = win["High"].values
            lows = win["Low"].values
            ema_hl_arr = win["EmaHL"].values
            est_hl_arr = win["EstHL"].values

            valid_ema = ~np.isnan(ema_hl_arr)
            if not valid_ema.any():
                continue
            ema_hl_day = float(ema_hl_arr[valid_ema][0])
            if ema_hl_day <= 0:
                continue
            buf = ema_hl_day / 8.0

            running_low = np.minimum.accumulate(lows)
            running_high = np.maximum.accumulate(highs)
            est_valid = ~np.isnan(est_hl_arr)

            row = {"date": d, "tier": tier_df.at[d, "tier"]}
            for k in LAGS:
                anchor_low = lagged_arr(running_low, k)
                anchor_high = lagged_arr(running_high, k)
                target_up = anchor_low + M * est_hl_arr - buf
                target_dn = anchor_high - M * est_hl_arr + buf
                row[f"up_lag{k}"] = bool(((highs >= target_up) & est_valid).any())
                row[f"dn_lag{k}"] = bool(((lows <= target_dn) & est_valid).any())
            rows.append(row)

        df = pd.DataFrame(rows)
        print(f"   Days processed: {len(df)}")

        for tier in TIER_LABELS:
            sub = df[df["tier"] == tier]
            n = len(sub)
            for k in LAGS:
                up = sub[f"up_lag{k}"].mean() * 100
                dn = sub[f"dn_lag{k}"].mean() * 100
                either = ((sub[f"up_lag{k}"]) | (sub[f"dn_lag{k}"])).mean() * 100
                both = ((sub[f"up_lag{k}"]) & (sub[f"dn_lag{k}"])).mean() * 100
                summary_rows.append({
                    "window_h": hours, "tier": tier, "lag": k, "N": n,
                    "upper": up, "lower": dn, "either": either, "both": both,
                })

    sdf = pd.DataFrame(summary_rows)
    out_csv = OUT_DIR / "reach_lag_satzone_m1.csv"
    sdf.to_csv(out_csv, index=False)
    print(f"\n✅ Saved {out_csv}")

    # ── Pretty print ──
    for direction in ["upper", "lower", "either"]:
        print("\n" + "=" * 110)
        print(f"B-sat m=1.0 — {direction.upper()} reach % by Lag × Window × Tier")
        print("=" * 110)
        print(f"{'Tier':<11} {'Win':<4} " + " ".join([f"lag={k:<3}" for k in LAGS]))
        print("-" * 60)
        for tier in TIER_LABELS:
            for h in WINDOWS_HOURS:
                sub = sdf[(sdf["tier"] == tier) & (sdf["window_h"] == h)]
                vals = [sub[sub["lag"] == k][direction].iloc[0] for k in LAGS]
                print(f"{tier:<11} {h}h   " + " ".join([f"{v:>5.1f}%" for v in vals]))
            print()


if __name__ == "__main__":
    main()
