#!/usr/bin/env python3
"""H092 Phase 2 補完 — 用新 4-tier (0.8 / 1.0 / 1.2) 重算 reach 表.

把原本的 reach rate (either / upper / lower / diff) 從舊 5-bucket
重新整理成 Phase 2 採用的 4-tier,確保口徑一致。

使用方式:
    uv run python research/active/H092-nvf-reach-direction/phase2_reach_4tier.py
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from phase2_market_structure import load_data, TIER_LABELS, TIER_COLORS, TIER_CUTS

OUT_DIR = Path("research/active/H092-nvf-reach-direction/results")

MULTIPLES = [0.618, 0.75, 1.0, 1.2]


def main():
    print("=" * 90)
    print(f"H092 Phase 2 補完 — reach rate by 4-tier (cuts: {TIER_CUTS})")
    print("=" * 90)

    merged, _, _ = load_data()
    merged["up_dist"] = merged["day_high"] - merged["day_open"]
    merged["dn_dist"] = merged["day_open"] - merged["day_low"]
    merged["up_ratio"] = merged["up_dist"] / merged["ema_hl"]
    merged["dn_ratio"] = merged["dn_dist"] / merged["ema_hl"]

    # ── A. Either reach ──
    print("\n" + "─" * 90)
    print("A. Reach (either side) — hl_ratio = day_hl / EmaHL")
    print("─" * 90)
    rows = []
    for t in TIER_LABELS:
        sub = merged[merged["tier"] == t]
        row = {"tier": t, "N": len(sub)}
        for m in MULTIPLES:
            row[f"either_{m}"] = (sub["hl_ratio"] >= m).mean()
        rows.append(row)
    a_df = pd.DataFrame(rows)
    print(a_df.to_string(index=False, formatters={
        c: (lambda v: f"{v:.1%}") for c in a_df.columns if c.startswith("either")
    }))
    a_df.to_csv(OUT_DIR / "phase2_reach_either_4tier.csv", index=False)

    # ── B. Direction (upper / lower / diff) ──
    print("\n" + "─" * 90)
    print("B. Reach upper / lower / diff (upper − lower, pp)")
    print("─" * 90)
    rows = []
    for t in TIER_LABELS:
        sub = merged[merged["tier"] == t]
        row = {"tier": t, "N": len(sub)}
        for m in MULTIPLES:
            u = (sub["up_ratio"] >= m).mean()
            l = (sub["dn_ratio"] >= m).mean()
            row[f"u_{m}"] = u
            row[f"l_{m}"] = l
            row[f"d_{m}"] = (u - l) * 100
        rows.append(row)
    d_df = pd.DataFrame(rows)
    # Direction-focused summary
    print("\n  Direction diff table (upper − lower, pp):")
    diff_cols = ["tier", "N", "d_0.618", "d_0.75", "d_1.0", "d_1.2"]
    print(d_df[diff_cols].to_string(index=False, formatters={
        c: (lambda v: f"{v:+.1f}pp") for c in diff_cols if c.startswith("d_")
    }))

    print("\n  Full upper / lower / diff:")
    print(d_df.to_string(index=False, formatters={
        **{f"u_{m}": (lambda v: f"{v:.1%}") for m in MULTIPLES},
        **{f"l_{m}": (lambda v: f"{v:.1%}") for m in MULTIPLES},
        **{f"d_{m}": (lambda v: f"{v:+.1f}pp") for m in MULTIPLES},
    }))
    d_df.to_csv(OUT_DIR / "phase2_reach_direction_4tier.csv", index=False)

    # ── C. Cross-year for strong-GO (≥1.2, the actionable bucket) ──
    print("\n" + "─" * 90)
    print("C. Strong-GO (≥1.2) cross-year reach (verification)")
    print("─" * 90)
    strong = merged[merged["tier"] == "strong GO"].copy()
    print(f"Total strong-GO days: {len(strong)}")
    rows = []
    for y in sorted(strong["year"].unique()):
        sub = strong[strong["year"] == y]
        if len(sub) < 10:
            continue
        row = {"year": int(y), "N": len(sub)}
        for m in MULTIPLES:
            row[f"either_{m}"] = (sub["hl_ratio"] >= m).mean()
            row[f"upper_{m}"] = (sub["up_ratio"] >= m).mean()
            row[f"lower_{m}"] = (sub["dn_ratio"] >= m).mean()
            row[f"diff_{m}"] = ((sub["up_ratio"] >= m).mean() - (sub["dn_ratio"] >= m).mean()) * 100
        rows.append(row)
    yr_df = pd.DataFrame(rows)
    cols = ["year", "N"] + [f"either_{m}" for m in MULTIPLES] + [f"diff_{m}" for m in MULTIPLES]
    print(yr_df[cols].to_string(index=False, formatters={
        **{f"either_{m}": (lambda v: f"{v:.1%}") for m in MULTIPLES},
        **{f"diff_{m}": (lambda v: f"{v:+.1f}") for m in MULTIPLES},
    }))
    yr_df.to_csv(OUT_DIR / "phase2_strong_go_yearly_4tier.csv", index=False)

    # ── D. Plot ──
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle(f"H092 Phase 2 — Reach by 4-tier (cuts {TIER_CUTS[0]} / {TIER_CUTS[1]} / {TIER_CUTS[2]})",
                 fontsize=13, fontweight="bold")

    # (a) either reach lines
    ax = axes[0, 0]
    for t in TIER_LABELS:
        sub = merged[merged["tier"] == t]
        ys = [(sub["hl_ratio"] >= m).mean() for m in MULTIPLES]
        ax.plot(MULTIPLES, ys, "-o", color=TIER_COLORS[t], label=f"{t} (N={len(sub)})")
    ax.set_xlabel("reach multiple (× EmaHL)")
    ax.set_ylabel("reach (either side)")
    ax.set_title("(a) Reach (either) by tier")
    ax.legend(fontsize=8, loc="lower left")
    ax.grid(alpha=0.3)
    ax.set_ylim(0, 1.02)

    # (b) Direction diff by tier × multiple
    ax = axes[0, 1]
    x = np.arange(len(MULTIPLES))
    w = 0.2
    for i, t in enumerate(TIER_LABELS):
        sub = merged[merged["tier"] == t]
        diffs = [((sub["up_ratio"] >= m).mean() - (sub["dn_ratio"] >= m).mean()) * 100 for m in MULTIPLES]
        ax.bar(x + (i - 1.5) * w, diffs, w, color=TIER_COLORS[t], label=t)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.axhline(10, color="grey", linewidth=0.4, linestyle="--")
    ax.axhline(-10, color="grey", linewidth=0.4, linestyle="--")
    ax.set_xticks(x)
    ax.set_xticklabels([str(m) for m in MULTIPLES])
    ax.set_xlabel("reach multiple")
    ax.set_ylabel("upper − lower (pp)")
    ax.set_title("(b) Direction bias (U−L) by tier")
    ax.legend(fontsize=8, loc="lower left")
    ax.grid(alpha=0.3, axis="y")

    # (c) Strong-GO yearly reach (either)
    ax = axes[1, 0]
    yrs = yr_df["year"].values
    for m in MULTIPLES:
        ax.plot(yrs, yr_df[f"either_{m}"], "-o", label=f"reach ≥ {m}")
    ax.set_xlabel("year")
    ax.set_ylabel("reach rate (either)")
    ax.set_title("(c) Strong-GO yearly reach rates")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    ax.set_ylim(0, 1.02)

    # (d) Strong-GO yearly direction diff
    ax = axes[1, 1]
    for m in MULTIPLES:
        ax.plot(yrs, yr_df[f"diff_{m}"], "-o", label=f"m={m}")
    ax.axhline(0, color="black", linewidth=0.7)
    ax.axhline(-10, color="grey", linewidth=0.4, linestyle="--", label="−10pp")
    ax.set_xlabel("year")
    ax.set_ylabel("upper − lower (pp)")
    ax.set_title("(d) Strong-GO yearly direction bias")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    out_png = OUT_DIR / "h092_phase2_reach_4tier.png"
    plt.savefig(out_png, dpi=140)
    print(f"\nPlot saved: {out_png}")


if __name__ == "__main__":
    main()
