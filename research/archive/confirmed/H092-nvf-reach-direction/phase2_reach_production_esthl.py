#!/usr/bin/env python3
"""H092 Phase 2 — Production EstHL reach analysis.

用 production S001 動態 EstHL 重算 reach 機率,並與固定 EmaHL 版本對照。

三個 target 定義(running-anchored, B definition):
    B-old: running_low + m × EmaHL          (我之前的,prior 20-day EMA fixed)
    B-est: running_low + m × EstHL          (production 動態 EstHL,無 buffer)
    B-sat: running_low + m × EstHL − EmaHL/8 (S001 SatZone exact, m=1.0 = S001 Upper)

EstHL:
    每 15 分鐘 slot 更新,基於累積量 / 累積時段佔比推算的「動態振幅估計」。
    當日量大 → EstHL > EmaHL → target 更高(reach 更難)。
    當日量縮 → EstHL < EmaHL → target 更低(reach 更易)。

使用方式:
    uv run python research/active/H092-nvf-reach-direction/phase2_reach_production_esthl.py
"""

import sys
from datetime import time
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from phase2_market_structure import (
    load_data as load_tier_data,
    TIER_LABELS, TIER_COLORS, DB_PATH, SYMBOL,
)
from src.backtest.estimate_hl import compute_estimate_hl_zones

OUT_DIR = Path("research/active/H092-nvf-reach-direction/results")
MULTIPLES = [0.618, 0.75, 0.875, 1.0, 1.2]
WINDOW_START = time(8, 45)
WINDOW_END = time(10, 45)  # exclusive


