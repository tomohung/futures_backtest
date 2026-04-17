#!/usr/bin/env python3
"""H068 Phase 1+2: Reversal Weekday Effect — 分佈探索 + 回測驗證。

Usage:
    uv run python research/active/H068-reversal-weekday-effect/explore.py
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
OUT_DIR = Path("research/active/H068-reversal-weekday-effect/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.size"] = 11
plt.rcParams["figure.figsize"] = (16, 10)

LIVE_PARAMS = dict(
    vol_ratio=1.2, sl_ema_fraction=0.25, exhaust_fraction=0.5,
    signal_skip=0, sat_pullback_fraction=0.5,
)

IS_END = "2024-12-31"
OOS_START = "2025-01-01"


def compute_night_norm():
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
    return night


def calc(t):
    n = len(t)
    if n == 0:
        return {"N": 0, "WR": 0, "PF": 0, "avg": 0, "total": 0, "sharpe": 0}
    w = t[t["PnL"] > 0]["PnL"].sum()
    l = abs(t[t["PnL"] <= 0]["PnL"].sum())
    pnl_pct = t["PnL"] / t["EntryPrice"] * 100
    sharpe = pnl_pct.mean() / pnl_pct.std() * np.sqrt(252) if pnl_pct.std() > 0 else 0
    return {"N": n, "WR": (t["PnL"] > 0).sum() / n,
            "PF": w / l if l > 0 else float("inf"),
            "avg": t["PnL"].mean(), "total": t["PnL"].sum(), "sharpe": sharpe}


def fmt(s):
    return (f"N={s['N']:3d}  WR={s['WR']:.1%}  PF={s['PF']:.2f}  "
            f"avg={s['avg']:+.0f}  total={s['total']:+,.0f}  Sharpe={s['sharpe']:.2f}")


def main():
    print("=" * 70)
    print("H068: Reversal Weekday Effect")
    print("=" * 70)

    night = compute_night_norm()

    print("\nRunning Reversal backtest...")
    df = load_data_for_reversal()
    bt = Backtest(df, ReversalStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**LIVE_PARAMS)
    trades = stats["_trades"].copy()
    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["trade_date"] = trades["EntryTime"].dt.normalize()
    trades["weekday"] = trades["EntryTime"].dt.dayofweek
    trades["year"] = trades["EntryTime"].dt.year

    merged = trades.merge(night[["night_norm"]], left_on="trade_date",
                          right_index=True, how="inner")
    print(f"Trades: {len(merged)}")

    wd_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']

    # ── Phase 1: Weekday breakdown ──
    print("\n── Weekday breakdown ──")
    print(f"  {'Day':>4}  {fmt(calc(merged))[:0]}", end="")
    wd_stats = {}
    for wd in range(5):
        s = calc(merged[merged["weekday"] == wd])
        wd_stats[wd] = s
        print(f"  {wd_names[wd]:>4}  {fmt(s)}")

    # ── Cross-year stability per weekday ──
    print("\n── Cross-year stability ──")
    years = sorted(merged["year"].unique())
    wd_yearly = {wd: [] for wd in range(5)}

    print(f"  {'Year':>6}", end="")
    for wd in range(5):
        print(f"  {wd_names[wd]:>8}", end="")
    print()

    for y in years:
        yt = merged[merged["year"] == y]
        print(f"  {y:>6}", end="")
        for wd in range(5):
            s = calc(yt[yt["weekday"] == wd])
            wd_yearly[wd].append(s["PF"])
            if s["N"] > 0:
                print(f"  {s['PF']:>5.2f}({s['N']:>2})", end="")
            else:
                print(f"       —   ", end="")
        print()

    print(f"\n  {'Consistency':>6}", end="")
    for wd in range(5):
        above1 = sum(1 for pf in wd_yearly[wd] if pf > 1.0)
        print(f"  {above1}/{len(years):>6}", end="")
    print()

    # ── Night vol × weekday cross-analysis ──
    print("\n── Night vol × Weekday ──")
    print(f"  {'Day':>4}  {'HIGH_N':>6} {'HIGH_PF':>7}  {'LOW_N':>5} {'LOW_PF':>7}")
    for wd in range(5):
        wd_data = merged[merged["weekday"] == wd]
        wd_med = wd_data["night_norm"].median()
        hi = calc(wd_data[wd_data["night_norm"] >= wd_med])
        lo = calc(wd_data[wd_data["night_norm"] < wd_med])
        print(f"  {wd_names[wd]:>4}  {hi['N']:>6} {hi['PF']:>7.2f}  {lo['N']:>5} {lo['PF']:>7.2f}")

    # ── Filter combinations ──
    print("\n── Filter combinations ──")
    is_t = merged[merged["trade_date"] <= IS_END]
    oos_t = merged[merged["trade_date"] >= OOS_START]

    combos = {
        "No filter": lambda t: pd.Series(True, index=t.index),
        "Skip Mon": lambda t: t["weekday"] != 0,
        "Skip Fri": lambda t: t["weekday"] != 4,
        "Skip Mon+Fri": lambda t: ~t["weekday"].isin([0, 4]),
        "Night vol only": lambda t: t["night_norm"] >= 0.85,
        "Night vol + skip Mon": lambda t: (t["night_norm"] >= 0.85) & (t["weekday"] != 0),
        "Night vol + skip Fri": lambda t: (t["night_norm"] >= 0.85) & (t["weekday"] != 4),
        "Night vol + skip MF": lambda t: (t["night_norm"] >= 0.85) & (~t["weekday"].isin([0, 4])),
    }

    print(f"\n  {'Config':>25}  {'IS_N':>5} {'IS_PF':>6} {'IS_Sh':>6}  "
          f"{'OOS_N':>5} {'OOS_PF':>6} {'OOS_Sh':>6}")
    combo_results = {}
    for name, filt in combos.items():
        si = calc(is_t[filt(is_t)])
        so = calc(oos_t[filt(oos_t)])
        combo_results[name] = {"is": si, "oos": so}
        print(f"  {name:>25}  {si['N']:>5} {si['PF']:>6.2f} {si['sharpe']:>6.2f}  "
              f"{so['N']:>5} {so['PF']:>6.2f} {so['sharpe']:>6.2f}")

    # ── Walk-forward ──
    print("\n── Walk-forward: skip Mon+Fri vs baseline ──")
    wf_results = []
    for y in years:
        if y == years[0]:
            continue
        yt = merged[merged["year"] == y]
        yt_base = yt
        yt_skip = yt[~yt["weekday"].isin([0, 4])]
        yt_nvf = yt[yt["night_norm"] >= 0.85]
        yt_both = yt[(yt["night_norm"] >= 0.85) & (~yt["weekday"].isin([0, 4]))]
        sb = calc(yt_base)
        ss = calc(yt_skip)
        sn = calc(yt_nvf)
        sc = calc(yt_both)
        wf_results.append({"year": y, "base": sb, "skip_mf": ss, "nvf": sn, "both": sc})
        print(f"  {y}:  base PF={sb['PF']:.2f}({sb['N']})  "
              f"skip_MF PF={ss['PF']:.2f}({ss['N']})  "
              f"nvf PF={sn['PF']:.2f}({sn['N']})  "
              f"both PF={sc['PF']:.2f}({sc['N']})")

    # ── Visualization ──
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("H068: Reversal Weekday Effect", fontsize=14)

    # (a) PF by weekday
    ax = axes[0, 0]
    pfs = [wd_stats[wd]["PF"] for wd in range(5)]
    colors = ["#ef9a9a" if pf < 1.0 else "#66bb6a" for pf in pfs]
    ax.bar(range(5), pfs, color=colors)
    ax.set_xticks(range(5))
    ax.set_xticklabels([f"{wd_names[wd]}\n(N={wd_stats[wd]['N']})" for wd in range(5)])
    ax.axhline(1.0, color="red", linewidth=0.5, linestyle="--")
    ax.set_ylabel("Profit Factor")
    ax.set_title("(a) PF by Weekday")
    for i, pf in enumerate(pfs):
        ax.text(i, pf + 0.03, f"{pf:.2f}", ha="center", fontsize=10)

    # (b) Yearly PF by weekday heatmap
    ax = axes[0, 1]
    hm = np.array([[calc(merged[(merged["year"] == y) & (merged["weekday"] == wd)])["PF"]
                     for wd in range(5)] for y in years])
    hm = np.clip(hm, 0, 4)
    im = ax.imshow(hm, cmap="RdYlGn", aspect="auto", vmin=0, vmax=3)
    ax.set_xticks(range(5))
    ax.set_xticklabels(wd_names)
    ax.set_yticks(range(len(years)))
    ax.set_yticklabels([str(y) for y in years])
    for i in range(len(years)):
        for j in range(5):
            v = hm[i, j]
            ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=9,
                    color="white" if v < 1.0 else "black")
    ax.set_title("(b) PF by Year × Weekday (clipped at 4)")
    fig.colorbar(im, ax=ax)

    # (c) IS vs OOS comparison
    ax = axes[1, 0]
    names_short = ["None", "Mon", "Fri", "M+F", "NVF", "NVF+M", "NVF+F", "NVF+MF"]
    x = np.arange(len(names_short))
    w = 0.35
    is_pfs = [combo_results[k]["is"]["PF"] for k in combos]
    oos_pfs = [combo_results[k]["oos"]["PF"] for k in combos]
    ax.bar(x - w/2, is_pfs, w, label="IS", color="#66bb6a")
    ax.bar(x + w/2, oos_pfs, w, label="OOS", color="#42a5f5")
    ax.set_xticks(x)
    ax.set_xticklabels(names_short, rotation=45, ha="right", fontsize=9)
    ax.axhline(1.0, color="red", linewidth=0.5, linestyle="--")
    ax.set_ylabel("Profit Factor")
    ax.set_title("(c) IS vs OOS: Filter Combinations")
    ax.legend()

    # (d) Walk-forward
    ax = axes[1, 1]
    wf_years = [r["year"] for r in wf_results]
    x = np.arange(len(wf_years))
    w = 0.2
    ax.bar(x - 1.5*w, [r["base"]["PF"] for r in wf_results], w, label="Baseline", color="#bdbdbd")
    ax.bar(x - 0.5*w, [r["skip_mf"]["PF"] for r in wf_results], w, label="Skip M+F", color="#ff9800")
    ax.bar(x + 0.5*w, [r["nvf"]["PF"] for r in wf_results], w, label="NVF", color="#66bb6a")
    ax.bar(x + 1.5*w, [r["both"]["PF"] for r in wf_results], w, label="NVF+M+F", color="#9c27b0")
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in wf_years])
    ax.axhline(1.0, color="red", linewidth=0.5, linestyle="--")
    ax.set_ylabel("Profit Factor")
    ax.set_title("(d) Walk-Forward: Filter Comparison")
    ax.legend(fontsize=9)

    plt.tight_layout()
    fig_path = OUT_DIR / "h068_reversal_weekday.png"
    plt.savefig(fig_path, dpi=150)
    print(f"\nSaved → {fig_path}")
    plt.close()


if __name__ == "__main__":
    main()
