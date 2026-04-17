#!/usr/bin/env python3
"""H066 Phase 1: Night Session Volatility as EstHL Filter — 分佈探索。

分析夜盤振幅（EMA20 正規化）高低分組對 EstHL 績效的區分力。

Usage:
    uv run python research/active/H066-night-vol-esthl-filter/explore.py
"""

import bisect
import duckdb
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

from backtesting import Backtest
from src.backtest.runner import load_data_for_orb_est_hl
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H066-night-vol-esthl-filter/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.size"] = 11
plt.rcParams["figure.figsize"] = (14, 8)

ESTHL_PARAMS = dict(
    sl_ema_fraction=0.25,
    adx_min=0.0,
    long_only=True,
    vwap_days=2,
    skip_thursday=False,
    skip_friday=False,
)


# ── 1. Night session amplitude ────────────────────────────────────────────

def compute_night_ranges() -> pd.DataFrame:
    """Compute night session H-L per trading date with EMA20 normalization."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        day_dates_df = conn.execute("""
            SELECT DISTINCT timestamp::DATE AS trade_date
            FROM ohlcv_1m WHERE symbol = 'TX'
              AND timestamp::TIME >= '08:45' AND timestamp::TIME < '13:45'
            ORDER BY trade_date
        """).df()
        day_dates_list = sorted(pd.to_datetime(day_dates_df["trade_date"]).tolist())

        night_raw = conn.execute("""
            SELECT timestamp, high, low
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND (timestamp::TIME >= '15:00' OR timestamp::TIME < '05:00')
            ORDER BY timestamp
        """).df()

    night_raw["timestamp"] = pd.to_datetime(night_raw["timestamp"])

    def find_next_trade_date(ts):
        cal_time = ts.time()
        if cal_time >= pd.Timestamp("15:00").time():
            search_date = (ts + pd.Timedelta(days=1)).normalize()
        else:
            search_date = ts.normalize()
        idx = bisect.bisect_left(day_dates_list, search_date)
        if idx < len(day_dates_list):
            return day_dates_list[idx]
        return None

    night_raw["trade_date"] = night_raw["timestamp"].apply(find_next_trade_date)
    night_raw = night_raw.dropna(subset=["trade_date"])

    night = night_raw.groupby("trade_date").agg(
        night_high=("high", "max"),
        night_low=("low", "min"),
        night_bars=("high", "count"),
    )
    night["night_range"] = night["night_high"] - night["night_low"]
    night = night[night["night_bars"] >= 100].copy()

    night["night_ema20"] = night["night_range"].ewm(span=20, adjust=False).mean()
    night["night_norm"] = night["night_range"] / night["night_ema20"]

    return night


# ── 2. EstHL trades ──────────────────────────────────────────────────────

def run_esthl_backtest() -> pd.DataFrame:
    """Run EstHL backtest WITHOUT weekday filter, return per-trade results."""
    print("Loading data for EstHL backtest...")
    df = load_data_for_orb_est_hl()
    print(f"  {len(df):,} bars  [{df.index[0]} → {df.index[-1]}]")

    bt = Backtest(df, ORBWithEstHLExitStrategy,
                  cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**ESTHL_PARAMS)
    trades = stats["_trades"].copy()

    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["trade_date"] = trades["EntryTime"].dt.normalize()
    trades["weekday"] = trades["EntryTime"].dt.dayofweek
    trades["weekday_name"] = trades["EntryTime"].dt.day_name()
    trades["year"] = trades["EntryTime"].dt.year

    n = len(trades)
    wins = (trades["PnL"] > 0).sum()
    total_pnl = trades["PnL"].sum()
    print(f"  EstHL (no weekday filter): {n} trades, WR={wins/n:.1%}, total PnL={total_pnl:,.0f}")
    return trades


# ── 3. Analysis helpers ──────────────────────────────────────────────────

def calc_stats(group: pd.DataFrame) -> dict:
    n = len(group)
    if n == 0:
        return {"N": 0, "WR": 0, "PF": 0, "avg_pnl": 0, "total_pnl": 0}
    wins = group[group["PnL"] > 0]["PnL"].sum()
    losses = abs(group[group["PnL"] <= 0]["PnL"].sum())
    return {
        "N": n,
        "WR": (group["PnL"] > 0).sum() / n,
        "PF": wins / losses if losses > 0 else float("inf"),
        "avg_pnl": group["PnL"].mean(),
        "total_pnl": group["PnL"].sum(),
    }


def print_group_stats(label: str, stats: dict):
    print(f"  {label:20s}  N={stats['N']:4d}  WR={stats['WR']:.1%}  "
          f"PF={stats['PF']:.2f}  avg={stats['avg_pnl']:+.0f}  "
          f"total={stats['total_pnl']:+,.0f}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("H066 Phase 1: Night Session Volatility as EstHL Filter")
    print("=" * 60)

    # Step 1: Night ranges
    print("\n── Step 1: Night session amplitude ──")
    night = compute_night_ranges()
    print(f"  Night sessions: {len(night)} days")
    print(f"  Night range: mean={night['night_range'].mean():.0f}, "
          f"median={night['night_range'].median():.0f}")
    print(f"  Night norm: mean={night['night_norm'].mean():.3f}, "
          f"median={night['night_norm'].median():.3f}")

    # Step 2: EstHL trades
    print("\n── Step 2: EstHL backtest (no weekday filter) ──")
    trades = run_esthl_backtest()

    # Step 3: Pair night vol with trades
    print("\n── Step 3: Pair night vol with EstHL trades ──")
    merged = trades.merge(
        night[["night_range", "night_ema20", "night_norm"]],
        left_on="trade_date",
        right_index=True,
        how="inner",
    )
    print(f"  Paired trades: {len(merged)} / {len(trades)}")

    # ── Median split ──
    print("\n── Step 4: Median split analysis ──")
    median_norm = merged["night_norm"].median()
    print(f"  Median night_norm = {median_norm:.3f}")

    hi_vol = merged[merged["night_norm"] >= median_norm]
    lo_vol = merged[merged["night_norm"] < median_norm]

    hi_stats = calc_stats(hi_vol)
    lo_stats = calc_stats(lo_vol)
    print_group_stats("Night HIGH vol", hi_stats)
    print_group_stats("Night LOW vol", lo_stats)

    pf_diff_pct = (hi_stats["PF"] - lo_stats["PF"]) / lo_stats["PF"] * 100 if lo_stats["PF"] > 0 else float("inf")
    print(f"\n  PF difference: {pf_diff_pct:+.1f}%  (high vs low)")

    # ── Tercile split ──
    print("\n── Step 5: Tercile & quartile splits ──")
    for n_groups, label in [(3, "Tercile"), (4, "Quartile")]:
        merged[f"g{n_groups}"] = pd.qcut(merged["night_norm"], n_groups, labels=False)
        print(f"\n  {label} split:")
        for g in range(n_groups):
            g_data = merged[merged[f"g{n_groups}"] == g]
            g_stats = calc_stats(g_data)
            tag = f"  G{g} (n_norm {'lowest' if g == 0 else 'highest' if g == n_groups - 1 else 'mid'})"
            print_group_stats(tag, g_stats)

    # ── Cross-year stability ──
    print("\n── Step 6: Cross-year stability ──")
    years = sorted(merged["year"].unique())
    yearly_results = []
    print(f"  {'Year':>6}  {'N_hi':>5} {'WR_hi':>6} {'PF_hi':>6}  "
          f"{'N_lo':>5} {'WR_lo':>6} {'PF_lo':>6}  {'hi>lo?':>6}")

    for y in years:
        yd = merged[merged["year"] == y]
        y_median = yd["night_norm"].median()
        y_hi = yd[yd["night_norm"] >= y_median]
        y_lo = yd[yd["night_norm"] < y_median]
        sh = calc_stats(y_hi)
        sl = calc_stats(y_lo)
        consistent = sh["PF"] > sl["PF"]
        yearly_results.append({"year": y, "hi_pf": sh["PF"], "lo_pf": sl["PF"],
                               "hi_wr": sh["WR"], "lo_wr": sl["WR"],
                               "hi_n": sh["N"], "lo_n": sl["N"],
                               "consistent": consistent})
        print(f"  {y:>6}  {sh['N']:>5} {sh['WR']:>6.1%} {sh['PF']:>6.2f}  "
              f"{sl['N']:>5} {sl['WR']:>6.1%} {sl['PF']:>6.2f}  "
              f"{'✓' if consistent else '✗':>6}")

    n_consistent = sum(r["consistent"] for r in yearly_results)
    print(f"\n  Consistency: {n_consistent}/{len(years)} years hi_PF > lo_PF")

    # ── Cross-analysis: night vol × weekday ──
    print("\n── Step 7: Night vol × Weekday cross-analysis ──")
    weekday_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    print(f"  {'Weekday':>8}  {'N_hi':>5} {'WR_hi':>6} {'PF_hi':>6}  "
          f"{'N_lo':>5} {'WR_lo':>6} {'PF_lo':>6}")

    for wd in range(5):
        wd_data = merged[merged["weekday"] == wd]
        if len(wd_data) < 10:
            continue
        wd_median = wd_data["night_norm"].median()
        wd_hi = wd_data[wd_data["night_norm"] >= wd_median]
        wd_lo = wd_data[wd_data["night_norm"] < wd_median]
        sh = calc_stats(wd_hi)
        sl = calc_stats(wd_lo)
        print(f"  {weekday_names[wd]:>8}  {sh['N']:>5} {sh['WR']:>6.1%} {sh['PF']:>6.2f}  "
              f"{sl['N']:>5} {sl['WR']:>6.1%} {sl['PF']:>6.2f}")

    # ── Baseline comparison: weekday filter only ──
    print("\n── Step 8: Baseline comparison ──")
    no_filter = calc_stats(merged)
    weekday_filtered = calc_stats(merged[~merged["weekday"].isin([3, 4])])
    print_group_stats("No filter", no_filter)
    print_group_stats("Skip Thu+Fri", weekday_filtered)
    print_group_stats("Night HIGH vol only", hi_stats)

    combined = merged[(merged["night_norm"] >= median_norm) & (~merged["weekday"].isin([3, 4]))]
    combined_stats = calc_stats(combined)
    print_group_stats("HIGH vol + skip TF", combined_stats)

    # ── Visualization ──
    print("\n── Step 9: Visualization ──")

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("H066: Night Session Volatility × EstHL Performance", fontsize=14)

    # (a) Scatter: night_norm vs trade PnL
    ax = axes[0, 0]
    colors = ["#d32f2f" if p < 0 else "#2e7d32" for p in merged["PnL"]]
    ax.scatter(merged["night_norm"], merged["PnL"], alpha=0.4, s=15, c=colors)
    ax.axhline(0, color="gray", linewidth=0.5)
    ax.axvline(median_norm, color="blue", linewidth=1, linestyle="--", label=f"median={median_norm:.2f}")
    ax.set_xlabel("Night Range (EMA20 normalized)")
    ax.set_ylabel("Trade PnL (pts)")
    ax.set_title("(a) Night Vol vs EstHL PnL")
    ax.legend()

    # (b) Grouped bar: PF by quartile
    ax = axes[0, 1]
    q_labels = []
    q_pfs = []
    q_wrs = []
    for g in range(4):
        g_data = merged[merged["g4"] == g]
        s = calc_stats(g_data)
        q_labels.append(f"Q{g+1}\n(N={s['N']})")
        q_pfs.append(s["PF"])
        q_wrs.append(s["WR"])
    x = np.arange(4)
    bars = ax.bar(x, q_pfs, color=["#ef9a9a", "#ffcc80", "#a5d6a7", "#66bb6a"])
    ax.set_xticks(x)
    ax.set_xticklabels(q_labels)
    ax.axhline(1.0, color="red", linewidth=0.5, linestyle="--")
    ax.set_ylabel("Profit Factor")
    ax.set_title("(b) PF by Night Vol Quartile (Q1=low, Q4=high)")
    for i, (pf, wr) in enumerate(zip(q_pfs, q_wrs)):
        ax.text(i, pf + 0.05, f"PF={pf:.2f}\nWR={wr:.0%}", ha="center", fontsize=9)

    # (c) Year-by-year PF comparison
    ax = axes[1, 0]
    yr_df = pd.DataFrame(yearly_results)
    x = np.arange(len(yr_df))
    w = 0.35
    ax.bar(x - w/2, yr_df["hi_pf"], w, label="Night HIGH vol", color="#66bb6a")
    ax.bar(x + w/2, yr_df["lo_pf"], w, label="Night LOW vol", color="#ef9a9a")
    ax.set_xticks(x)
    ax.set_xticklabels(yr_df["year"].astype(str))
    ax.axhline(1.0, color="red", linewidth=0.5, linestyle="--")
    ax.set_ylabel("Profit Factor")
    ax.set_title("(c) Yearly PF: High vs Low Night Vol")
    ax.legend()

    # (d) Weekday × night vol heatmap
    ax = axes[1, 1]
    heatmap_data = []
    for wd in range(5):
        row = []
        for vol_group in ["high", "low"]:
            wd_data = merged[merged["weekday"] == wd]
            wd_median = wd_data["night_norm"].median() if len(wd_data) > 0 else 1.0
            if vol_group == "high":
                subset = wd_data[wd_data["night_norm"] >= wd_median]
            else:
                subset = wd_data[wd_data["night_norm"] < wd_median]
            s = calc_stats(subset)
            row.append(s["PF"])
        heatmap_data.append(row)
    hm = np.array(heatmap_data)
    im = ax.imshow(hm, cmap="RdYlGn", aspect="auto", vmin=0, vmax=max(3.0, hm.max()))
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Night HIGH", "Night LOW"])
    ax.set_yticks(range(5))
    ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri"])
    for i in range(5):
        for j in range(2):
            ax.text(j, i, f"{hm[i, j]:.2f}", ha="center", va="center", fontsize=11,
                    color="white" if hm[i, j] < 1.0 else "black")
    ax.set_title("(d) PF: Weekday × Night Vol")
    fig.colorbar(im, ax=ax, label="Profit Factor")

    plt.tight_layout()
    fig_path = OUT_DIR / "h066_night_vol_esthl.png"
    plt.savefig(fig_path, dpi=150)
    print(f"  Saved → {fig_path}")
    plt.close()

    # ── Summary ──
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total paired trades: {len(merged)}")
    print(f"  Night norm median: {median_norm:.3f}")
    print(f"\n  Median split:")
    print_group_stats("  HIGH vol", hi_stats)
    print_group_stats("  LOW vol", lo_stats)
    print(f"\n  PF diff: {pf_diff_pct:+.1f}%")
    print(f"  Year consistency: {n_consistent}/{len(years)}")
    print(f"\n  Baseline comparison:")
    print_group_stats("  No filter", no_filter)
    print_group_stats("  Skip Thu+Fri", weekday_filtered)
    print_group_stats("  Night HIGH only", hi_stats)
    print_group_stats("  HIGH + skip TF", combined_stats)


if __name__ == "__main__":
    main()
