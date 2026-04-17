#!/usr/bin/env python3
"""H066 Phase 2: Night Session Volatility as EstHL Filter — 回測驗證。

Post-hoc filtering approach: run EstHL without weekday filter, then filter trades
based on night_norm. Valid because night_norm is known before market open (15:00-05:00).

Usage:
    uv run python research/active/H066-night-vol-esthl-filter/backtest.py
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
plt.rcParams["figure.figsize"] = (16, 10)

ESTHL_PARAMS = dict(
    sl_ema_fraction=0.25,
    adx_min=0.0,
    long_only=True,
    vwap_days=2,
    skip_thursday=False,
    skip_friday=False,
)

IS_END = "2024-12-31"
OOS_START = "2025-01-01"


# ── Night session amplitude ──────────────────────────────────────────────

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
        return day_dates_list[idx] if idx < len(day_dates_list) else None

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


# ── Helpers ──────────────────────────────────────────────────────────────

def calc_stats(trades: pd.DataFrame) -> dict:
    n = len(trades)
    if n == 0:
        return {"N": 0, "WR": 0, "PF": 0, "avg_pnl": 0, "total_pnl": 0,
                "sharpe": 0, "max_dd_pts": 0, "avg_pnl_pct": 0}
    wins = trades[trades["PnL"] > 0]["PnL"].sum()
    losses = abs(trades[trades["PnL"] <= 0]["PnL"].sum())
    pnl_pct = trades["PnL"] / trades["EntryPrice"] * 100
    sharpe = pnl_pct.mean() / pnl_pct.std() * np.sqrt(252) if pnl_pct.std() > 0 else 0
    cum = trades["PnL"].cumsum()
    dd = cum - cum.cummax()
    return {
        "N": n,
        "WR": (trades["PnL"] > 0).sum() / n,
        "PF": wins / losses if losses > 0 else float("inf"),
        "avg_pnl": trades["PnL"].mean(),
        "total_pnl": trades["PnL"].sum(),
        "sharpe": sharpe,
        "max_dd_pts": dd.min(),
        "avg_pnl_pct": pnl_pct.mean(),
    }


def fmt(s: dict) -> str:
    return (f"N={s['N']:3d}  WR={s['WR']:.1%}  PF={s['PF']:.2f}  "
            f"avg={s['avg_pnl']:+.0f}  total={s['total_pnl']:+,.0f}  "
            f"Sharpe={s['sharpe']:.2f}  MDD={s['max_dd_pts']:+.0f}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("H066 Phase 2: Night Session Volatility as EstHL Filter — Backtest")
    print("=" * 70)

    # Load data & run backtest
    night = compute_night_ranges()
    print(f"Night sessions: {len(night)} days")

    print("\nRunning EstHL backtest (no weekday filter)...")
    df = load_data_for_orb_est_hl()
    bt = Backtest(df, ORBWithEstHLExitStrategy,
                  cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**ESTHL_PARAMS)
    trades = stats["_trades"].copy()
    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["trade_date"] = trades["EntryTime"].dt.normalize()
    trades["weekday"] = trades["EntryTime"].dt.dayofweek
    trades["year"] = trades["EntryTime"].dt.year

    merged = trades.merge(
        night[["night_range", "night_ema20", "night_norm"]],
        left_on="trade_date", right_index=True, how="inner",
    )
    print(f"Total trades: {len(merged)}")

    # Night norm median (computed from IS period only to avoid lookahead)
    is_trades = merged[merged["trade_date"] <= IS_END]
    oos_trades = merged[merged["trade_date"] >= OOS_START]
    is_median = is_trades["night_norm"].median()
    print(f"\nIS period: ≤ {IS_END} ({len(is_trades)} trades)")
    print(f"OOS period: ≥ {OOS_START} ({len(oos_trades)} trades)")
    print(f"IS night_norm median: {is_median:.3f}")

    # ── Filter configurations ────────────────────────────────────────────
    configs = {
        "A: Skip Thu+Fri (baseline)": lambda t: ~t["weekday"].isin([3, 4]),
        "B: Night HIGH only": lambda t: t["night_norm"] >= is_median,
        "C: Night HIGH + skip Fri": lambda t: (t["night_norm"] >= is_median) & (t["weekday"] != 4),
        "D: Night HIGH + skip TF": lambda t: (t["night_norm"] >= is_median) & (~t["weekday"].isin([3, 4])),
        "E: No filter": lambda t: pd.Series(True, index=t.index),
    }

    # ── In-sample / Out-of-sample comparison ─────────────────────────────
    print("\n" + "=" * 70)
    print("IN-SAMPLE (2021-2024)")
    print("=" * 70)
    is_results = {}
    for name, filt in configs.items():
        filtered = is_trades[filt(is_trades)]
        s = calc_stats(filtered)
        is_results[name] = s
        print(f"  {name:35s}  {fmt(s)}")

    print("\n" + "=" * 70)
    print("OUT-OF-SAMPLE (2025-2026)")
    print("=" * 70)
    oos_results = {}
    for name, filt in configs.items():
        filtered = oos_trades[filt(oos_trades)]
        s = calc_stats(filtered)
        oos_results[name] = s
        print(f"  {name:35s}  {fmt(s)}")

    # ── Walk-forward (yearly rolling) ────────────────────────────────────
    print("\n" + "=" * 70)
    print("WALK-FORWARD: Yearly rolling median")
    print("=" * 70)
    print("  Each year uses prior-year median as threshold\n")

    years = sorted(merged["year"].unique())
    wf_results = []

    for y in years:
        prior = merged[merged["year"] < y]
        if len(prior) < 20:
            continue
        y_median = prior["night_norm"].median()
        y_trades = merged[merged["year"] == y]

        y_hi = y_trades[y_trades["night_norm"] >= y_median]
        y_lo = y_trades[y_trades["night_norm"] < y_median]
        y_base = y_trades[~y_trades["weekday"].isin([3, 4])]

        sh = calc_stats(y_hi)
        sl = calc_stats(y_lo)
        sb = calc_stats(y_base)

        wf_results.append({
            "year": y, "median": y_median,
            "hi": sh, "lo": sl, "base": sb,
        })

        print(f"  {y} (threshold={y_median:.3f}):")
        print(f"    Night HIGH      {fmt(sh)}")
        print(f"    Night LOW       {fmt(sl)}")
        print(f"    Skip Thu+Fri    {fmt(sb)}")
        print()

    # ── Parameter sensitivity: threshold values ──────────────────────────
    print("=" * 70)
    print("PARAMETER SENSITIVITY: Night norm threshold")
    print("=" * 70)

    thresholds = np.arange(0.6, 1.4, 0.05)
    sens_results = []

    for thr in thresholds:
        is_hi = is_trades[is_trades["night_norm"] >= thr]
        oos_hi = oos_trades[oos_trades["night_norm"] >= thr]
        s_is = calc_stats(is_hi)
        s_oos = calc_stats(oos_hi)
        sens_results.append({
            "threshold": thr,
            "is_n": s_is["N"], "is_pf": s_is["PF"], "is_wr": s_is["WR"],
            "oos_n": s_oos["N"], "oos_pf": s_oos["PF"], "oos_wr": s_oos["WR"],
        })

    print(f"  {'Thr':>6}  {'IS_N':>5} {'IS_WR':>6} {'IS_PF':>6}  "
          f"{'OOS_N':>5} {'OOS_WR':>6} {'OOS_PF':>6}")
    for r in sens_results:
        marker = " ←median" if abs(r["threshold"] - is_median) < 0.03 else ""
        print(f"  {r['threshold']:>6.2f}  {r['is_n']:>5} {r['is_wr']:>6.1%} {r['is_pf']:>6.2f}  "
              f"{r['oos_n']:>5} {r['oos_wr']:>6.1%} {r['oos_pf']:>6.2f}{marker}")

    # ── Visualization ────────────────────────────────────────────────────
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("H066 Phase 2: Night Vol Filter — Backtest Results", fontsize=14)

    # (a) IS vs OOS comparison bar chart
    ax = axes[0, 0]
    config_names = [k.split(":")[0] for k in configs.keys()]
    x = np.arange(len(config_names))
    w = 0.35
    is_pfs = [is_results[k]["PF"] for k in configs]
    oos_pfs = [oos_results[k]["PF"] for k in configs]
    ax.bar(x - w/2, is_pfs, w, label="IS (2021-24)", color="#66bb6a")
    ax.bar(x + w/2, oos_pfs, w, label="OOS (2025-26)", color="#42a5f5")
    ax.set_xticks(x)
    ax.set_xticklabels(config_names)
    ax.axhline(1.0, color="red", linewidth=0.5, linestyle="--")
    ax.set_ylabel("Profit Factor")
    ax.set_title("(a) IS vs OOS: Filter Configurations")
    ax.legend()
    for i, (ip, op) in enumerate(zip(is_pfs, oos_pfs)):
        ax.text(i - w/2, ip + 0.05, f"{ip:.2f}", ha="center", fontsize=9)
        ax.text(i + w/2, op + 0.05, f"{op:.2f}", ha="center", fontsize=9)

    # (b) Walk-forward yearly
    ax = axes[0, 1]
    wf_years = [r["year"] for r in wf_results]
    wf_hi_pf = [r["hi"]["PF"] for r in wf_results]
    wf_base_pf = [r["base"]["PF"] for r in wf_results]
    x = np.arange(len(wf_years))
    ax.bar(x - w/2, wf_hi_pf, w, label="Night HIGH vol", color="#66bb6a")
    ax.bar(x + w/2, wf_base_pf, w, label="Skip Thu+Fri", color="#ff9800")
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in wf_years])
    ax.axhline(1.0, color="red", linewidth=0.5, linestyle="--")
    ax.set_ylabel("Profit Factor")
    ax.set_title("(b) Walk-Forward: Night HIGH vs Weekday Filter")
    ax.legend()

    # (c) Parameter sensitivity
    ax = axes[1, 0]
    sens_df = pd.DataFrame(sens_results)
    ax.plot(sens_df["threshold"], sens_df["is_pf"], "g-o", markersize=4, label="IS PF")
    ax.plot(sens_df["threshold"], sens_df["oos_pf"], "b-s", markersize=4, label="OOS PF")
    ax.axvline(is_median, color="purple", linewidth=1, linestyle="--", label=f"IS median={is_median:.2f}")
    ax.axhline(1.0, color="red", linewidth=0.5, linestyle="--")
    ax.set_xlabel("Night Norm Threshold")
    ax.set_ylabel("Profit Factor")
    ax.set_title("(c) Threshold Sensitivity")
    ax.legend()

    ax2 = ax.twinx()
    ax2.plot(sens_df["threshold"], sens_df["is_n"], "g--", alpha=0.4, label="IS N")
    ax2.plot(sens_df["threshold"], sens_df["oos_n"], "b--", alpha=0.4, label="OOS N")
    ax2.set_ylabel("# Trades")

    # (d) Cumulative PnL curves for key configs
    ax = axes[1, 1]
    for name, color, ls in [
        ("A: Skip Thu+Fri (baseline)", "#ff9800", "-"),
        ("B: Night HIGH only", "#66bb6a", "-"),
        ("C: Night HIGH + skip Fri", "#2196f3", "-"),
        ("D: Night HIGH + skip TF", "#9c27b0", "--"),
    ]:
        filt = configs[name]
        filtered = merged[filt(merged)].sort_values("EntryTime")
        cum_pnl = filtered["PnL"].cumsum()
        ax.plot(range(len(cum_pnl)), cum_pnl.values, color=color, linestyle=ls,
                label=f"{name.split(':')[0]}: {name.split(':')[1].strip()}")
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Cumulative PnL (pts)")
    ax.set_title("(d) Cumulative PnL by Configuration")
    ax.legend(fontsize=9)
    ax.axhline(0, color="gray", linewidth=0.5)

    plt.tight_layout()
    fig_path = OUT_DIR / "h066_backtest.png"
    plt.savefig(fig_path, dpi=150)
    print(f"\nSaved → {fig_path}")
    plt.close()

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("\nIS vs OOS consistency:")
    for name in configs:
        is_s = is_results[name]
        oos_s = oos_results[name]
        delta = oos_s["PF"] - is_s["PF"]
        print(f"  {name:35s}  IS PF={is_s['PF']:.2f}  OOS PF={oos_s['PF']:.2f}  "
              f"Δ={delta:+.2f}")

    print(f"\nWalk-forward: Night HIGH beat baseline in "
          f"{sum(1 for r in wf_results if r['hi']['PF'] > r['base']['PF'])}"
          f"/{len(wf_results)} years")


if __name__ == "__main__":
    main()
