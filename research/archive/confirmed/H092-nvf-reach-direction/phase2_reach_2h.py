#!/usr/bin/env python3
"""H092 Phase 2 補完 — 開盤 2 小時(08:45-10:45)內的 reach 機率分布.

回應實務需求:
    - 前 2h 波動最大,出場決策常落在此區間
    - Full-day reach 數字對「2h 內已出場」的部位不完全適用

分析:
    A. 2h upper / lower reach by tier × 4 multiples
    B. 2h vs full-day reach 對比(capture rate)
    C. 2h 內 high/low 形成比例(每個 tier 多少天 extremes 在 2h 內鎖定)

使用方式:
    uv run python research/active/H092-nvf-reach-direction/phase2_reach_2h.py
"""

import bisect
import sys
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from phase2_market_structure import (
    load_data, TIER_LABELS, TIER_COLORS, TIER_CUTS, DB_PATH, SYMBOL,
)

OUT_DIR = Path("research/active/H092-nvf-reach-direction/results")
MULTIPLES = [0.618, 0.75, 1.0, 1.2]
WINDOW_END_MINUTE = 120  # 10:45 = 08:45 + 120 min


def load_2h_aggregates(day_dates):
    """從 1m bars 取 08:45-10:45 區間每日的 2h_high / 2h_low / first_2h_open."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute(
            """
            SELECT timestamp::DATE AS td,
                   arg_min(open, timestamp) AS open_2h,
                   MAX(high) AS high_2h,
                   MIN(low)  AS low_2h
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '10:44:00'
            GROUP BY td
            ORDER BY td
            """,
            [SYMBOL],
        ).df()
    df["td"] = pd.to_datetime(df["td"])
    df = df.set_index("td")
    return df.reindex(day_dates)


def main():
    print("=" * 90)
    print(f"H092 Phase 2 — 2h window reach analysis (08:45-10:45, 120 min)")
    print("=" * 90)

    print("\nLoading full-day data (reuse phase2_market_structure)...")
    merged, _, _ = load_data()
    print(f"  Days: {len(merged)}")

    print("Loading 2h-window aggregates...")
    h2 = load_2h_aggregates(merged.index)
    merged = merged.join(h2[["open_2h", "high_2h", "low_2h"]], how="left")

    # 2h reach distances (using day_open as anchor for consistency with full-day analysis)
    merged["up_2h"] = merged["high_2h"] - merged["day_open"]
    merged["dn_2h"] = merged["day_open"] - merged["low_2h"]
    merged["up_2h_ratio"] = merged["up_2h"] / merged["ema_hl"]
    merged["dn_2h_ratio"] = merged["dn_2h"] / merged["ema_hl"]

    # Full-day equivalents
    merged["up_full"] = merged["day_high"] - merged["day_open"]
    merged["dn_full"] = merged["day_open"] - merged["day_low"]
    merged["up_full_ratio"] = merged["up_full"] / merged["ema_hl"]
    merged["dn_full_ratio"] = merged["dn_full"] / merged["ema_hl"]

    # ── A. 2h upper/lower reach by tier ──
    print("\n" + "─" * 90)
    print("A. 2h-window upper / lower reach by tier")
    print("─" * 90)
    rows = []
    for t in TIER_LABELS:
        sub = merged[merged["tier"] == t]
        row = {"tier": t, "N": len(sub)}
        for m in MULTIPLES:
            row[f"u_{m}"] = (sub["up_2h_ratio"] >= m).mean()
            row[f"l_{m}"] = (sub["dn_2h_ratio"] >= m).mean()
            row[f"d_{m}"] = (row[f"u_{m}"] - row[f"l_{m}"]) * 100
        rows.append(row)
    a_df = pd.DataFrame(rows)

    print("\n  Upper reach (2h window):")
    cols_u = ["tier", "N"] + [f"u_{m}" for m in MULTIPLES]
    print(a_df[cols_u].to_string(index=False, formatters={
        f"u_{m}": (lambda v: f"{v:.1%}") for m in MULTIPLES
    }))
    print("\n  Lower reach (2h window):")
    cols_l = ["tier", "N"] + [f"l_{m}" for m in MULTIPLES]
    print(a_df[cols_l].to_string(index=False, formatters={
        f"l_{m}": (lambda v: f"{v:.1%}") for m in MULTIPLES
    }))
    print("\n  Direction diff (upper − lower, pp):")
    cols_d = ["tier", "N"] + [f"d_{m}" for m in MULTIPLES]
    print(a_df[cols_d].to_string(index=False, formatters={
        f"d_{m}": (lambda v: f"{v:+.1f}pp") for m in MULTIPLES
    }))
    a_df.to_csv(OUT_DIR / "phase2_reach_2h_by_tier.csv", index=False)

    # ── B. 2h vs full-day reach (capture rate) ──
    print("\n" + "─" * 90)
    print("B. 2h reach vs full-day reach — capture rate = P(reach in 2h) / P(reach full day)")
    print("─" * 90)
    print("  Upper side:")
    rows_b_u = []
    for t in TIER_LABELS:
        sub = merged[merged["tier"] == t]
        row = {"tier": t, "N": len(sub)}
        for m in MULTIPLES:
            p_2h = (sub["up_2h_ratio"] >= m).mean()
            p_full = (sub["up_full_ratio"] >= m).mean()
            row[f"u_2h_{m}"] = p_2h
            row[f"u_full_{m}"] = p_full
            row[f"u_cap_{m}"] = p_2h / p_full if p_full > 0 else np.nan
        rows_b_u.append(row)
    b_u_df = pd.DataFrame(rows_b_u)
    cols_show = ["tier", "N"] + [c for c in b_u_df.columns if c.startswith("u_cap_")]
    print(b_u_df[cols_show].to_string(index=False, formatters={
        f"u_cap_{m}": (lambda v: f"{v:.1%}") for m in MULTIPLES
    }))

    print("\n  Lower side:")
    rows_b_l = []
    for t in TIER_LABELS:
        sub = merged[merged["tier"] == t]
        row = {"tier": t, "N": len(sub)}
        for m in MULTIPLES:
            p_2h = (sub["dn_2h_ratio"] >= m).mean()
            p_full = (sub["dn_full_ratio"] >= m).mean()
            row[f"l_2h_{m}"] = p_2h
            row[f"l_full_{m}"] = p_full
            row[f"l_cap_{m}"] = p_2h / p_full if p_full > 0 else np.nan
        rows_b_l.append(row)
    b_l_df = pd.DataFrame(rows_b_l)
    cols_show = ["tier", "N"] + [c for c in b_l_df.columns if c.startswith("l_cap_")]
    print(b_l_df[cols_show].to_string(index=False, formatters={
        f"l_cap_{m}": (lambda v: f"{v:.1%}") for m in MULTIPLES
    }))

    b_u_df.to_csv(OUT_DIR / "phase2_reach_2h_capture_upper.csv", index=False)
    b_l_df.to_csv(OUT_DIR / "phase2_reach_2h_capture_lower.csv", index=False)

    # ── C. % of high/low formed in 2h ──
    print("\n" + "─" * 90)
    print("C. % of day-high / day-low formed within first 2h (minute_idx < 120)")
    print("─" * 90)
    rows = []
    for t in TIER_LABELS:
        sub = merged[merged["tier"] == t]
        h_in_2h = (sub["high_minute"] < 120).mean()
        l_in_2h = (sub["low_minute"] < 120).mean()
        rows.append({
            "tier": t, "N": len(sub),
            "pct_high_in_2h": h_in_2h * 100,
            "pct_low_in_2h": l_in_2h * 100,
        })
    c_df = pd.DataFrame(rows)
    print(c_df.to_string(index=False, formatters={
        "pct_high_in_2h": lambda v: f"{v:.1f}%",
        "pct_low_in_2h": lambda v: f"{v:.1f}%",
    }))
    c_df.to_csv(OUT_DIR / "phase2_extremes_in_2h.csv", index=False)

    # ── D. Cross-year STOP/GO direction stability (2h window) ──
    print("\n" + "─" * 90)
    print("D. Strong-GO 2h direction stability across years")
    print("─" * 90)
    strong = merged[merged["tier"] == "strong GO"].copy()
    rows = []
    for y in sorted(strong["year"].unique()):
        sub = strong[strong["year"] == y]
        if len(sub) < 10:
            continue
        row = {"year": int(y), "N": len(sub)}
        for m in MULTIPLES:
            u = (sub["up_2h_ratio"] >= m).mean()
            l = (sub["dn_2h_ratio"] >= m).mean()
            row[f"u_{m}"] = u
            row[f"l_{m}"] = l
            row[f"d_{m}"] = (u - l) * 100
        rows.append(row)
    sg_yr_df = pd.DataFrame(rows)
    cols = ["year", "N"] + [f"d_{m}" for m in MULTIPLES]
    print(sg_yr_df[cols].to_string(index=False, formatters={
        f"d_{m}": (lambda v: f"{v:+.1f}pp") for m in MULTIPLES
    }))
    sg_yr_df.to_csv(OUT_DIR / "phase2_strong_go_yearly_2h.csv", index=False)

    # ── Plot ──
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle("H092 Phase 2 — 2h-window reach (08:45-10:45)",
                 fontsize=13, fontweight="bold")

    # (a) Upper reach 2h by tier
    ax = axes[0, 0]
    x = np.arange(len(MULTIPLES))
    w = 0.2
    for i, t in enumerate(TIER_LABELS):
        sub = merged[merged["tier"] == t]
        vals = [(sub["up_2h_ratio"] >= m).mean() for m in MULTIPLES]
        ax.bar(x + (i - 1.5) * w, vals, w, color=TIER_COLORS[t], label=t)
    ax.set_xticks(x)
    ax.set_xticklabels([str(m) for m in MULTIPLES])
    ax.set_xlabel("reach multiple")
    ax.set_ylabel("P(upper reach in 2h)")
    ax.set_title("(a) Upper reach within 2h by tier")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    # (b) Lower reach 2h by tier
    ax = axes[0, 1]
    for i, t in enumerate(TIER_LABELS):
        sub = merged[merged["tier"] == t]
        vals = [(sub["dn_2h_ratio"] >= m).mean() for m in MULTIPLES]
        ax.bar(x + (i - 1.5) * w, vals, w, color=TIER_COLORS[t], label=t)
    ax.set_xticks(x)
    ax.set_xticklabels([str(m) for m in MULTIPLES])
    ax.set_xlabel("reach multiple")
    ax.set_ylabel("P(lower reach in 2h)")
    ax.set_title("(b) Lower reach within 2h by tier")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    # (c) Direction diff 2h by tier
    ax = axes[1, 0]
    for i, t in enumerate(TIER_LABELS):
        sub = merged[merged["tier"] == t]
        diffs = [((sub["up_2h_ratio"] >= m).mean() - (sub["dn_2h_ratio"] >= m).mean()) * 100 for m in MULTIPLES]
        ax.bar(x + (i - 1.5) * w, diffs, w, color=TIER_COLORS[t], label=t)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels([str(m) for m in MULTIPLES])
    ax.set_xlabel("reach multiple")
    ax.set_ylabel("upper − lower (pp, 2h window)")
    ax.set_title("(c) 2h direction bias (U−L)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    # (d) Capture rate: 2h / full-day for upper side
    ax = axes[1, 1]
    for i, t in enumerate(TIER_LABELS):
        sub = merged[merged["tier"] == t]
        ys = []
        for m in MULTIPLES:
            p_2h = (sub["up_2h_ratio"] >= m).mean()
            p_full = (sub["up_full_ratio"] >= m).mean()
            ys.append(p_2h / p_full if p_full > 0 else np.nan)
        ax.bar(x + (i - 1.5) * w, ys, w, color=TIER_COLORS[t], label=t)
    ax.set_xticks(x)
    ax.set_xticklabels([str(m) for m in MULTIPLES])
    ax.set_xlabel("reach multiple")
    ax.set_ylabel("capture rate (2h / full-day, upper)")
    ax.set_title("(d) 2h capture rate vs full-day, upper side")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")
    ax.set_ylim(0, 1.05)

    plt.tight_layout()
    out_png = OUT_DIR / "h092_phase2_reach_2h.png"
    plt.savefig(out_png, dpi=140)
    print(f"\nPlot saved: {out_png}")


if __name__ == "__main__":
    main()
