#!/usr/bin/env python3
"""H092 — Strong-GO cutoff sensitivity.

驗證 strong-GO lower bias (−10pp at 1.0×) 是否依賴於 ≥1.30 這個 arbitrary cutoff。

掃描兩種切法:
    A) 絕對值: 1.10, 1.15, 1.20, 1.25, 1.30, 1.35, 1.40, 1.50
    B) 百分位: 60th, 70th, 75th, 80th, 85th, 90th

對每個 cutoff 計算:
    - N
    - reach upper / lower / diff at 0.618 / 0.75 / 1.0 / 1.2
    - cross-year consistency
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent))
from explore import load_data

OUT_DIR = Path("research/active/H092-nvf-reach-direction/results")


def diff_stats(sub, multiples):
    out = {}
    for m in multiples:
        u = (sub["up_ratio"] >= m).mean()
        l = (sub["dn_ratio"] >= m).mean()
        out[f"u_{m}"] = u
        out[f"l_{m}"] = l
        out[f"d_{m}"] = (u - l) * 100
    return out


def cross_year_consistency(df_sub, multiples):
    """For each multiple, return (avg_pp, n_neg, n_yrs) across years with N>=10."""
    result = {}
    years = sorted(df_sub["year"].unique())
    for m in multiples:
        diffs = []
        for y in years:
            sy = df_sub[df_sub["year"] == y]
            if len(sy) < 10:
                continue
            d = (sy["up_ratio"] >= m).mean() - (sy["dn_ratio"] >= m).mean()
            diffs.append(d * 100)
        if not diffs:
            result[m] = (np.nan, 0, 0)
            continue
        avg = float(np.mean(diffs))
        n_neg = sum(1 for d in diffs if d < 0)
        result[m] = (avg, n_neg, len(diffs))
    return result


def main():
    print("=" * 78)
    print("H092 — Strong-GO cutoff sensitivity")
    print("=" * 78)

    df = load_data()
    print(f"Total days: {len(df)}")
    print(f"night_norm distribution:")
    for p in [50, 60, 70, 75, 80, 85, 90, 95]:
        v = np.percentile(df["night_norm"], p)
        print(f"  p{p:2d} = {v:.3f}")

    multiples = [0.618, 0.75, 1.0, 1.2]

    # ── A) absolute cutoffs ──
    print("\n" + "─" * 78)
    print("A) Absolute cutoffs:  norm >= X  → strong-GO bucket")
    print("─" * 78)
    abs_cutoffs = [1.10, 1.15, 1.20, 1.25, 1.30, 1.35, 1.40, 1.50]
    abs_rows = []
    for c in abs_cutoffs:
        sub = df[df["night_norm"] >= c]
        n = len(sub)
        pct = n / len(df) * 100
        row = {"cutoff": c, "N": n, "%": pct}
        row.update(diff_stats(sub, multiples))
        cons = cross_year_consistency(sub, multiples)
        for m in multiples:
            avg, n_neg, n_yrs = cons[m]
            row[f"yr_avg_{m}"] = avg
            row[f"yr_neg_{m}"] = f"{n_neg}/{n_yrs}"
        abs_rows.append(row)
    abs_df = pd.DataFrame(abs_rows)
    abs_df.to_csv(OUT_DIR / "cutoff_sensitivity_absolute.csv", index=False)
    print(abs_df[["cutoff", "N", "%", "d_0.618", "d_0.75", "d_1.0", "d_1.2"]].to_string(
        index=False, formatters={"%": lambda v: f"{v:.1f}%",
                                 "d_0.618": lambda v: f"{v:+.1f}",
                                 "d_0.75": lambda v: f"{v:+.1f}",
                                 "d_1.0": lambda v: f"{v:+.1f}",
                                 "d_1.2": lambda v: f"{v:+.1f}"}))
    print("\n  Cross-year (avg pp / n_neg / n_yrs) at each multiple:")
    cols = ["cutoff", "N"] + [f"yr_avg_{m}" for m in multiples] + [f"yr_neg_{m}" for m in multiples]
    print(abs_df[cols].to_string(index=False, formatters={
        f"yr_avg_{m}": (lambda v: f"{v:+.1f}") for m in multiples
    }))

    # ── B) percentile cutoffs ──
    print("\n" + "─" * 78)
    print("B) Percentile cutoffs:  norm >= p_X  → strong-GO bucket")
    print("─" * 78)
    pct_cutoffs = [60, 70, 75, 80, 85, 90]
    pct_rows = []
    for p in pct_cutoffs:
        v = float(np.percentile(df["night_norm"], p))
        sub = df[df["night_norm"] >= v]
        n = len(sub)
        row = {"pct": p, "cutoff_val": v, "N": n}
        row.update(diff_stats(sub, multiples))
        cons = cross_year_consistency(sub, multiples)
        for m in multiples:
            avg, n_neg, n_yrs = cons[m]
            row[f"yr_avg_{m}"] = avg
            row[f"yr_neg_{m}"] = f"{n_neg}/{n_yrs}"
        pct_rows.append(row)
    pct_df = pd.DataFrame(pct_rows)
    pct_df.to_csv(OUT_DIR / "cutoff_sensitivity_percentile.csv", index=False)
    print(pct_df[["pct", "cutoff_val", "N", "d_0.618", "d_0.75", "d_1.0", "d_1.2"]].to_string(
        index=False, formatters={"cutoff_val": lambda v: f"{v:.3f}",
                                 "d_0.618": lambda v: f"{v:+.1f}",
                                 "d_0.75": lambda v: f"{v:+.1f}",
                                 "d_1.0": lambda v: f"{v:+.1f}",
                                 "d_1.2": lambda v: f"{v:+.1f}"}))

    # ── C) Smooth scan plot ──
    cuts = np.arange(1.00, 1.60, 0.02)
    scan = []
    for c in cuts:
        sub = df[df["night_norm"] >= c]
        if len(sub) < 30:
            continue
        row = {"cutoff": c, "N": len(sub)}
        for m in multiples:
            u = (sub["up_ratio"] >= m).mean()
            l = (sub["dn_ratio"] >= m).mean()
            row[f"d_{m}"] = (u - l) * 100
        scan.append(row)
    scan_df = pd.DataFrame(scan)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("H092 — Strong-GO cutoff sensitivity (lower bias robustness)",
                 fontsize=12, fontweight="bold")

    ax = axes[0]
    for m in multiples:
        ax.plot(scan_df["cutoff"], scan_df[f"d_{m}"], "-o", label=f"m={m}", markersize=4)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.axhline(-10, color="grey", linewidth=0.4, linestyle="--", label="−10pp target")
    ax.axvline(1.30, color="orange", linewidth=0.6, linestyle=":", label="orig cutoff 1.30")
    ax.set_xlabel("night_norm ≥ cutoff")
    ax.set_ylabel("upper − lower (pp)")
    ax.set_title("Direction bias vs cutoff (pooled)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    ax = axes[1]
    ax.plot(scan_df["cutoff"], scan_df["N"], "-o", color="grey", markersize=4)
    ax.axvline(1.30, color="orange", linewidth=0.6, linestyle=":")
    ax.set_xlabel("night_norm ≥ cutoff")
    ax.set_ylabel("N (strong-GO sample size)")
    ax.set_title("Sample size vs cutoff")
    ax.grid(alpha=0.3)

    plt.tight_layout()
    out_png = OUT_DIR / "h092_cutoff_sensitivity.png"
    plt.savefig(out_png, dpi=150)
    print(f"\nPlot saved: {out_png}")

    # ── D) Distribution histogram for context ──
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.hist(df["night_norm"], bins=50, color="#42a5f5", alpha=0.7, edgecolor="white")
    for p, c in zip([50, 70, 80, 90], ["green", "orange", "red", "purple"]):
        v = np.percentile(df["night_norm"], p)
        ax.axvline(v, color=c, linewidth=1.2, linestyle="--", label=f"p{p}={v:.2f}")
    ax.axvline(1.30, color="black", linewidth=1.5, linestyle="-", label="orig cutoff 1.30")
    ax.set_xlabel("night_norm")
    ax.set_ylabel("count")
    ax.set_title("night_norm distribution (N=1264) — where does 1.30 sit?")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    out_png2 = OUT_DIR / "h092_night_norm_distribution.png"
    plt.savefig(out_png2, dpi=150)
    print(f"Plot saved: {out_png2}")


if __name__ == "__main__":
    main()
