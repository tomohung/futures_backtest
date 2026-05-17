#!/usr/bin/env python3
"""H092 Phase 2 — Reach definition comparison.

回應 user 質疑:之前的 reach 用 open-anchored, 跟 SatZone-style
running-anchored 結果差異大。一次跑 5 種定義對照:

    A.  open-anchored (static)
        target_upper = day_open + m × EmaHL  (整天固定)
        target_lower = day_open − m × EmaHL

    B.  running-anchored (live)
        target_upper(t) = running_low(t) + m × EmaHL
        target_lower(t) = running_high(t) − m × EmaHL

    C5, C10, C15. running-anchored with lag k minutes
        target_upper(t) = running_low(max(0, t-k)) + m × EmaHL
        target_lower(t) = running_high(max(0, t-k)) − m × EmaHL

對每個交易日的 08:45-10:45 (120 bars):
    - 計算各定義下「窗口內任一根 bar 是否觸及」boolean
    - 按 NVF tier 聚合機率

使用方式:
    uv run python research/active/H092-nvf-reach-direction/phase2_reach_definitions.py
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
    load_data as load_tier_data,
    TIER_LABELS, TIER_COLORS, DB_PATH, SYMBOL,
)

OUT_DIR = Path("research/active/H092-nvf-reach-direction/results")
MULTIPLES = [0.618, 0.75, 1.0, 1.2]
LAGS = [5, 10, 15]  # minutes
WINDOW_BARS = 120   # 08:45 - 10:44


def load_bars_window():
    """載入 08:45-10:44 每日 1m bars,回傳 dict[date] -> (highs, lows, opens) arrays."""
    print("Loading 1m bars for 08:45-10:44 window...")
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        bars = conn.execute(
            """
            SELECT timestamp, open, high, low, close
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '10:44:00'
            ORDER BY timestamp
            """,
            [SYMBOL],
        ).df()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"])
    bars["trade_date"] = bars["timestamp"].dt.normalize()
    bars_by_date = {d: g.reset_index(drop=True) for d, g in bars.groupby("trade_date", sort=False)}
    print(f"  Days loaded: {len(bars_by_date)}")
    return bars_by_date


def lagged_arr(arr, lag):
    """Shift arr forward by `lag`, fill first `lag` with arr[0]."""
    if lag == 0 or len(arr) == 0:
        return arr.copy()
    lagged = np.empty_like(arr)
    lagged[:lag] = arr[0]
    lagged[lag:] = arr[:len(arr) - lag]
    return lagged


def day_reach_metrics(highs, lows, day_open, ema_hl):
    """For one day, compute max upper/lower extension under each definition.

    Returns dict: { (def_label, dir) : reach_ratio }
    where dir in {"up", "dn"} and ratio = max_extension / ema_hl.
    """
    if len(highs) == 0 or ema_hl <= 0 or np.isnan(ema_hl):
        return None

    out = {}

    # ── A: open-anchored ──
    max_up_open = float(np.max(highs) - day_open)
    max_dn_open = float(day_open - np.min(lows))
    out[("A", "up")] = max_up_open / ema_hl
    out[("A", "dn")] = max_dn_open / ema_hl

    # ── B: running-anchored (live) ──
    running_min = np.minimum.accumulate(lows)
    running_max = np.maximum.accumulate(highs)
    ext_up_live = highs - running_min  # max upward extension from running low
    ext_dn_live = running_max - lows   # max downward extension from running high
    out[("B", "up")] = float(ext_up_live.max()) / ema_hl
    out[("B", "dn")] = float(ext_dn_live.max()) / ema_hl

    # ── C: running with lag ──
    for k in LAGS:
        lag_min = lagged_arr(running_min, k)
        lag_max = lagged_arr(running_max, k)
        ext_up_lag = highs - lag_min
        ext_dn_lag = lag_max - lows
        out[(f"C{k}", "up")] = float(ext_up_lag.max()) / ema_hl
        out[(f"C{k}", "dn")] = float(ext_dn_lag.max()) / ema_hl

    return out


def main():
    print("=" * 100)
    print("H092 Phase 2 — Reach definition comparison (A / B / C5 / C10 / C15)")
    print("=" * 100)

    tier_df = load_tier_data()[0]  # only need merged df
    print(f"\nTier data: {len(tier_df)} days")

    bars_by_date = load_bars_window()

    # Compute per-day reach metrics for all definitions
    print("\nComputing reach metrics per day...")
    rows = []
    skipped = 0
    for d in tier_df.index:
        day_bars = bars_by_date.get(d)
        if day_bars is None or len(day_bars) == 0:
            skipped += 1
            continue
        highs = day_bars["high"].values.astype(float)
        lows = day_bars["low"].values.astype(float)
        day_open = float(day_bars.iloc[0]["open"])
        ema_hl = float(tier_df.at[d, "ema_hl"])
        metrics = day_reach_metrics(highs, lows, day_open, ema_hl)
        if metrics is None:
            skipped += 1
            continue
        row = {"date": d, "tier": tier_df.at[d, "tier"],
               "year": tier_df.at[d, "year"], "ema_hl": ema_hl}
        for (defn, dir_), val in metrics.items():
            row[f"{defn}_{dir_}"] = val
        rows.append(row)
    print(f"  Days computed: {len(rows)}, skipped: {skipped}")

    df = pd.DataFrame(rows).set_index("date")

    DEFS = ["A", "B", "C5", "C10", "C15"]

    # ── Output 1: reach by tier and definition, upper side ──
    print("\n" + "─" * 100)
    print("Upper reach probability by tier × definition × multiple (08:45-10:45 window)")
    print("─" * 100)
    print(f"{'Tier':<12} {'Def':<5} {'N':>4} " + " ".join([f"  m={m:<5}" for m in MULTIPLES]))
    print("─" * 100)
    out_up_rows = []
    for tier in TIER_LABELS:
        sub = df[df["tier"] == tier]
        n = len(sub)
        for defn in DEFS:
            col = f"{defn}_up"
            vals = sub[col]
            probs = {m: (vals >= m).mean() for m in MULTIPLES}
            print(f"{tier:<12} {defn:<5} {n:>4} " +
                  " ".join([f"  {probs[m]*100:>5.1f}%" for m in MULTIPLES]))
            out_up_rows.append({
                "tier": tier, "def": defn, "N": n,
                **{f"p_{m}": probs[m] for m in MULTIPLES}
            })
        print()
    pd.DataFrame(out_up_rows).to_csv(OUT_DIR / "reach_defs_upper.csv", index=False)

    # ── Output 2: lower side ──
    print("\n" + "─" * 100)
    print("Lower reach probability by tier × definition × multiple")
    print("─" * 100)
    print(f"{'Tier':<12} {'Def':<5} {'N':>4} " + " ".join([f"  m={m:<5}" for m in MULTIPLES]))
    print("─" * 100)
    out_dn_rows = []
    for tier in TIER_LABELS:
        sub = df[df["tier"] == tier]
        n = len(sub)
        for defn in DEFS:
            col = f"{defn}_dn"
            vals = sub[col]
            probs = {m: (vals >= m).mean() for m in MULTIPLES}
            print(f"{tier:<12} {defn:<5} {n:>4} " +
                  " ".join([f"  {probs[m]*100:>5.1f}%" for m in MULTIPLES]))
            out_dn_rows.append({
                "tier": tier, "def": defn, "N": n,
                **{f"p_{m}": probs[m] for m in MULTIPLES}
            })
        print()
    pd.DataFrame(out_dn_rows).to_csv(OUT_DIR / "reach_defs_lower.csv", index=False)

    # ── Output 3: focus comparison — upper at m=0.618 across definitions ──
    print("\n" + "─" * 100)
    print("Quick view — Upper reach @ m=0.618 by tier × definition")
    print("─" * 100)
    print(f"{'Tier':<12} " + " ".join([f"  {d:<5}" for d in DEFS]))
    for tier in TIER_LABELS:
        sub = df[df["tier"] == tier]
        row_str = f"{tier:<12} "
        for defn in DEFS:
            p = (sub[f"{defn}_up"] >= 0.618).mean()
            row_str += f"  {p*100:>5.1f}%"
        print(row_str)

    print("\n" + "─" * 100)
    print("Quick view — Lower reach @ m=0.618 by tier × definition")
    print("─" * 100)
    print(f"{'Tier':<12} " + " ".join([f"  {d:<5}" for d in DEFS]))
    for tier in TIER_LABELS:
        sub = df[df["tier"] == tier]
        row_str = f"{tier:<12} "
        for defn in DEFS:
            p = (sub[f"{defn}_dn"] >= 0.618).mean()
            row_str += f"  {p*100:>5.1f}%"
        print(row_str)

    # ── Output 4: AND condition reach (B AND A) for variance reduction ──
    print("\n" + "─" * 100)
    print("AND condition: reach B (running) AND reach A (open-anchored) — selective exit signal")
    print("─" * 100)
    print(f"{'Tier':<12} {'Dir':<4} " + " ".join([f"  m={m:<5}" for m in MULTIPLES]))
    print("  (B only / A only / B AND A / B XOR A)")
    print("─" * 100)
    and_rows = []
    for tier in TIER_LABELS:
        sub = df[df["tier"] == tier]
        for dir_ in ["up", "dn"]:
            for m in MULTIPLES:
                B_reach = sub[f"B_{dir_}"] >= m
                A_reach = sub[f"A_{dir_}"] >= m
                p_B = B_reach.mean()
                p_A = A_reach.mean()
                p_both = (B_reach & A_reach).mean()
                p_only_B = (B_reach & ~A_reach).mean()
                and_rows.append({
                    "tier": tier, "dir": dir_, "m": m,
                    "B_only": p_B, "A_only": p_A,
                    "B_and_A": p_both, "B_not_A": p_only_B,
                })

    print(f"{'Tier':<12} {'Dir':<4} {'m':<6} {'P(B)':>7} {'P(A)':>7} {'P(B∩A)':>8} {'P(B−A)':>8}")
    for r in and_rows:
        print(f"{r['tier']:<12} {r['dir']:<4} {r['m']:<6} "
              f"{r['B_only']*100:>6.1f}% {r['A_only']*100:>6.1f}% "
              f"{r['B_and_A']*100:>7.1f}% {r['B_not_A']*100:>7.1f}%")
    pd.DataFrame(and_rows).to_csv(OUT_DIR / "reach_defs_and_condition.csv", index=False)

    df.to_csv(OUT_DIR / "reach_defs_raw.csv")

    # ── Plot ──
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle("H092 Phase 2 — Reach definitions A/B/C5/C10/C15 (08:45-10:45 window)",
                 fontsize=13, fontweight="bold")

    def_colors = {"A": "#1e88e5", "B": "#e53935", "C5": "#fb8c00", "C10": "#43a047", "C15": "#7e57c2"}

    # (a) Upper reach by tier — m=0.618, all definitions
    ax = axes[0, 0]
    x = np.arange(len(TIER_LABELS))
    w = 0.16
    for i, defn in enumerate(DEFS):
        vals = []
        for tier in TIER_LABELS:
            sub = df[df["tier"] == tier]
            vals.append((sub[f"{defn}_up"] >= 0.618).mean() * 100)
        ax.bar(x + (i - 2) * w, vals, w, color=def_colors[defn], label=defn)
    ax.set_xticks(x)
    ax.set_xticklabels(TIER_LABELS, fontsize=9)
    ax.set_ylabel("P(reach upper ≥ 0.618 × EmaHL in 2h) [%]")
    ax.set_title("(a) Upper reach @ m=0.618 — definition vs tier")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    # (b) Lower reach by tier — m=0.618
    ax = axes[0, 1]
    for i, defn in enumerate(DEFS):
        vals = []
        for tier in TIER_LABELS:
            sub = df[df["tier"] == tier]
            vals.append((sub[f"{defn}_dn"] >= 0.618).mean() * 100)
        ax.bar(x + (i - 2) * w, vals, w, color=def_colors[defn], label=defn)
    ax.set_xticks(x)
    ax.set_xticklabels(TIER_LABELS, fontsize=9)
    ax.set_ylabel("P(reach lower ≥ 0.618 × EmaHL in 2h) [%]")
    ax.set_title("(b) Lower reach @ m=0.618 — definition vs tier")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    # (c) Upper reach for strong-GO across multiples & definitions
    ax = axes[1, 0]
    sub = df[df["tier"] == "strong GO"]
    for defn in DEFS:
        ys = [(sub[f"{defn}_up"] >= m).mean() * 100 for m in MULTIPLES]
        ax.plot(MULTIPLES, ys, "-o", color=def_colors[defn], label=defn)
    ax.set_xlabel("reach multiple")
    ax.set_ylabel("P(reach upper) [%]")
    ax.set_title("(c) Strong-GO upper reach — definition curves")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # (d) Lower reach for strong-GO across multiples & definitions
    ax = axes[1, 1]
    for defn in DEFS:
        ys = [(sub[f"{defn}_dn"] >= m).mean() * 100 for m in MULTIPLES]
        ax.plot(MULTIPLES, ys, "-o", color=def_colors[defn], label=defn)
    ax.set_xlabel("reach multiple")
    ax.set_ylabel("P(reach lower) [%]")
    ax.set_title("(d) Strong-GO lower reach — definition curves")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    out_png = OUT_DIR / "h092_phase2_reach_defs.png"
    plt.savefig(out_png, dpi=140)
    print(f"\nPlot saved: {out_png}")


if __name__ == "__main__":
    main()
