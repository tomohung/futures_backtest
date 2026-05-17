#!/usr/bin/env python3
"""H092 Phase 1 — NVF Reach Multiples & Direction Asymmetry.

驗證：
1. 0.75× reach 是否為 H070 結果的有資訊量補完（H1）
2. STOP 天 reach_upper vs reach_lower 是否方向不對稱（H2）

NVF 方法：EMA20 + expanding median（post-H075，與 production
src/analysis/key_prices.py:_compute_night_vol_filter 一致）。

使用方式：
    uv run python research/active/H092-nvf-reach-direction/explore.py
"""

import bisect
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H092-nvf-reach-direction/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMBOL = "TX"
NVF_MIN_HISTORY_NIGHTS = 60
NVF_FALLBACK_THRESHOLD = 0.93

plt.rcParams["font.size"] = 10
plt.rcParams["figure.figsize"] = (16, 10)


def load_data():
    """載入 day session HL、EstRange(EmaHL)、night_norm 與 expanding median threshold。"""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        day = conn.execute(
            """
            SELECT timestamp::DATE AS td,
                   arg_min(open, timestamp) AS day_open,
                   MAX(high) AS day_high,
                   MIN(low) AS day_low,
                   MAX(high) - MIN(low) AS day_hl
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            GROUP BY td
            ORDER BY td
            """,
            [SYMBOL],
        ).df()
        day["td"] = pd.to_datetime(day["td"])
        day = day.set_index("td").sort_index()

        night_raw = conn.execute(
            """
            SELECT timestamp, high, low
            FROM ohlcv_1m
            WHERE symbol = ?
              AND (timestamp::TIME >= '15:00:00' OR timestamp::TIME < '05:00:00')
            ORDER BY timestamp
            """,
            [SYMBOL],
        ).df()
    night_raw["timestamp"] = pd.to_datetime(night_raw["timestamp"])

    day_dates_list = sorted(day.index.tolist())

    def find_next_trade_date(ts):
        cal_time = ts.time()
        if cal_time >= pd.Timestamp("15:00").time():
            search_date = (ts + pd.Timedelta(days=1)).normalize()
        else:
            search_date = ts.normalize()
        idx = bisect.bisect_left(day_dates_list, search_date)
        return day_dates_list[idx] if idx < len(day_dates_list) else None

    night_raw["trade_date"] = night_raw["timestamp"].apply(find_next_trade_date)
    night_raw = night_raw.dropna(subset=["trade_date"])
    night = night_raw.groupby("trade_date").agg(
        night_high=("high", "max"),
        night_low=("low", "min"),
        n_bars=("high", "count"),
    )
    night["night_range"] = night["night_high"] - night["night_low"]
    night = night[night["n_bars"] >= 100].copy()
    night = night.sort_index()

    # EMA20 of night_range (production method post-H075)
    night["ema20"] = night["night_range"].ewm(span=20, adjust=False).mean()
    night["night_norm"] = night["night_range"] / night["ema20"]

    # Causal expanding median threshold: threshold_t = median(norms[0..t-1])
    norms = night["night_norm"].values
    thresholds = np.empty(len(norms))
    for i in range(len(norms)):
        history = norms[:i]
        history = history[~np.isnan(history)]
        if len(history) >= NVF_MIN_HISTORY_NIGHTS:
            thresholds[i] = float(np.median(history))
        else:
            thresholds[i] = NVF_FALLBACK_THRESHOLD
    night["threshold"] = thresholds
    night["nvf_pass"] = night["night_norm"] >= night["threshold"]
    night["nvf_stop"] = night["night_norm"] < night["threshold"]

    # EmaHL: EMA20 of day_hl, shift 1 (causal — matches estimate_hl_exit.py)
    day["ema_hl"] = day["day_hl"].ewm(span=20, adjust=False).mean().shift(1)

    merged = day.join(
        night[["night_range", "night_norm", "threshold", "nvf_pass", "nvf_stop"]],
        how="inner",
    )
    merged = merged.dropna(subset=["ema_hl", "night_norm"])

    merged["up_dist"] = merged["day_high"] - merged["day_open"]
    merged["dn_dist"] = merged["day_open"] - merged["day_low"]
    merged["hl_ratio"] = merged["day_hl"] / merged["ema_hl"]
    merged["up_ratio"] = merged["up_dist"] / merged["ema_hl"]
    merged["dn_ratio"] = merged["dn_dist"] / merged["ema_hl"]

    merged["year"] = merged.index.year
    merged["weekday"] = merged.index.dayofweek
    return merged


