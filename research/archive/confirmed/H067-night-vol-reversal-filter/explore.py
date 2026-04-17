#!/usr/bin/env python3
"""H067 Phase 1: Night Session Volatility as Reversal Filter — 分佈探索。

Usage:
    uv run python research/active/H067-night-vol-reversal-filter/explore.py
"""

import bisect
import duckdb
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

from backtesting import Backtest
from src.backtest.runner import load_data_for_reversal
from src.strategies.reversal import ReversalStrategy

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H067-night-vol-reversal-filter/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.size"] = 11
plt.rcParams["figure.figsize"] = (16, 10)

REVERSAL_PARAMS = dict(
    vol_ratio=1.2,
    sl_ema_fraction=0.25,
    exhaust_fraction=0.5,
    signal_skip=0,
    sat_pullback_fraction=0.5,
)


def compute_night_ranges() -> pd.DataFrame:
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
            FROM ohlcv_1m WHERE symbol = 'TX'
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
        return day_dates_list[idx] if idx < len(day_dates_list) else None

    night_raw["trade_date"] = night_raw["timestamp"].apply(find_next_trade_date)
    night_raw = night_raw.dropna(subset=["trade_date"])

    night = night_raw.groupby("trade_date").agg(
        night_high=("high", "max"), night_low=("low", "min"),
        night_bars=("high", "count"),
    )
    night["night_range"] = night["night_high"] - night["night_low"]
    night = night[night["night_bars"] >= 100].copy()
    night["sma20"] = night["night_range"].rolling(20).mean()
    night["night_norm"] = night["night_range"] / night["sma20"]
    return night


def calc_stats(trades: pd.DataFrame) -> dict:
    n = len(trades)
    if n == 0:
        return {"N": 0, "WR": 0, "PF": 0, "avg_pnl": 0, "total_pnl": 0, "sharpe": 0, "max_dd_pts": 0}
    wins = trades[trades["PnL"] > 0]["PnL"].sum()
    losses = abs(trades[trades["PnL"] <= 0]["PnL"].sum())
    pnl_pct = trades["PnL"] / trades["EntryPrice"] * 100
    sharpe = pnl_pct.mean() / pnl_pct.std() * np.sqrt(252) if pnl_pct.std() > 0 else 0
    cum = trades["PnL"].cumsum()
    dd = cum - cum.cummax()
    return {
        "N": n, "WR": (trades["PnL"] > 0).sum() / n,
        "PF": wins / losses if losses > 0 else float("inf"),
        "avg_pnl": trades["PnL"].mean(), "total_pnl": trades["PnL"].sum(),
        "sharpe": sharpe, "max_dd_pts": dd.min(),
    }


def fmt(s: dict) -> str:
    return (f"N={s['N']:3d}  WR={s['WR']:.1%}  PF={s['PF']:.2f}  "
            f"avg={s['avg_pnl']:+.0f}  total={s['total_pnl']:+,.0f}  "
            f"Sharpe={s['sharpe']:.2f}  MDD={s['max_dd_pts']:+.0f}")


