#!/usr/bin/env python3
"""H070: Night Vol → EstRange Reach Rate.

Analyze whether night session volatility predicts day session HL / EstRange ratio.

Usage:
    uv run python research/active/H070-night-vol-estrange-reach/explore.py
"""

import bisect
import duckdb
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats as sp_stats

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H070-night-vol-estrange-reach/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.size"] = 11
plt.rcParams["figure.figsize"] = (16, 12)


def load_data():
    """Load day session HL, EstRange (EmaHL as proxy), and night_norm."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        # Day session HL per date
        day_hl = conn.execute("""
            SELECT timestamp::DATE AS td,
                   MAX(high) - MIN(low) AS day_hl,
                   MAX(high) AS day_high,
                   MIN(low) AS day_low
            FROM ohlcv_1m WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            GROUP BY td ORDER BY td
        """).df()
        day_hl["td"] = pd.to_datetime(day_hl["td"])

        # EmaHL from ohlcv_1m (the 08:45 bar's value = prior-day EMA, no lookahead)
        ema_hl = conn.execute("""
            SELECT timestamp::DATE AS td,
                   FIRST(close ORDER BY timestamp) AS day_open
            FROM ohlcv_1m WHERE symbol = 'TX'
              AND timestamp::TIME = '08:45:00'
            GROUP BY td ORDER BY td
        """).df()
        ema_hl["td"] = pd.to_datetime(ema_hl["td"])

        # Get EmaHL from runner's precomputed data
        day_dates_df = conn.execute("""
            SELECT DISTINCT timestamp::DATE AS trade_date
            FROM ohlcv_1m WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ORDER BY trade_date
        """).df()
        day_dates_list = sorted(pd.to_datetime(day_dates_df["trade_date"]).tolist())

        # Night ranges
        night_raw = conn.execute("""
            SELECT timestamp, high, low
            FROM ohlcv_1m WHERE symbol = 'TX'
              AND (timestamp::TIME >= '15:00' OR timestamp::TIME < '05:00')
            ORDER BY timestamp
        """).df()

    night_raw["timestamp"] = pd.to_datetime(night_raw["timestamp"])

    def find_next(ts):
        cal_time = ts.time()
        if cal_time >= pd.Timestamp("15:00").time():
            search_date = (ts + pd.Timedelta(days=1)).normalize()
        else:
            search_date = ts.normalize()
        idx = bisect.bisect_left(day_dates_list, search_date)
        return day_dates_list[idx] if idx < len(day_dates_list) else None

    night_raw["trade_date"] = night_raw["timestamp"].apply(find_next)
    night_raw = night_raw.dropna(subset=["trade_date"])

    night = night_raw.groupby("trade_date").agg(
        night_high=("high", "max"), night_low=("low", "min"),
        night_bars=("high", "count"),
    )
    night["night_range"] = night["night_high"] - night["night_low"]
    night = night[night["night_bars"] >= 100].copy()
    night["sma20"] = night["night_range"].rolling(20).mean()
    night["night_norm"] = night["night_range"] / night["sma20"]

    # Compute EmaHL (EMA20 of day session HL) — same as estimate_hl.py
    day_hl = day_hl.set_index("td").sort_index()
    day_hl["ema_hl"] = day_hl["day_hl"].ewm(span=20, adjust=False).mean().shift(1)

    # Merge
    merged = day_hl.join(night[["night_norm", "night_range"]], how="inner")
    merged = merged.dropna(subset=["ema_hl", "night_norm"])
    merged["hl_ratio"] = merged["day_hl"] / merged["ema_hl"]
    merged["weekday"] = merged.index.dayofweek
    merged["year"] = merged.index.year

    return merged


def main():
    print("=" * 70)
    print("H070: Night Vol → EstRange Reach Rate")
    print("=" * 70)

    df = load_data()
    print(f"Total days: {len(df)}")
    print(f"Date range: {df.index[0]} ~ {df.index[-1]}")

    wd_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    years = sorted(df["year"].unique())

    # ── 1. Correlation ──
    print("\n── 1. Correlation: night_norm vs hl_ratio ──")
    r_pearson, p_pearson = sp_stats.pearsonr(df["night_norm"], df["hl_ratio"])
    r_spearman, p_spearman = sp_stats.spearmanr(df["night_norm"], df["hl_ratio"])
    print(f"  Pearson:  r={r_pearson:.4f}, p={p_pearson:.4e}")
    print(f"  Spearman: r={r_spearman:.4f}, p={p_spearman:.4e}")

    # ── 2. Night norm groups → reach rate ──
    print("\n── 2. Night norm groups → HL/EmaHL ratio & reach rate ──")

    thresholds = [("norm < 0.70", df["night_norm"] < 0.70),
                  ("0.70 ≤ norm < 0.85", (df["night_norm"] >= 0.70) & (df["night_norm"] < 0.85)),
                  ("0.85 ≤ norm < 1.00", (df["night_norm"] >= 0.85) & (df["night_norm"] < 1.00)),
                  ("1.00 ≤ norm < 1.30", (df["night_norm"] >= 1.00) & (df["night_norm"] < 1.30)),
                  ("norm ≥ 1.30", df["night_norm"] >= 1.30)]

    print(f"  {'Group':>22}  {'N':>5} {'mean_ratio':>10} {'median':>7} "
          f"{'reach≥0.618':>10} {'reach≥0.75':>9} {'reach≥1.0':>9} {'reach≥1.2':>9}")
    group_stats = []
    for label, mask in thresholds:
        sub = df[mask]
        n = len(sub)
        mean_r = sub["hl_ratio"].mean()
        med_r = sub["hl_ratio"].median()
        r618 = (sub["hl_ratio"] >= 0.618).mean()
        r75 = (sub["hl_ratio"] >= 0.75).mean()
        r100 = (sub["hl_ratio"] >= 1.0).mean()
        r120 = (sub["hl_ratio"] >= 1.2).mean()
        group_stats.append({"label": label, "N": n, "mean": mean_r, "median": med_r,
                            "r618": r618, "r75": r75, "r100": r100, "r120": r120})
        print(f"  {label:>22}  {n:>5} {mean_r:>10.3f} {med_r:>7.3f} "
              f"{r618:>10.1%} {r75:>9.1%} {r100:>9.1%} {r120:>9.1%}")

    # ── 3. Median split: high vs low night vol ──
    print("\n── 3. Median split ──")
    median = df["night_norm"].median()
    hi = df[df["night_norm"] >= median]
    lo = df[df["night_norm"] < median]
    print(f"  Median: {median:.3f}")
    print(f"  HIGH: N={len(hi)}, mean_ratio={hi['hl_ratio'].mean():.3f}, "
          f"reach≥1.0={( hi['hl_ratio'] >= 1.0).mean():.1%}")
    print(f"  LOW:  N={len(lo)}, mean_ratio={lo['hl_ratio'].mean():.3f}, "
          f"reach≥1.0={(lo['hl_ratio'] >= 1.0).mean():.1%}")

    # ── 4. Cross-year stability ──
    print("\n── 4. Cross-year stability (mean hl_ratio: HIGH vs LOW) ──")
    print(f"  {'Year':>6}  {'HI_mean':>8} {'HI_reach1x':>10}  {'LO_mean':>8} {'LO_reach1x':>10}  {'HI>LO':>5}")
    n_consistent = 0
    for y in years:
        yd = df[df["year"] == y]
        ym = yd["night_norm"].median()
        yh = yd[yd["night_norm"] >= ym]
        yl = yd[yd["night_norm"] < ym]
        hm = yh["hl_ratio"].mean()
        lm = yl["hl_ratio"].mean()
        hr = (yh["hl_ratio"] >= 1.0).mean()
        lr = (yl["hl_ratio"] >= 1.0).mean()
        c = hm > lm
        n_consistent += c
        print(f"  {y:>6}  {hm:>8.3f} {hr:>10.1%}  {lm:>8.3f} {lr:>10.1%}  {'✓' if c else '✗':>5}")
    print(f"  Consistency: {n_consistent}/{len(years)}")

    # ── 5. Night norm × Weekday cross-analysis ──
    print("\n── 5. Night norm × Weekday (mean hl_ratio) ──")
    print(f"  {'Day':>4}  {'ALL_mean':>8} {'ALL_reach1x':>10}  "
          f"{'HI_mean':>8} {'HI_reach1x':>10}  {'LO_mean':>8} {'LO_reach1x':>10}")
    for wd in range(5):
        wd_data = df[df["weekday"] == wd]
        wd_med = wd_data["night_norm"].median()
        wh = wd_data[wd_data["night_norm"] >= wd_med]
        wl = wd_data[wd_data["night_norm"] < wd_med]
        print(f"  {wd_names[wd]:>4}  {wd_data['hl_ratio'].mean():>8.3f} "
              f"{(wd_data['hl_ratio'] >= 1.0).mean():>10.1%}  "
              f"{wh['hl_ratio'].mean():>8.3f} {(wh['hl_ratio'] >= 1.0).mean():>10.1%}  "
              f"{wl['hl_ratio'].mean():>8.3f} {(wl['hl_ratio'] >= 1.0).mean():>10.1%}")

    # ── 6. Regression: which explains more? ──
    print("\n── 6. Explanatory power comparison ──")
    def ols_r2(X, y):
        X = np.column_stack([np.ones(len(X)), X])
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        y_hat = X @ beta
        ss_res = ((y - y_hat) ** 2).sum()
        ss_tot = ((y - y.mean()) ** 2).sum()
        return 1 - ss_res / ss_tot

    y = df["hl_ratio"].values
    r2_night = ols_r2(df[["night_norm"]].values, y)

    wd_dummies = pd.get_dummies(df["weekday"], prefix="wd").values
    r2_wd = ols_r2(wd_dummies, y)

    r2_both = ols_r2(np.hstack([df[["night_norm"]].values, wd_dummies]), y)

    print(f"  Night norm only:  R² = {r2_night:.4f}")
    print(f"  Weekday only:     R² = {r2_wd:.4f}")
    print(f"  Both:             R² = {r2_both:.4f}")
    print(f"  Night norm 額外解釋: {r2_both - r2_wd:.4f}")
    print(f"  Weekday 額外解釋:    {r2_both - r2_night:.4f}")

    # ── 7. Visualization ──
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("H070: Night Vol → EstRange Reach Rate", fontsize=14)

    # (a) Scatter: night_norm vs hl_ratio
    ax = axes[0, 0]
    ax.scatter(df["night_norm"], df["hl_ratio"], alpha=0.2, s=10, c="#2196f3")
    ax.axhline(1.0, color="red", linewidth=0.5, linestyle="--", label="HL = EstRange")
    ax.axhline(0.618, color="orange", linewidth=0.5, linestyle="--", label="0.618×")
    ax.axhline(0.75, color="green", linewidth=0.5, linestyle="--", label="0.75×")
    # Trend line
    z = np.polyfit(df["night_norm"], df["hl_ratio"], 1)
    x_line = np.linspace(df["night_norm"].min(), df["night_norm"].max(), 100)
    ax.plot(x_line, np.polyval(z, x_line), "r-", linewidth=2, label=f"r={r_pearson:.3f}")
    ax.set_xlabel("Night Norm (SMA20)")
    ax.set_ylabel("Day HL / EmaHL")
    ax.set_title("(a) Night Vol vs Day Range Ratio")
    ax.legend(fontsize=9)
    ax.set_ylim(0, 3)

    # (b) Reach rate by night norm group
    ax = axes[0, 1]
    labels = [g["label"].split("≤")[-1].split("<")[0].strip() if "≤" in g["label"]
              else g["label"][:8] for g in group_stats]
    labels = [g["label"] for g in group_stats]
    x = np.arange(len(group_stats))
    w = 0.2
    ax.bar(x - 1.5*w, [g["r618"] for g in group_stats], w, label="≥0.618", color="#ffcc80")
    ax.bar(x - 0.5*w, [g["r75"] for g in group_stats], w, label="≥0.75", color="#a5d6a7")
    ax.bar(x + 0.5*w, [g["r100"] for g in group_stats], w, label="≥1.0×", color="#66bb6a")
    ax.bar(x + 1.5*w, [g["r120"] for g in group_stats], w, label="≥1.2×", color="#2e7d32")
    ax.set_xticks(x)
    ax.set_xticklabels([g["label"] for g in group_stats], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Reach Rate")
    ax.set_title("(b) Reach Rate by Night Vol Group")
    ax.legend(fontsize=9)

    # (c) Weekday × night vol heatmap (mean hl_ratio)
    ax = axes[1, 0]
    hm = np.zeros((5, 2))
    for wd in range(5):
        wd_data = df[df["weekday"] == wd]
        wd_med = wd_data["night_norm"].median()
        hm[wd, 0] = wd_data[wd_data["night_norm"] >= wd_med]["hl_ratio"].mean()
        hm[wd, 1] = wd_data[wd_data["night_norm"] < wd_med]["hl_ratio"].mean()
    im = ax.imshow(hm, cmap="RdYlGn", aspect="auto", vmin=0.7, vmax=1.3)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Night HIGH", "Night LOW"])
    ax.set_yticks(range(5))
    ax.set_yticklabels(wd_names)
    for i in range(5):
        for j in range(2):
            ax.text(j, i, f"{hm[i, j]:.3f}", ha="center", va="center", fontsize=11)
    ax.set_title("(c) Mean HL/EmaHL: Weekday × Night Vol")
    fig.colorbar(im, ax=ax)

    # (d) R² comparison
    ax = axes[1, 1]
    bars = ax.bar(["Night norm", "Weekday", "Both"], [r2_night, r2_wd, r2_both],
                  color=["#66bb6a", "#ff9800", "#9c27b0"])
    ax.set_ylabel("R²")
    ax.set_title("(d) Explanatory Power (R²)")
    for b, v in zip(bars, [r2_night, r2_wd, r2_both]):
        ax.text(b.get_x() + b.get_width()/2, v + 0.002, f"{v:.4f}",
                ha="center", fontsize=11)

    plt.tight_layout()
    fig_path = OUT_DIR / "h070_night_vol_estrange.png"
    plt.savefig(fig_path, dpi=150)
    print(f"\nSaved → {fig_path}")
    plt.close()


if __name__ == "__main__":
    main()
