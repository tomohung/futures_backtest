#!/usr/bin/env python3
"""H092 Phase 2 — Optimal m scan.

掃描 m = 0.10 ~ 1.50 (step 0.05) 找各定義下的真正最佳 m。

定義:
    A (open-anchored, EmaHL): target = day_open + m × EmaHL
        profit/unit = m (EmaHL units)
    B-est (running-anchored, EstHL, no buffer):
        target = running_low + m × EstHL (per-bar dynamic)
        profit/unit = m × (EstHL/EmaHL)
    B-sat (running-anchored, EstHL, /8 buffer = S001):
        target = running_low + m × EstHL − EmaHL/8
        profit/unit = m × (EstHL/EmaHL) − 1/8

每個 tier × direction × definition 找 argmax E[R/unit]。
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
OUT_DIR.mkdir(parents=True, exist_ok=True)

WINDOW_START = time(8, 45)
WINDOW_END = time(10, 45)

M_GRID = np.round(np.arange(0.10, 1.51, 0.05), 3)


def load_full_day_bars():
    print("Loading full-day 1m bars...")
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        bars = conn.execute(
            """
            SELECT timestamp,
                   open AS Open, high AS High, low AS Low,
                   close AS Close, volume AS Volume
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


def main():
    print("=" * 100)
    print("H092 Phase 2 — Fine-grained m scan to find optimal exit level")
    print("=" * 100)

    tier_df = load_tier_data()[0]
    print(f"Tier days: {len(tier_df)}")

    bars = load_full_day_bars()
    print("Running compute_estimate_hl_zones...")
    bars = compute_estimate_hl_zones(bars)

    bars["trade_date"] = bars.index.normalize()
    bars_by_date = {d: g for d, g in bars.groupby("trade_date", sort=False)}

    print("Computing per-day max reach metrics + per-day est_hl/ema_hl ratio...")
    rows = []
    for d in tier_df.index:
        day_bars = bars_by_date.get(d)
        if day_bars is None or day_bars.empty:
            continue
        win = day_bars[(day_bars.index.time >= WINDOW_START)
                       & (day_bars.index.time < WINDOW_END)]
        if win.empty:
            continue

        highs = win["High"].values
        lows = win["Low"].values
        est_hl_arr = win["EstHL"].values
        ema_hl_arr = win["EmaHL"].values

        # Day's EmaHL (fixed)
        valid_ema = ~np.isnan(ema_hl_arr)
        if not valid_ema.any():
            continue
        ema_hl = float(ema_hl_arr[valid_ema][0])
        if ema_hl <= 0:
            continue

        day_open = float(win.iloc[0]["Open"])

        # Open-anchored max ratios (A definition)
        max_old_up = (highs.max() - day_open) / ema_hl
        max_old_dn = (day_open - lows.min()) / ema_hl

        # Running anchors
        running_low = np.minimum.accumulate(lows)
        running_high = np.maximum.accumulate(highs)

        # EstHL validity
        est_valid = ~np.isnan(est_hl_arr) & (est_hl_arr > 0)

        if est_valid.any():
            # B-est: per-bar ratio = (high - running_low) / est_hl
            # max_ratio: max over valid bars
            ext_up_no_buf = highs - running_low
            ext_dn_no_buf = running_high - lows
            with np.errstate(invalid="ignore", divide="ignore"):
                ratio_est_up = np.where(est_valid, ext_up_no_buf / est_hl_arr, -np.inf)
                ratio_est_dn = np.where(est_valid, ext_dn_no_buf / est_hl_arr, -np.inf)

            # B-sat: with EmaHL/8 buffer
            buf = ema_hl / 8.0
            ext_up_buf = ext_up_no_buf + buf
            ext_dn_buf = ext_dn_no_buf + buf
            with np.errstate(invalid="ignore", divide="ignore"):
                ratio_sat_up = np.where(est_valid, ext_up_buf / est_hl_arr, -np.inf)
                ratio_sat_dn = np.where(est_valid, ext_dn_buf / est_hl_arr, -np.inf)

            max_est_up = float(np.max(ratio_est_up))
            max_est_dn = float(np.max(ratio_est_dn))
            max_sat_up = float(np.max(ratio_sat_up))
            max_sat_dn = float(np.max(ratio_sat_dn))

            # Average ratio for profit calculation
            mean_ratio = float(np.mean(est_hl_arr[est_valid]) / ema_hl)
        else:
            max_est_up = max_est_dn = max_sat_up = max_sat_dn = -np.inf
            mean_ratio = 1.0

        rows.append({
            "date": d,
            "tier": tier_df.at[d, "tier"],
            "ema_hl": ema_hl,
            "max_old_up": max_old_up,
            "max_old_dn": max_old_dn,
            "max_est_up": max_est_up,
            "max_est_dn": max_est_dn,
            "max_sat_up": max_sat_up,
            "max_sat_dn": max_sat_dn,
            "est_hl_ratio_mean": mean_ratio,
        })

    df = pd.DataFrame(rows).set_index("date")
    print(f"Processed days: {len(df)}")

    # ── Scan m for each tier × direction × definition ──
    print("\n" + "─" * 100)
    print("Scanning m grid for E[R/unit] optimum")
    print("─" * 100)

    scan_rows = []
    for tier in TIER_LABELS:
        sub = df[df["tier"] == tier]
        n = len(sub)
        for direction in ["up", "dn"]:
            max_old = sub[f"max_old_{direction}"].values
            max_est = sub[f"max_est_{direction}"].values
            max_sat = sub[f"max_sat_{direction}"].values
            ratios = sub["est_hl_ratio_mean"].values
            for m in M_GRID:
                # A (open-anchored, EmaHL)
                reach_old = max_old >= m
                er_old = (reach_old * m).mean()

                # B-est: profit_i = m × ratio_i, summed only over reach_i = 1
                reach_est = max_est >= m
                er_est = (reach_est * (m * ratios)).mean()

                # B-sat: profit_i = m × ratio_i − 1/8
                reach_sat = max_sat >= m
                er_sat = (reach_sat * (m * ratios - 1 / 8)).mean()

                scan_rows.append({
                    "tier": tier, "dir": direction, "N": n, "m": m,
                    "P_A": float(reach_old.mean()),
                    "ER_A": float(er_old),
                    "P_Best": float(reach_est.mean()),
                    "ER_Best": float(er_est),
                    "P_Bsat": float(reach_sat.mean()),
                    "ER_Bsat": float(er_sat),
                })
    scan_df = pd.DataFrame(scan_rows)
    scan_df.to_csv(OUT_DIR / "optimal_m_scan.csv", index=False)

    # ── Report optima ──
    print(f"\n{'Tier':<12} {'Dir':<4} {'Def':<6} {'opt_m':>6} {'P(reach)':>10} {'E[R/unit]':>10}")
    print("─" * 60)
    summary = []
    for tier in TIER_LABELS:
        for direction in ["up", "dn"]:
            sub = scan_df[(scan_df["tier"] == tier) & (scan_df["dir"] == direction)]
            for defn, p_col, er_col in [("A", "P_A", "ER_A"),
                                          ("B-est", "P_Best", "ER_Best"),
                                          ("B-sat", "P_Bsat", "ER_Bsat")]:
                best_idx = sub[er_col].idxmax()
                best_row = sub.loc[best_idx]
                print(f"{tier:<12} {direction:<4} {defn:<6} "
                      f"{best_row['m']:>6.2f} {best_row[p_col]*100:>9.1f}% "
                      f"{best_row[er_col]:>10.4f}")
                summary.append({
                    "tier": tier, "dir": direction, "def": defn,
                    "opt_m": float(best_row["m"]),
                    "P_at_opt": float(best_row[p_col]),
                    "ER_at_opt": float(best_row[er_col]),
                })
    pd.DataFrame(summary).to_csv(OUT_DIR / "optimal_m_summary.csv", index=False)

    # ── Plot E[R/unit] vs m ──
    fig, axes = plt.subplots(4, 2, figsize=(15, 14))
    fig.suptitle("H092 Phase 2 — E[R/unit] vs m (single-level exit) by tier × direction",
                 fontsize=13, fontweight="bold")
    def_colors = {"A": "#1e88e5", "B-est": "#fb8c00", "B-sat": "#e53935"}

    for i, tier in enumerate(TIER_LABELS):
        for j, (direction, dir_label) in enumerate([("up", "Long (upper)"),
                                                      ("dn", "Short (lower)")]):
            ax = axes[i, j]
            sub = scan_df[(scan_df["tier"] == tier) & (scan_df["dir"] == direction)]
            ms = sub["m"].values

            for defn, er_col in [("A", "ER_A"), ("B-est", "ER_Best"), ("B-sat", "ER_Bsat")]:
                ers = sub[er_col].values
                ax.plot(ms, ers, "-o", color=def_colors[defn],
                        label=defn, markersize=3, linewidth=1.5)
                # Mark optimum
                opt_idx = np.argmax(ers)
                ax.scatter([ms[opt_idx]], [ers[opt_idx]],
                           color=def_colors[defn], s=80, zorder=5,
                           edgecolor="black", linewidth=1.5)
                ax.annotate(f"m={ms[opt_idx]:.2f}\n{ers[opt_idx]:.3f}",
                            xy=(ms[opt_idx], ers[opt_idx]),
                            xytext=(8, 8), textcoords="offset points",
                            fontsize=7, color=def_colors[defn])

            ax.axvline(0.618, color="grey", linestyle=":", linewidth=0.5, label="m=0.618")
            ax.axhline(0, color="black", linewidth=0.4)
            ax.set_xlabel("m")
            ax.set_ylabel("E[R/unit] (EmaHL units)")
            ax.set_title(f"{tier} — {dir_label}", fontsize=10)
            ax.legend(fontsize=7, loc="upper right")
            ax.grid(alpha=0.3)

    plt.tight_layout()
    out_png = OUT_DIR / "h092_phase2_optimal_m.png"
    plt.savefig(out_png, dpi=140)
    print(f"\nPlot saved: {out_png}")


if __name__ == "__main__":
    main()
