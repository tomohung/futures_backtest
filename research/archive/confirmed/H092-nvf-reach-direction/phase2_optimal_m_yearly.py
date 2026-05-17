#!/usr/bin/env python3
"""H092 Phase 2 — Year-by-year stability of optimal m.

對 phase2_optimal_m_scan 的延伸:
    - 把 m scan 拆到每一年看
    - 找每年每個 tier × direction × definition 的最佳 m
    - 檢驗:pooled 最佳 m 在每一年是否仍接近最佳?
    - 看 2025/2026 是否是異常年(對應 distribution.md 提到的 regime 反例)

Definitions:
    A     — open-anchored, m × EmaHL
    B-sat — running-anchored, m × EstHL − EmaHL/8 (S001 production)
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
    print("H092 Phase 2 — Yearly stability of optimal m")
    print("=" * 100)

    tier_df = load_tier_data()[0]
    bars = load_full_day_bars()
    print("Running compute_estimate_hl_zones...")
    bars = compute_estimate_hl_zones(bars)
    bars["trade_date"] = bars.index.normalize()
    bars_by_date = {d: g for d, g in bars.groupby("trade_date", sort=False)}

    print("Computing per-day metrics...")
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
        valid_ema = ~np.isnan(ema_hl_arr)
        if not valid_ema.any():
            continue
        ema_hl = float(ema_hl_arr[valid_ema][0])
        if ema_hl <= 0:
            continue
        day_open = float(win.iloc[0]["Open"])
        max_old_up = (highs.max() - day_open) / ema_hl
        max_old_dn = (day_open - lows.min()) / ema_hl
        running_low = np.minimum.accumulate(lows)
        running_high = np.maximum.accumulate(highs)
        est_valid = ~np.isnan(est_hl_arr) & (est_hl_arr > 0)
        if est_valid.any():
            ext_up_buf = highs - running_low + ema_hl / 8
            ext_dn_buf = running_high - lows + ema_hl / 8
            with np.errstate(invalid="ignore", divide="ignore"):
                ratio_sat_up = np.where(est_valid, ext_up_buf / est_hl_arr, -np.inf)
                ratio_sat_dn = np.where(est_valid, ext_dn_buf / est_hl_arr, -np.inf)
            max_sat_up = float(np.max(ratio_sat_up))
            max_sat_dn = float(np.max(ratio_sat_dn))
            mean_ratio = float(np.mean(est_hl_arr[est_valid]) / ema_hl)
        else:
            max_sat_up = max_sat_dn = -np.inf
            mean_ratio = 1.0
        rows.append({
            "date": d,
            "year": d.year,
            "tier": tier_df.at[d, "tier"],
            "ema_hl": ema_hl,
            "max_old_up": max_old_up,
            "max_old_dn": max_old_dn,
            "max_sat_up": max_sat_up,
            "max_sat_dn": max_sat_dn,
            "ratio": mean_ratio,
        })
    df = pd.DataFrame(rows).set_index("date")
    print(f"Processed days: {len(df)}")

    # Scan m for each year × tier × direction × def
    print("\nScanning m per year × tier × direction...")
    years = sorted(df["year"].unique())
    yearly_rows = []
    for y in years:
        df_y = df[df["year"] == y]
        for tier in TIER_LABELS:
            sub = df_y[df_y["tier"] == tier]
            n = len(sub)
            if n < 10:
                continue
            for direction in ["up", "dn"]:
                max_old = sub[f"max_old_{direction}"].values
                max_sat = sub[f"max_sat_{direction}"].values
                ratios = sub["ratio"].values
                for m in M_GRID:
                    reach_old = max_old >= m
                    er_old = float((reach_old * m).mean())
                    reach_sat = max_sat >= m
                    er_sat = float((reach_sat * (m * ratios - 1 / 8)).mean())
                    yearly_rows.append({
                        "year": int(y), "tier": tier, "dir": direction, "N": n, "m": m,
                        "P_A": float(reach_old.mean()), "ER_A": er_old,
                        "P_Bsat": float(reach_sat.mean()), "ER_Bsat": er_sat,
                    })
    yearly_df = pd.DataFrame(yearly_rows)
    yearly_df.to_csv(OUT_DIR / "optimal_m_yearly_scan.csv", index=False)

    # Find optima per year × tier × dir × def
    opt_rows = []
    for y in years:
        for tier in TIER_LABELS:
            for direction in ["up", "dn"]:
                sub = yearly_df[(yearly_df["year"] == y) &
                                 (yearly_df["tier"] == tier) &
                                 (yearly_df["dir"] == direction)]
                if sub.empty:
                    continue
                # A
                best_a_idx = sub["ER_A"].idxmax()
                row_a = sub.loc[best_a_idx]
                # B-sat
                best_b_idx = sub["ER_Bsat"].idxmax()
                row_b = sub.loc[best_b_idx]
                opt_rows.append({
                    "year": y, "tier": tier, "dir": direction, "N": int(sub["N"].iloc[0]),
                    "A_opt_m": float(row_a["m"]),
                    "A_P": float(row_a["P_A"]),
                    "A_ER": float(row_a["ER_A"]),
                    "Bsat_opt_m": float(row_b["m"]),
                    "Bsat_P": float(row_b["P_Bsat"]),
                    "Bsat_ER": float(row_b["ER_Bsat"]),
                })
    opt_df = pd.DataFrame(opt_rows)
    opt_df.to_csv(OUT_DIR / "optimal_m_yearly_summary.csv", index=False)

    # Print: opt_m per year for A & B-sat by tier × dir
    print("\n" + "=" * 100)
    print("Optimal m per year — A definition (EmaHL ladder)")
    print("=" * 100)
    for direction, dir_label in [("up", "Long"), ("dn", "Short")]:
        print(f"\n  {dir_label}:")
        print(f"  {'Year':<6} " + " ".join([f"{t:>14}" for t in TIER_LABELS]))
        for y in years:
            line = f"  {y:<6} "
            for tier in TIER_LABELS:
                r = opt_df[(opt_df["year"] == y) & (opt_df["tier"] == tier) & (opt_df["dir"] == direction)]
                if r.empty:
                    line += "             — "
                else:
                    m = r.iloc[0]["A_opt_m"]
                    er = r.iloc[0]["A_ER"]
                    line += f" m={m:.2f}/{er:.3f}"
            print(line)

    print("\n" + "=" * 100)
    print("Optimal m per year — B-sat (S001 SatZone)")
    print("=" * 100)
    for direction, dir_label in [("up", "Long"), ("dn", "Short")]:
        print(f"\n  {dir_label}:")
        print(f"  {'Year':<6} " + " ".join([f"{t:>14}" for t in TIER_LABELS]))
        for y in years:
            line = f"  {y:<6} "
            for tier in TIER_LABELS:
                r = opt_df[(opt_df["year"] == y) & (opt_df["tier"] == tier) & (opt_df["dir"] == direction)]
                if r.empty:
                    line += "             — "
                else:
                    m = r.iloc[0]["Bsat_opt_m"]
                    er = r.iloc[0]["Bsat_ER"]
                    line += f" m={m:.2f}/{er:.3f}"
            print(line)

    # ── IS/OOS check: use 2021-2024 IS optimum on 2025-2026 OOS ──
    print("\n" + "=" * 100)
    print("IS (2021-2024) vs OOS (2025-2026) stability check")
    print("=" * 100)

    POOLED_OPT_A = {  # from earlier pooled scan
        ("deep STOP", "up"): 0.30, ("deep STOP", "dn"): 0.35,
        ("mid STOP", "up"): 0.40, ("mid STOP", "dn"): 0.35,
        ("mid GO", "up"): 0.45, ("mid GO", "dn"): 0.30,
        ("strong GO", "up"): 0.45, ("strong GO", "dn"): 0.60,
    }
    POOLED_OPT_BSAT = {
        ("deep STOP", "up"): 0.60, ("deep STOP", "dn"): 0.70,
        ("mid STOP", "up"): 0.60, ("mid STOP", "dn"): 0.55,
        ("mid GO", "up"): 0.60, ("mid GO", "dn"): 0.60,
        ("strong GO", "up"): 0.60, ("strong GO", "dn"): 0.55,
    }

    print(f"\n{'Tier':<12} {'Dir':<4} {'Def':<6} "
          f"{'IS_opt_m':>9} {'IS_ER':>8} | {'OOS_opt_m':>10} {'OOS_ER':>8} | "
          f"{'OOS@IS_m':>10} {'gap':>7}")
    print("─" * 100)
    is_oos_rows = []
    for tier in TIER_LABELS:
        for direction in ["up", "dn"]:
            for defn in ["A", "Bsat"]:
                er_col = f"ER_{defn}"
                # IS: use yearly_df pooled over 2021-2024
                is_sub = yearly_df[(yearly_df["tier"] == tier) &
                                    (yearly_df["dir"] == direction) &
                                    (yearly_df["year"].between(2021, 2024))]
                if is_sub.empty:
                    continue
                # weighted by N per year
                is_grouped = is_sub.groupby("m").apply(
                    lambda g: (g[er_col] * g["N"]).sum() / g["N"].sum()
                )
                is_opt_m = is_grouped.idxmax()
                is_er = is_grouped.max()

                # OOS: 2025-2026
                oos_sub = yearly_df[(yearly_df["tier"] == tier) &
                                     (yearly_df["dir"] == direction) &
                                     (yearly_df["year"].between(2025, 2026))]
                if oos_sub.empty:
                    continue
                oos_grouped = oos_sub.groupby("m").apply(
                    lambda g: (g[er_col] * g["N"]).sum() / g["N"].sum()
                )
                oos_opt_m = oos_grouped.idxmax()
                oos_er = oos_grouped.max()
                # OOS performance AT IS optimum
                oos_at_is = float(oos_grouped.loc[is_opt_m]) if is_opt_m in oos_grouped.index else np.nan
                gap = oos_er - oos_at_is

                print(f"{tier:<12} {direction:<4} {defn:<6} "
                      f"{is_opt_m:>9.2f} {is_er:>8.4f} | {oos_opt_m:>10.2f} {oos_er:>8.4f} | "
                      f"{oos_at_is:>10.4f} {gap:>+7.4f}")
                is_oos_rows.append({
                    "tier": tier, "dir": direction, "def": defn,
                    "IS_opt_m": float(is_opt_m), "IS_ER": float(is_er),
                    "OOS_opt_m": float(oos_opt_m), "OOS_ER": float(oos_er),
                    "OOS_at_IS_m": float(oos_at_is),
                    "overfit_gap": float(gap),
                })
    pd.DataFrame(is_oos_rows).to_csv(OUT_DIR / "is_oos_optimal_m.csv", index=False)

    # ── Plot opt_m drift by year ──
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle("H092 Phase 2 — Yearly optimal m drift (A vs B-sat)",
                 fontsize=13, fontweight="bold")
    for i, defn in enumerate(["A", "Bsat"]):
        for j, (direction, dir_label) in enumerate([("up", "Long"), ("dn", "Short")]):
            ax = axes[i, j]
            for tier in TIER_LABELS:
                sub = opt_df[(opt_df["tier"] == tier) & (opt_df["dir"] == direction)].sort_values("year")
                col_m = f"{defn}_opt_m"
                ax.plot(sub["year"], sub[col_m], "-o",
                        color=TIER_COLORS[tier], label=f"{tier}", markersize=6)
            ax.set_xlabel("year")
            ax.set_ylabel(f"optimal m ({defn})")
            ax.set_title(f"({chr(97 + i*2 + j)}) {defn} — {dir_label}")
            ax.legend(fontsize=8)
            ax.grid(alpha=0.3)
            ax.axhline(0.618, color="grey", linestyle=":", linewidth=0.5, label="0.618")
            ax.set_ylim(0, 1.5)

    plt.tight_layout()
    out_png = OUT_DIR / "h092_phase2_opt_m_yearly.png"
    plt.savefig(out_png, dpi=140)
    print(f"\nPlot saved: {out_png}")


if __name__ == "__main__":
    main()
