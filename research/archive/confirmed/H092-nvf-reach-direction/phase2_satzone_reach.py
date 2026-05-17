#!/usr/bin/env python3
"""H092 Phase 2 — SatZone reach (m=0.875) 加入比較.

S001 SatZone:
    Upper = session_low  + EmaHL − EmaHL/8 = session_low + 0.875 × EmaHL
    Lower = session_high − EmaHL + EmaHL/8 = session_high − 0.875 × EmaHL

新 multiples = [0.618, 0.75, 0.875 (=SatZone), 1.0, 1.2]
5 個 definitions:A / B / C5 / C10 / C15

使用方式:
    uv run python research/active/H092-nvf-reach-direction/phase2_satzone_reach.py
"""

import sys
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
from phase2_reach_definitions import (
    load_bars_window, day_reach_metrics, LAGS,
)

OUT_DIR = Path("research/active/H092-nvf-reach-direction/results")
MULTIPLES = [0.618, 0.75, 0.875, 1.0, 1.2]
SATZONE_M = 0.875


def main():
    print("=" * 100)
    print("H092 Phase 2 — SatZone (m=0.875) reach probability")
    print("=" * 100)

    tier_df = load_tier_data()[0]
    bars_by_date = load_bars_window()

    rows = []
    for d in tier_df.index:
        day_bars = bars_by_date.get(d)
        if day_bars is None or len(day_bars) == 0:
            continue
        highs = day_bars["high"].values.astype(float)
        lows = day_bars["low"].values.astype(float)
        day_open = float(day_bars.iloc[0]["open"])
        ema_hl = float(tier_df.at[d, "ema_hl"])
        metrics = day_reach_metrics(highs, lows, day_open, ema_hl)
        if metrics is None:
            continue
        row = {"date": d, "tier": tier_df.at[d, "tier"],
               "year": tier_df.at[d, "year"], "ema_hl": ema_hl}
        for (defn, dir_), val in metrics.items():
            row[f"{defn}_{dir_}"] = val
        rows.append(row)
    df = pd.DataFrame(rows).set_index("date")
    print(f"Computed days: {len(df)}")

    DEFS = ["A", "B", "C5", "C10", "C15"]

    # ── Upper SatZone reach across definitions ──
    print("\n" + "─" * 100)
    print("Upper reach probability (含 SatZone m=0.875)")
    print("─" * 100)
    print(f"{'Tier':<12} {'Def':<5} {'N':>4} " + " ".join([f"  m={m:<6}" for m in MULTIPLES]))
    print(f"{'':12} {'':5} {'':>4} " + " ".join(["   <-- 0.875 = SatZone" if abs(m-SATZONE_M)<1e-9 else "         " for m in MULTIPLES]))
    print("─" * 100)
    for tier in TIER_LABELS:
        sub = df[df["tier"] == tier]
        n = len(sub)
        for defn in DEFS:
            col = f"{defn}_up"
            probs = [(sub[col] >= m).mean() * 100 for m in MULTIPLES]
            print(f"{tier:<12} {defn:<5} {n:>4} " +
                  " ".join([f"  {p:>5.1f}% " for p in probs]))
        print()

    # ── Lower SatZone reach across definitions ──
    print("\n" + "─" * 100)
    print("Lower reach probability (含 SatZone m=0.875)")
    print("─" * 100)
    print(f"{'Tier':<12} {'Def':<5} {'N':>4} " + " ".join([f"  m={m:<6}" for m in MULTIPLES]))
    print("─" * 100)
    for tier in TIER_LABELS:
        sub = df[df["tier"] == tier]
        n = len(sub)
        for defn in DEFS:
            col = f"{defn}_dn"
            probs = [(sub[col] >= m).mean() * 100 for m in MULTIPLES]
            print(f"{tier:<12} {defn:<5} {n:>4} " +
                  " ".join([f"  {p:>5.1f}% " for p in probs]))
        print()

    # ── Focus: SatZone (0.875) by tier, B definition (the most realistic) ──
    print("\n" + "─" * 100)
    print("⭐ Focus: P(reach SatZone Upper/Lower) under B (live SatZone) by tier")
    print("─" * 100)
    print(f"{'Tier':<12} {'N':>4} {'upper_satzone':>14} {'lower_satzone':>14} {'either':>10} {'both':>8}")
    sat_rows = []
    for tier in TIER_LABELS:
        sub = df[df["tier"] == tier]
        n = len(sub)
        up_hit = sub["B_up"] >= SATZONE_M
        dn_hit = sub["B_dn"] >= SATZONE_M
        p_up = up_hit.mean()
        p_dn = dn_hit.mean()
        p_either = (up_hit | dn_hit).mean()
        p_both = (up_hit & dn_hit).mean()
        print(f"{tier:<12} {n:>4} {p_up*100:>12.1f}%  {p_dn*100:>12.1f}%  "
              f"{p_either*100:>8.1f}%  {p_both*100:>6.1f}%")
        sat_rows.append({
            "tier": tier, "N": n,
            "P_upper_satzone": p_up, "P_lower_satzone": p_dn,
            "P_either": p_either, "P_both": p_both,
        })
    pd.DataFrame(sat_rows).to_csv(OUT_DIR / "satzone_reach_by_tier.csv", index=False)

    # ── SatZone reach yearly for strong GO ──
    print("\n" + "─" * 100)
    print("Strong-GO yearly SatZone reach (B definition)")
    print("─" * 100)
    strong = df[df["tier"] == "strong GO"]
    rows_y = []
    for y in sorted(strong["year"].unique()):
        sub = strong[strong["year"] == y]
        if len(sub) < 10:
            continue
        up = (sub["B_up"] >= SATZONE_M).mean()
        dn = (sub["B_dn"] >= SATZONE_M).mean()
        either = ((sub["B_up"] >= SATZONE_M) | (sub["B_dn"] >= SATZONE_M)).mean()
        both = ((sub["B_up"] >= SATZONE_M) & (sub["B_dn"] >= SATZONE_M)).mean()
        rows_y.append({"year": int(y), "N": len(sub),
                       "upper": up, "lower": dn, "either": either, "both": both,
                       "diff_U_minus_L_pp": (up - dn) * 100})
    sg_yr = pd.DataFrame(rows_y)
    print(sg_yr.to_string(index=False, formatters={
        "upper": lambda v: f"{v*100:.1f}%",
        "lower": lambda v: f"{v*100:.1f}%",
        "either": lambda v: f"{v*100:.1f}%",
        "both": lambda v: f"{v*100:.1f}%",
        "diff_U_minus_L_pp": lambda v: f"{v:+.1f}",
    }))
    sg_yr.to_csv(OUT_DIR / "satzone_strong_go_yearly.csv", index=False)

    # ── Plot ──
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    fig.suptitle("H092 Phase 2 — SatZone reach (m=0.875) within first 2h",
                 fontsize=12, fontweight="bold")

    # (a) Upper SatZone reach across tiers and definitions
    ax = axes[0]
    x = np.arange(len(TIER_LABELS))
    w = 0.16
    def_colors = {"A": "#1e88e5", "B": "#e53935", "C5": "#fb8c00",
                  "C10": "#43a047", "C15": "#7e57c2"}
    for i, defn in enumerate(DEFS):
        vals = []
        for tier in TIER_LABELS:
            sub = df[df["tier"] == tier]
            vals.append((sub[f"{defn}_up"] >= SATZONE_M).mean() * 100)
        ax.bar(x + (i - 2) * w, vals, w, color=def_colors[defn], label=defn)
    ax.set_xticks(x)
    ax.set_xticklabels(TIER_LABELS, fontsize=9)
    ax.set_ylabel("P(reach Upper SatZone) [%]")
    ax.set_title("(a) Upper SatZone (m=0.875) reach by definition")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    # (b) Lower SatZone reach
    ax = axes[1]
    for i, defn in enumerate(DEFS):
        vals = []
        for tier in TIER_LABELS:
            sub = df[df["tier"] == tier]
            vals.append((sub[f"{defn}_dn"] >= SATZONE_M).mean() * 100)
        ax.bar(x + (i - 2) * w, vals, w, color=def_colors[defn], label=defn)
    ax.set_xticks(x)
    ax.set_xticklabels(TIER_LABELS, fontsize=9)
    ax.set_ylabel("P(reach Lower SatZone) [%]")
    ax.set_title("(b) Lower SatZone (m=0.875) reach by definition")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    plt.tight_layout()
    out_png = OUT_DIR / "h092_phase2_satzone_reach.png"
    plt.savefig(out_png, dpi=140)
    print(f"\nPlot saved: {out_png}")


if __name__ == "__main__":
    main()
