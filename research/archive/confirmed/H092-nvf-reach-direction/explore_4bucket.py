#!/usr/bin/env python3
"""H092 Phase 1 追加 — 4-bucket NVF refinement + ≥1.30 cross-year verification.

回應 review:
- 2-bin STOP/GO 可能太粗(STOP 0.618 reach 仍 81%)
- 驗證 ≥1.30 bucket lower bias 是否跨年穩定

4 buckets:
    < 0.70       deep STOP
    0.70 - 1.00  mid STOP (跨 threshold 中位數附近)
    1.00 - 1.30  mid GO
    >= 1.30      strong GO

使用方式:
    uv run python research/active/H092-nvf-reach-direction/explore_4bucket.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent))
from explore import load_data

OUT_DIR = Path("research/active/H092-nvf-reach-direction/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    print("=" * 78)
    print("H092 Refinement — 4-bucket + ≥1.30 cross-year verification")
    print("=" * 78)

    df = load_data()
    print(f"Total days: {len(df)},  range: {df.index[0].date()} ~ {df.index[-1].date()}")

    multiples = [0.618, 0.75, 1.0, 1.2]

    # ── 4-bucket split ──
    labels = [
        "< 0.70 (deep STOP)",
        "0.70 - 1.00 (mid STOP)",
        "1.00 - 1.30 (mid GO)",
        "≥ 1.30 (strong GO)",
    ]
    masks = [
        df["night_norm"] < 0.70,
        (df["night_norm"] >= 0.70) & (df["night_norm"] < 1.00),
        (df["night_norm"] >= 1.00) & (df["night_norm"] < 1.30),
        df["night_norm"] >= 1.30,
    ]

    print("\n" + "─" * 78)
    print("Reach (either) by 4 buckets × 4 multiples")
    print("─" * 78)
    rows_e = []
    for label, mask in zip(labels, masks):
        sub = df[mask]
        row = {"bucket": label, "N": len(sub)}
        for m in multiples:
            row[f"either_{m}"] = (sub["hl_ratio"] >= m).mean()
        rows_e.append(row)
    e_df = pd.DataFrame(rows_e)
    print(e_df.to_string(index=False, formatters={c: (lambda v: f"{v:.1%}") for c in e_df.columns if c.startswith("either")}))

    print("\n" + "─" * 78)
    print("Direction bias by 4 buckets × 4 multiples  (upper − lower, pp)")
    print("─" * 78)
    rows_d = []
    for label, mask in zip(labels, masks):
        sub = df[mask]
        row = {"bucket": label, "N": len(sub)}
        for m in multiples:
            u = (sub["up_ratio"] >= m).mean()
            l = (sub["dn_ratio"] >= m).mean()
            row[f"u_{m}"] = u
            row[f"l_{m}"] = l
            row[f"diff_{m}"] = (u - l) * 100  # in pp
        rows_d.append(row)
    d_df = pd.DataFrame(rows_d)
    cols_show = ["bucket", "N", "diff_0.618", "diff_0.75", "diff_1.0", "diff_1.2"]
    print(d_df[cols_show].to_string(index=False, formatters={
        "diff_0.618": lambda v: f"{v:+.1f}pp",
        "diff_0.75": lambda v: f"{v:+.1f}pp",
        "diff_1.0": lambda v: f"{v:+.1f}pp",
        "diff_1.2": lambda v: f"{v:+.1f}pp",
    }))

    print("\n  Full upper / lower / diff:")
    print(d_df.to_string(index=False, formatters={
        c: (lambda v: f"{v:+.1f}pp") if c.startswith("diff") else (lambda v: f"{v:.1%}")
        for c in d_df.columns if c not in ("bucket", "N")
    }))

    e_df.to_csv(OUT_DIR / "reach_4bucket_either.csv", index=False)
    d_df.to_csv(OUT_DIR / "reach_4bucket_direction.csv", index=False)

    # ── ≥1.30 cross-year ──
    print("\n" + "─" * 78)
    print("Strong-GO (≥1.30) — cross-year direction verification")
    print("─" * 78)
    strong = df[df["night_norm"] >= 1.30].copy()
    print(f"Total strong-GO days: {len(strong)}")
    years = sorted(strong["year"].unique())
    rows_y = []
    for y in years:
        sub = strong[strong["year"] == y]
        if len(sub) < 10:
            print(f"  {y}: N={len(sub)} (skip, N<10)")
            continue
        row = {"year": int(y), "N": len(sub)}
        for m in multiples:
            u = (sub["up_ratio"] >= m).mean()
            l = (sub["dn_ratio"] >= m).mean()
            row[f"upper_{m}"] = u
            row[f"lower_{m}"] = l
            row[f"diff_{m}"] = (u - l) * 100
        rows_y.append(row)
    sy = pd.DataFrame(rows_y)
    print(sy.to_string(index=False, formatters={
        c: (lambda v: f"{v:+.1f}pp") if c.startswith("diff") else (lambda v: f"{v:.1%}")
        for c in sy.columns if c not in ("year", "N")
    }))

    print("\n  Consistency check (yr_neg means lower > upper that year):")
    for m in multiples:
        diffs = sy[f"diff_{m}"]
        n_pos = int((diffs > 0).sum())
        n_neg = int((diffs < 0).sum())
        n_zero = len(diffs) - n_pos - n_neg
        avg = diffs.mean()
        # Magnitude classification
        consistent = (n_neg >= 4) if avg < 0 else (n_pos >= 4)
        target_10 = abs(avg) >= 10
        target_5 = abs(avg) >= 5
        print(f"  m={m}: avg={avg:+.1f}pp, pos/neg/zero={n_pos}/{n_neg}/{n_zero}, "
              f"≥4 consistent: {consistent}, |avg|≥5pp: {target_5}, |avg|≥10pp: {target_10}")

    sy.to_csv(OUT_DIR / "strong_go_yearly.csv", index=False)

    # ── Plot ──
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle("H092 Refinement — 4-bucket reach + strong-GO cross-year",
                 fontsize=13, fontweight="bold")

    # (a) either reach by 4 buckets
    ax = axes[0, 0]
    colors = plt.cm.coolwarm(np.linspace(0, 1, len(labels)))
    for label, mask, c in zip(labels, masks, colors):
        sub = df[mask]
        ys = [(sub["hl_ratio"] >= m).mean() for m in multiples]
        ax.plot(multiples, ys, "-o", label=f"{label} (N={len(sub)})", color=c)
    ax.set_xlabel("reach multiple (× EmaHL)")
    ax.set_ylabel("reach rate (either side)")
    ax.set_title("(a) Reach (either) by 4 buckets")
    ax.legend(fontsize=8, loc="lower left")
    ax.grid(alpha=0.3)
    ax.set_ylim(0, 1.05)

    # (b) Direction diff (upper - lower) by 4 buckets across multiples
    ax = axes[0, 1]
    x = np.arange(len(multiples))
    w = 0.18
    for i, (label, mask, c) in enumerate(zip(labels, masks, colors)):
        sub = df[mask]
        diffs = [((sub["up_ratio"] >= m).mean() - (sub["dn_ratio"] >= m).mean()) * 100 for m in multiples]
        ax.bar(x + (i - 1.5) * w, diffs, w, label=label, color=c)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.axhline(10, color="grey", linewidth=0.4, linestyle="--")
    ax.axhline(-10, color="grey", linewidth=0.4, linestyle="--")
    ax.set_xticks(x)
    ax.set_xticklabels([str(m) for m in multiples])
    ax.set_xlabel("reach multiple")
    ax.set_ylabel("upper − lower (pp)")
    ax.set_title("(b) Direction bias (U−L) by 4 buckets")
    ax.legend(fontsize=7, loc="lower left")
    ax.grid(alpha=0.3, axis="y")

    # (c) Strong-GO yearly upper / lower at 1.0
    ax = axes[1, 0]
    yrs = sy["year"].astype(int).values
    xp = np.arange(len(yrs))
    w = 0.35
    ax.bar(xp - w/2, sy["upper_1.0"], w, label="upper ≥ 1.0×", color="#fb8c00")
    ax.bar(xp + w/2, sy["lower_1.0"], w, label="lower ≥ 1.0×", color="#1e88e5")
    ax.set_xticks(xp)
    ax.set_xticklabels([f"{y}\n(N={int(n)})" for y, n in zip(yrs, sy["N"])])
    ax.set_ylabel("reach rate")
    ax.set_title("(c) Strong-GO (≥1.30) — reach ≥ 1.0× upper vs lower by year")
    ax.legend()
    ax.grid(alpha=0.3, axis="y")

    # (d) Strong-GO yearly diff across multiples
    ax = axes[1, 1]
    for m in multiples:
        ax.plot(sy["year"], sy[f"diff_{m}"], "-o", label=f"m={m}")
    ax.axhline(0, color="black", linewidth=0.7)
    ax.axhline(-10, color="grey", linewidth=0.4, linestyle="--", label="−10pp")
    ax.set_xlabel("year")
    ax.set_ylabel("upper − lower (pp)")
    ax.set_title("(d) Strong-GO yearly direction bias")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    out_png = OUT_DIR / "h092_4bucket_refinement.png"
    plt.savefig(out_png, dpi=150)
    print(f"\nPlot saved: {out_png}")


if __name__ == "__main__":
    main()