def main():
    print("=" * 70)
    print("H067 Phase 1+2: Night Session Volatility as Reversal Filter")
    print("=" * 70)

    night = compute_night_ranges()
    print(f"Night sessions: {len(night)} days")

    print("\nRunning Reversal backtest...")
    df = load_data_for_reversal()
    print(f"  {len(df):,} bars  [{df.index[0]} → {df.index[-1]}]")

    bt = Backtest(df, ReversalStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**REVERSAL_PARAMS)
    trades = stats["_trades"].copy()
    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["trade_date"] = trades["EntryTime"].dt.normalize()
    trades["weekday"] = trades["EntryTime"].dt.dayofweek
    trades["year"] = trades["EntryTime"].dt.year

    merged = trades.merge(night[["night_norm"]], left_on="trade_date", right_index=True, how="inner")
    print(f"Total trades: {len(merged)}")

    # ── Phase 1: Distribution ────────────────────────────────────────────

    # Median split
    print("\n── Phase 1: Median split ──")
    median = merged["night_norm"].median()
    print(f"  Median night_norm = {median:.3f}")

    hi = merged[merged["night_norm"] >= median]
    lo = merged[merged["night_norm"] < median]
    hi_s = calc_stats(hi)
    lo_s = calc_stats(lo)
    print(f"  Night HIGH vol  {fmt(hi_s)}")
    print(f"  Night LOW vol   {fmt(lo_s)}")
    pf_diff = (hi_s["PF"] - lo_s["PF"]) / lo_s["PF"] * 100 if lo_s["PF"] > 0 else float("inf")
    print(f"  PF diff: {pf_diff:+.1f}%")

    # Quartile
    print("\n── Quartile ──")
    merged["q4"] = pd.qcut(merged["night_norm"], 4, labels=False)
    q_stats = []
    for g in range(4):
        s = calc_stats(merged[merged["q4"] == g])
        q_stats.append(s)
        label = "(low)" if g == 0 else "(high)" if g == 3 else "     "
        print(f"  Q{g+1} {label}  {fmt(s)}")

    # Yearly stability
    print("\n── Cross-year stability ──")
    years = sorted(merged["year"].unique())
    yearly_results = []
    print(f"  {'Year':>6}  {'N_hi':>5} {'WR_hi':>6} {'PF_hi':>6}  "
          f"{'N_lo':>5} {'WR_lo':>6} {'PF_lo':>6}  {'hi>lo?':>6}")
    for y in years:
        yd = merged[merged["year"] == y]
        ym = yd["night_norm"].median()
        sh = calc_stats(yd[yd["night_norm"] >= ym])
        sl = calc_stats(yd[yd["night_norm"] < ym])
        c = sh["PF"] > sl["PF"]
        yearly_results.append({"year": y, "hi": sh, "lo": sl, "consistent": c})
        print(f"  {y:>6}  {sh['N']:>5} {sh['WR']:>6.1%} {sh['PF']:>6.2f}  "
              f"{sl['N']:>5} {sl['WR']:>6.1%} {sl['PF']:>6.2f}  "
              f"{'✓' if c else '✗':>6}")
    n_consistent = sum(r["consistent"] for r in yearly_results)
    print(f"\n  Consistency: {n_consistent}/{len(years)} years")

    # ── Phase 2: IS/OOS + Sensitivity ────────────────────────────────────

    IS_END = "2024-12-31"
    OOS_START = "2025-01-01"
    is_t = merged[merged["trade_date"] <= IS_END]
    oos_t = merged[merged["trade_date"] >= OOS_START]
    print(f"\n── Phase 2: IS ({len(is_t)} trades) / OOS ({len(oos_t)} trades) ──")

    # Threshold sensitivity
    print(f"\n  {'Thr':>6}  {'IS_N':>5} {'IS_WR':>6} {'IS_PF':>6}  "
          f"{'OOS_N':>5} {'OOS_WR':>6} {'OOS_PF':>6}")
    sens_results = []
    for thr in np.arange(0.70, 1.15, 0.05):
        is_f = is_t[is_t["night_norm"] >= thr]
        oos_f = oos_t[oos_t["night_norm"] >= thr]
        si = calc_stats(is_f)
        so = calc_stats(oos_f)
        sens_results.append({"thr": thr, "is": si, "oos": so})
        marker = " ←" if abs(thr - 0.85) < 0.03 else ""
        print(f"  {thr:>6.2f}  {si['N']:>5} {si['WR']:>6.1%} {si['PF']:>6.2f}  "
              f"{so['N']:>5} {so['WR']:>6.1%} {so['PF']:>6.2f}{marker}")

    # Baseline vs filtered
    print("\n── Baseline comparison ──")
    all_s = calc_stats(merged)
    filt_s = calc_stats(merged[merged["night_norm"] >= 0.85])
    is_base = calc_stats(is_t)
    oos_base = calc_stats(oos_t)
    is_filt = calc_stats(is_t[is_t["night_norm"] >= 0.85])
    oos_filt = calc_stats(oos_t[oos_t["night_norm"] >= 0.85])

    print(f"  All trades        {fmt(all_s)}")
    print(f"  night_norm>=0.85  {fmt(filt_s)}")
    print(f"\n  IS  baseline      {fmt(is_base)}")
    print(f"  IS  filtered      {fmt(is_filt)}")
    print(f"  OOS baseline      {fmt(oos_base)}")
    print(f"  OOS filtered      {fmt(oos_filt)}")

    # Walk-forward
    print("\n── Walk-forward (yearly rolling threshold) ──")
    wf_results = []
    for y in years:
        prior = merged[merged["year"] < y]
        if len(prior) < 20:
            continue
        y_thr = prior["night_norm"].median()
        yt = merged[merged["year"] == y]
        y_filt = yt[yt["night_norm"] >= y_thr]
        y_all = yt
        sf = calc_stats(y_filt)
        sa = calc_stats(y_all)
        wf_results.append({"year": y, "thr": y_thr, "filt": sf, "all": sa})
        beat = sf["PF"] > sa["PF"]
        print(f"  {y} (thr={y_thr:.3f}):  filtered {fmt(sf)}")
        print(f"  {' ' * 20}  baseline {fmt(sa)}  {'✓' if beat else '✗'}")

    wf_beat = sum(1 for r in wf_results if r["filt"]["PF"] > r["all"]["PF"])
    print(f"\n  Walk-forward filtered beat baseline: {wf_beat}/{len(wf_results)} years")

    # ── Visualization ────────────────────────────────────────────────────
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("H067: Night Session Volatility × Reversal Performance", fontsize=14)

    # (a) Scatter
    ax = axes[0, 0]
    colors = ["#d32f2f" if p < 0 else "#2e7d32" for p in merged["PnL"]]
    ax.scatter(merged["night_norm"], merged["PnL"], alpha=0.3, s=12, c=colors)
    ax.axhline(0, color="gray", linewidth=0.5)
    ax.axvline(0.85, color="blue", linewidth=1, linestyle="--", label="thr=0.85")
    ax.set_xlabel("Night Range (SMA20 normalized)")
    ax.set_ylabel("Trade PnL (pts)")
    ax.set_title("(a) Night Vol vs Reversal PnL")
    ax.legend()

    # (b) Quartile PF
    ax = axes[0, 1]
    q_labels = [f"Q{g+1}\n(N={q_stats[g]['N']})" for g in range(4)]
    q_pfs = [q_stats[g]["PF"] for g in range(4)]
    q_wrs = [q_stats[g]["WR"] for g in range(4)]
    bars = ax.bar(range(4), q_pfs, color=["#ef9a9a", "#ffcc80", "#a5d6a7", "#66bb6a"])
    ax.set_xticks(range(4))
    ax.set_xticklabels(q_labels)
    ax.axhline(1.0, color="red", linewidth=0.5, linestyle="--")
    ax.set_ylabel("Profit Factor")
    ax.set_title("(b) PF by Night Vol Quartile (Q1=low, Q4=high)")
    for i, (pf, wr) in enumerate(zip(q_pfs, q_wrs)):
        ax.text(i, pf + 0.03, f"PF={pf:.2f}\nWR={wr:.0%}", ha="center", fontsize=9)

    # (c) Yearly PF
    ax = axes[1, 0]
    yr_years = [r["year"] for r in yearly_results]
    x = np.arange(len(yr_years))
    w = 0.35
    ax.bar(x - w/2, [r["hi"]["PF"] for r in yearly_results], w, label="Night HIGH", color="#66bb6a")
    ax.bar(x + w/2, [r["lo"]["PF"] for r in yearly_results], w, label="Night LOW", color="#ef9a9a")
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in yr_years])
    ax.axhline(1.0, color="red", linewidth=0.5, linestyle="--")
    ax.set_ylabel("Profit Factor")
    ax.set_title("(c) Yearly PF: High vs Low Night Vol")
    ax.legend()

    # (d) Threshold sensitivity
    ax = axes[1, 1]
    thrs = [r["thr"] for r in sens_results]
    ax.plot(thrs, [r["is"]["PF"] for r in sens_results], "g-o", markersize=4, label="IS PF")
    ax.plot(thrs, [r["oos"]["PF"] for r in sens_results], "b-s", markersize=4, label="OOS PF")
    ax.axvline(0.85, color="purple", linewidth=1, linestyle="--", label="thr=0.85")
    ax.axhline(1.0, color="red", linewidth=0.5, linestyle="--")
    ax.set_xlabel("Night Norm Threshold")
    ax.set_ylabel("Profit Factor")
    ax.set_title("(d) Threshold Sensitivity")
    ax.legend()
    ax2 = ax.twinx()
    ax2.plot(thrs, [r["is"]["N"] for r in sens_results], "g--", alpha=0.4)
    ax2.plot(thrs, [r["oos"]["N"] for r in sens_results], "b--", alpha=0.4)
    ax2.set_ylabel("# Trades")

    plt.tight_layout()
    fig_path = OUT_DIR / "h067_night_vol_reversal.png"
    plt.savefig(fig_path, dpi=150)
    print(f"\nSaved → {fig_path}")
    plt.close()


if __name__ == "__main__":
    main()