def reach_table(df, bucket_labels, bucket_masks, multiples):
    rows = []
    for label, mask in zip(bucket_labels, bucket_masks):
        sub = df[mask]
        n = len(sub)
        row = {
            "bucket": label,
            "N": n,
            "mean_hl": sub["hl_ratio"].mean(),
            "mean_up": sub["up_ratio"].mean(),
            "mean_dn": sub["dn_ratio"].mean(),
        }
        for m in multiples:
            row[f"either_{m}"] = (sub["hl_ratio"] >= m).mean()
            row[f"upper_{m}"] = (sub["up_ratio"] >= m).mean()
            row[f"lower_{m}"] = (sub["dn_ratio"] >= m).mean()
            row[f"diff_{m}"] = row[f"upper_{m}"] - row[f"lower_{m}"]
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    print("=" * 78)
    print("H092: NVF Reach Multiples & Direction Asymmetry")
    print("=" * 78)

    df = load_data()
    print(f"Total days: {len(df)}")
    print(f"Date range: {df.index[0].date()} ~ {df.index[-1].date()}")
    print(f"NVF threshold (latest): {df['threshold'].iloc[-1]:.4f}")
    print(f"STOP days: {int(df['nvf_stop'].sum())}, GO days: {int(df['nvf_pass'].sum())}")

    sanity = (df["up_dist"] + df["dn_dist"] >= df["day_hl"] - 1e-6).all()
    print(f"Sanity (up_dist + dn_dist >= day_hl): {sanity}")

    multiples = [0.618, 0.75, 1.0, 1.2]

    # ── Analysis A: 5-bucket absolute NVF (H070 comparison) ──
    print("\n" + "─" * 78)
    print("Analysis A — Reach rate by absolute NVF bucket × multiple × direction")
    print("─" * 78)
    abs_labels = [
        "norm < 0.70",
        "0.70 ≤ norm < 0.85",
        "0.85 ≤ norm < 1.00",
        "1.00 ≤ norm < 1.30",
        "norm ≥ 1.30",
    ]
    abs_masks = [
        df["night_norm"] < 0.70,
        (df["night_norm"] >= 0.70) & (df["night_norm"] < 0.85),
        (df["night_norm"] >= 0.85) & (df["night_norm"] < 1.00),
        (df["night_norm"] >= 1.00) & (df["night_norm"] < 1.30),
        df["night_norm"] >= 1.30,
    ]
    tab_abs = reach_table(df, abs_labels, abs_masks, multiples)
    tab_abs.to_csv(OUT_DIR / "reach_by_absolute_bucket.csv", index=False)

    fmt = lambda v: f"{v:.3f}" if isinstance(v, float) else str(v)
    print(tab_abs.to_string(index=False, formatters={c: fmt for c in tab_abs.columns if c not in ("bucket", "N")}))

    # ── Analysis B: dynamic STOP/GO ──
    print("\n" + "─" * 78)
    print("Analysis B — Reach rate by dynamic STOP/GO (post-H075 EMA20 + expanding median)")
    print("─" * 78)
    dyn_labels = ["STOP (norm < threshold)", "GO (norm ≥ threshold)"]
    dyn_masks = [df["nvf_stop"], df["nvf_pass"]]
    tab_dyn = reach_table(df, dyn_labels, dyn_masks, multiples)
    tab_dyn.to_csv(OUT_DIR / "reach_by_dynamic_bucket.csv", index=False)
    print(tab_dyn.to_string(index=False, formatters={c: fmt for c in tab_dyn.columns if c not in ("bucket", "N")}))

    # ── Cross-year STOP day direction ──
    print("\n" + "─" * 78)
    print("Cross-year STOP day: upper vs lower at each multiple")
    print("─" * 78)
    years = sorted(df["year"].unique())
    yearly_rows = []
    for y in years:
        sub = df[(df["year"] == y) & df["nvf_stop"]]
        if len(sub) < 10:
            continue
        row = {"year": int(y), "N_stop": len(sub)}
        for m in multiples:
            row[f"upper_{m}"] = (sub["up_ratio"] >= m).mean()
            row[f"lower_{m}"] = (sub["dn_ratio"] >= m).mean()
            row[f"diff_{m}"] = row[f"upper_{m}"] - row[f"lower_{m}"]
        yearly_rows.append(row)
    yearly_df = pd.DataFrame(yearly_rows)
    yearly_df.to_csv(OUT_DIR / "stop_yearly_direction.csv", index=False)
    print(yearly_df.to_string(index=False, formatters={c: fmt for c in yearly_df.columns if c not in ("year", "N_stop")}))

    print("\n" + "─" * 78)
    print("STOP direction bias summary (across years)")
    print("─" * 78)
    summary_rows = []
    for m in multiples:
        diffs = yearly_df[f"diff_{m}"]
        n_pos = int((diffs > 0).sum())
        n_neg = int((diffs < 0).sum())
        n_zero = len(diffs) - n_pos - n_neg
        avg_diff = float(diffs.mean())
        max_abs = float(diffs.abs().max())
        # Consistency: dominant direction reached in ≥ 4 years
        if avg_diff >= 0:
            consistent = n_pos >= 4
        else:
            consistent = n_neg >= 4
        # Also compute pooled STOP diff
        stop_sub = df[df["nvf_stop"]]
        pooled_up = (stop_sub["up_ratio"] >= m).mean()
        pooled_dn = (stop_sub["dn_ratio"] >= m).mean()
        pooled_diff = pooled_up - pooled_dn
        summary_rows.append({
            "multiple": m,
            "pooled_upper": pooled_up,
            "pooled_lower": pooled_dn,
            "pooled_diff": pooled_diff,
            "yr_avg_diff": avg_diff,
            "yr_max_abs": max_abs,
            "yr_pos": n_pos,
            "yr_neg": n_neg,
            "yr_zero": n_zero,
            "consistent_dir_>=4": consistent,
            "pooled_diff_abs_>=10pp": abs(pooled_diff) >= 0.10,
        })
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(OUT_DIR / "stop_direction_summary.csv", index=False)
    print(summary_df.to_string(index=False, formatters={c: fmt for c in summary_df.columns if c not in ("multiple", "yr_pos", "yr_neg", "yr_zero", "consistent_dir_>=4", "pooled_diff_abs_>=10pp")}))

    # ── 0.75 informational test (H1) ──
    print("\n" + "─" * 78)
    print("H1 — 0.75 vs neighbouring multiples (STOP day, distance ≥ 5pp ?)")
    print("─" * 78)
    stop_sub = df[df["nvf_stop"]]
    e618 = (stop_sub["hl_ratio"] >= 0.618).mean()
    e75 = (stop_sub["hl_ratio"] >= 0.75).mean()
    e100 = (stop_sub["hl_ratio"] >= 1.0).mean()
    print(f"  STOP either reach: 0.618={e618:.1%}, 0.75={e75:.1%}, 1.0={e100:.1%}")
    print(f"  |0.75 - 0.618| = {abs(e75-e618):.1%}  (target ≥ 5pp)")
    print(f"  |0.75 - 1.0|   = {abs(e75-e100):.1%}  (target ≥ 5pp)")

    # ── Plot ──
    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    fig.suptitle("H092 — NVF Reach Multiples & Direction Asymmetry", fontsize=14, fontweight="bold")

    # (a) Reach (either) by absolute bucket — line plot across multiples
    ax = axes[0, 0]
    colors_a = plt.cm.coolwarm(np.linspace(0, 1, len(abs_labels)))
    for label, mask, c in zip(abs_labels, abs_masks, colors_a):
        sub = df[mask]
        ys = [(sub["hl_ratio"] >= m).mean() for m in multiples]
        ax.plot(multiples, ys, "-o", label=f"{label} (N={len(sub)})", color=c)
    ax.set_xlabel("reach multiple (× EmaHL)")
    ax.set_ylabel("reach rate (either side)")
    ax.set_title("(a) Reach (either) by absolute NVF bucket")
    ax.legend(fontsize=8, loc="lower left")
    ax.grid(alpha=0.3)
    ax.set_ylim(0, 1)

    # (b) STOP vs GO — upper vs lower bars
    ax = axes[0, 1]
    stop_df_ = df[df["nvf_stop"]]
    go_df_ = df[df["nvf_pass"]]
    x = np.arange(len(multiples))
    w = 0.2
    ax.bar(x - 1.5 * w, [(stop_df_["up_ratio"] >= m).mean() for m in multiples], w, label=f"STOP upper (N={len(stop_df_)})", color="#fb8c00")
    ax.bar(x - 0.5 * w, [(stop_df_["dn_ratio"] >= m).mean() for m in multiples], w, label="STOP lower", color="#e53935")
    ax.bar(x + 0.5 * w, [(go_df_["up_ratio"] >= m).mean() for m in multiples], w, label=f"GO upper (N={len(go_df_)})", color="#43a047")
    ax.bar(x + 1.5 * w, [(go_df_["dn_ratio"] >= m).mean() for m in multiples], w, label="GO lower", color="#1e88e5")
    ax.set_xticks(x)
    ax.set_xticklabels([str(m) for m in multiples])
    ax.set_xlabel("reach multiple")
    ax.set_ylabel("reach rate (directional)")
    ax.set_title("(b) Upper vs Lower reach: STOP vs GO")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")

    # (c) STOP-day yearly upper / lower at all multiples
    ax = axes[1, 0]
    yrs = yearly_df["year"].astype(int).values
    n_yr = len(yrs)
    x = np.arange(n_yr)
    w = 0.18
    for i, m in enumerate(multiples):
        offset = (i - 1.5) * w
        ax.bar(x + offset - w / 2, yearly_df[f"upper_{m}"], w / 2, label=f"upper {m}" if i == 0 else None, color="#fb8c00", alpha=0.4 + 0.2 * i)
        ax.bar(x + offset + w / 2, yearly_df[f"lower_{m}"], w / 2, label=f"lower {m}" if i == 0 else None, color="#1e88e5", alpha=0.4 + 0.2 * i)
    ax.set_xticks(x)
    ax.set_xticklabels(yrs)
    ax.set_xlabel("year")
    ax.set_ylabel("STOP reach rate")
    ax.set_title("(c) STOP-day reach by year — upper(orange) vs lower(blue), 4 multiples")
    ax.grid(alpha=0.3, axis="y")

    # (d) STOP diff (upper - lower) per year, all multiples
    ax = axes[1, 1]
    for m in multiples:
        ax.plot(yearly_df["year"], yearly_df[f"diff_{m}"], "-o", label=f"m={m}")
    ax.axhline(0, color="black", linewidth=0.7)
    ax.axhline(0.10, color="grey", linewidth=0.5, linestyle="--", label="±10pp")
    ax.axhline(-0.10, color="grey", linewidth=0.5, linestyle="--")
    ax.set_xlabel("year")
    ax.set_ylabel("upper − lower reach rate (STOP days)")
    ax.set_title("(d) STOP direction asymmetry by year")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    out_png = OUT_DIR / "h092_reach_direction.png"
    plt.savefig(out_png, dpi=150)
    print(f"\nPlot saved: {out_png}")

    # ── H070 sanity comparison ──
    print("\n" + "─" * 78)
    print("H070 sanity comparison (either-side reach ≥ 1.0×)")
    print("─" * 78)
    print(f"  H070 (SMA20 method):  norm<0.70=29.9%, 0.70-0.85=40.7%, 0.85-1.00=37.4%, 1.00-1.30=38.5%, ≥1.30=61.0%")
    vals = [(df[mask]["hl_ratio"] >= 1.0).mean() for mask in abs_masks]
    print(f"  H092 (EMA20 method):  norm<0.70={vals[0]:.1%}, 0.70-0.85={vals[1]:.1%}, 0.85-1.00={vals[2]:.1%}, 1.00-1.30={vals[3]:.1%}, ≥1.30={vals[4]:.1%}")


if __name__ == "__main__":
    main()