def load_full_day_bars():
    """載入 08:45-13:45 1m bars,給 compute_estimate_hl_zones 用。"""
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
    print("H092 Phase 2 — Production EstHL reach analysis")
    print("=" * 100)

    tier_df = load_tier_data()[0]
    print(f"Tier days: {len(tier_df)}")

    bars = load_full_day_bars()

    print("Running production compute_estimate_hl_zones (slot-level dynamic)...")
    bars = compute_estimate_hl_zones(bars)
    print("  Done. EmaHL / EstHL / SatZoneUpper / SatZoneLower columns appended.")

    # Group bars by date
    bars["trade_date"] = bars.index.normalize()
    bars_by_date = {d: g for d, g in bars.groupby("trade_date", sort=False)}

    # Per-day reach analysis in 08:45-10:44 window
    rows = []
    skipped = 0
    no_est_hl = 0
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

        # First bar's EmaHL: if NaN, skip (warmup)
        ema_hl_day = None
        valid_ema_mask = ~np.isnan(ema_hl_arr)
        if valid_ema_mask.any():
            ema_hl_day = float(ema_hl_arr[valid_ema_mask][0])
        if ema_hl_day is None or ema_hl_day <= 0:
            skipped += 1
            continue

        running_low = np.minimum.accumulate(lows)
        running_high = np.maximum.accumulate(highs)

        # EstHL availability mask (NaN before first slot completes)
        est_valid = ~np.isnan(est_hl_arr)
        if not est_valid.any():
            no_est_hl += 1
            # Still record B-old (uses EmaHL only, no EstHL needed)

        row = {
            "date": d,
            "tier": tier_df.at[d, "tier"],
            "year": tier_df.at[d, "year"],
            "ema_hl": ema_hl_day,
            "est_hl_first_valid": float(est_hl_arr[est_valid][0]) if est_valid.any() else np.nan,
            "est_hl_last_valid": float(est_hl_arr[est_valid][-1]) if est_valid.any() else np.nan,
            "est_hl_ratio_first": float(est_hl_arr[est_valid][0] / ema_hl_day) if est_valid.any() else np.nan,
            "est_hl_ratio_last": float(est_hl_arr[est_valid][-1] / ema_hl_day) if est_valid.any() else np.nan,
            "est_hl_valid_bars": int(est_valid.sum()),
        }

        for m in MULTIPLES:
            # B-old: running_low + m × EmaHL
            target_up_old = running_low + m * ema_hl_day
            target_dn_old = running_high - m * ema_hl_day
            row[f"Bold_up_{m}"] = bool((highs >= target_up_old).any())
            row[f"Bold_dn_{m}"] = bool((lows <= target_dn_old).any())

            # B-est: running_low + m × EstHL (per-bar, only where EstHL valid)
            target_up_est = running_low + m * est_hl_arr
            target_dn_est = running_high - m * est_hl_arr
            reach_up_est = (highs >= target_up_est) & est_valid
            reach_dn_est = (lows <= target_dn_est) & est_valid
            row[f"Best_up_{m}"] = bool(reach_up_est.any())
            row[f"Best_dn_{m}"] = bool(reach_dn_est.any())

            # B-sat: running_low + m × EstHL − EmaHL/8 (S001 with /8 buffer)
            target_up_sat = running_low + m * est_hl_arr - ema_hl_day / 8
            target_dn_sat = running_high - m * est_hl_arr + ema_hl_day / 8
            reach_up_sat = (highs >= target_up_sat) & est_valid
            reach_dn_sat = (lows <= target_dn_sat) & est_valid
            row[f"Bsat_up_{m}"] = bool(reach_up_sat.any())
            row[f"Bsat_dn_{m}"] = bool(reach_dn_sat.any())

        rows.append(row)

    df = pd.DataFrame(rows).set_index("date")
    print(f"\nDays processed: {len(df)} (skipped: {skipped}, no EstHL in window: {no_est_hl})")
    df.to_csv(OUT_DIR / "reach_production_esthl_raw.csv")

    # ── Tier-level summary ──
    print("\n" + "─" * 100)
    print("Reach probability by tier — Upper side")
    print("─" * 100)
    print(f"{'Tier':<12} {'Def':<7} {'N':>4} " +
          " ".join([f"  m={m:<5}" for m in MULTIPLES]))
    print("─" * 100)

    summary_rows = []
    for tier in TIER_LABELS:
        sub = df[df["tier"] == tier]
        n = len(sub)
        for defn, prefix in [("B-old", "Bold"), ("B-est", "Best"), ("B-sat", "Bsat")]:
            probs = []
            for m in MULTIPLES:
                p = sub[f"{prefix}_up_{m}"].mean() * 100
                probs.append(p)
            print(f"{tier:<12} {defn:<7} {n:>4} " +
                  " ".join([f"  {p:>5.1f}%" for p in probs]))
            summary_rows.append({
                "tier": tier, "def": defn, "dir": "up", "N": n,
                **{f"p_{m}": p / 100 for m, p in zip(MULTIPLES, probs)},
            })
        print()

    print("\n" + "─" * 100)
    print("Reach probability by tier — Lower side")
    print("─" * 100)
    print(f"{'Tier':<12} {'Def':<7} {'N':>4} " +
          " ".join([f"  m={m:<5}" for m in MULTIPLES]))
    print("─" * 100)
    for tier in TIER_LABELS:
        sub = df[df["tier"] == tier]
        n = len(sub)
        for defn, prefix in [("B-old", "Bold"), ("B-est", "Best"), ("B-sat", "Bsat")]:
            probs = []
            for m in MULTIPLES:
                p = sub[f"{prefix}_dn_{m}"].mean() * 100
                probs.append(p)
            print(f"{tier:<12} {defn:<7} {n:>4} " +
                  " ".join([f"  {p:>5.1f}%" for p in probs]))
            summary_rows.append({
                "tier": tier, "def": defn, "dir": "dn", "N": n,
                **{f"p_{m}": p / 100 for m, p in zip(MULTIPLES, probs)},
            })
        print()

    pd.DataFrame(summary_rows).to_csv(OUT_DIR / "reach_production_esthl_summary.csv", index=False)

    # ── EstHL / EmaHL ratio inspection ──
    print("\n" + "─" * 100)
    print("EstHL vs EmaHL ratio by tier (first valid / last valid in 2h window)")
    print("─" * 100)
    print(f"{'Tier':<12} {'N':>4} {'first_mean':>12} {'first_med':>11} {'last_mean':>11} {'last_med':>10}")
    for tier in TIER_LABELS:
        sub = df[df["tier"] == tier]
        n = len(sub)
        fm = sub["est_hl_ratio_first"].mean()
        fmed = sub["est_hl_ratio_first"].median()
        lm = sub["est_hl_ratio_last"].mean()
        lmed = sub["est_hl_ratio_last"].median()
        print(f"{tier:<12} {n:>4} {fm:>11.3f}  {fmed:>10.3f}  {lm:>10.3f}  {lmed:>9.3f}")

    # ── Focus comparison: S001 SatZone exact (B-sat m=1.0) by tier ──
    print("\n" + "─" * 100)
    print("⭐ S001 SatZone exact (B-sat m=1.0) — upper / lower / either / both")
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

    # ── Plot ──
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle("H092 Phase 2 — Production EstHL reach (08:45-10:45 window)",
                 fontsize=12, fontweight="bold")

    x = np.arange(len(TIER_LABELS))
    w = 0.27
    def_colors = {"B-old": "#1e88e5", "B-est": "#fb8c00", "B-sat": "#e53935"}

    # (a) Upper @ m=0.618
    ax = axes[0, 0]
    for i, (defn, prefix) in enumerate([("B-old", "Bold"), ("B-est", "Best"), ("B-sat", "Bsat")]):
        vals = [df[df["tier"] == t][f"{prefix}_up_0.618"].mean() * 100 for t in TIER_LABELS]
        ax.bar(x + (i - 1) * w, vals, w, color=def_colors[defn], label=defn)
    ax.set_xticks(x)
    ax.set_xticklabels(TIER_LABELS, fontsize=9)
    ax.set_ylabel("P(upper reach) [%]")
    ax.set_title("(a) Upper @ m=0.618")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    # (b) Upper @ m=1.0 (= SatZone for B-sat)
    ax = axes[0, 1]
    for i, (defn, prefix) in enumerate([("B-old", "Bold"), ("B-est", "Best"), ("B-sat", "Bsat")]):
        vals = [df[df["tier"] == t][f"{prefix}_up_1.0"].mean() * 100 for t in TIER_LABELS]
        ax.bar(x + (i - 1) * w, vals, w, color=def_colors[defn], label=defn)
    ax.set_xticks(x)
    ax.set_xticklabels(TIER_LABELS, fontsize=9)
    ax.set_ylabel("P(upper reach) [%]")
    ax.set_title("(b) Upper @ m=1.0 (B-sat m=1.0 = S001 SatZone Upper)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    # (c) Lower @ m=0.618
    ax = axes[1, 0]
    for i, (defn, prefix) in enumerate([("B-old", "Bold"), ("B-est", "Best"), ("B-sat", "Bsat")]):
        vals = [df[df["tier"] == t][f"{prefix}_dn_0.618"].mean() * 100 for t in TIER_LABELS]
        ax.bar(x + (i - 1) * w, vals, w, color=def_colors[defn], label=defn)
    ax.set_xticks(x)
    ax.set_xticklabels(TIER_LABELS, fontsize=9)
    ax.set_ylabel("P(lower reach) [%]")
    ax.set_title("(c) Lower @ m=0.618")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    # (d) Lower @ m=1.0
    ax = axes[1, 1]
    for i, (defn, prefix) in enumerate([("B-old", "Bold"), ("B-est", "Best"), ("B-sat", "Bsat")]):
        vals = [df[df["tier"] == t][f"{prefix}_dn_1.0"].mean() * 100 for t in TIER_LABELS]
        ax.bar(x + (i - 1) * w, vals, w, color=def_colors[defn], label=defn)
    ax.set_xticks(x)
    ax.set_xticklabels(TIER_LABELS, fontsize=9)
    ax.set_ylabel("P(lower reach) [%]")
    ax.set_title("(d) Lower @ m=1.0 (B-sat = S001 SatZone Lower)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    plt.tight_layout()
    out_png = OUT_DIR / "h092_phase2_reach_prod_esthl.png"
    plt.savefig(out_png, dpi=140)
    print(f"\nPlot saved: {out_png}")


if __name__ == "__main__":
    main()
