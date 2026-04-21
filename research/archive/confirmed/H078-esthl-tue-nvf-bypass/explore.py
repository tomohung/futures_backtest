#!/usr/bin/env python3
"""H078 Phase 1: EstHL Tue NVF Bypass — 快速 confirmation。

T1  Tue baseline vs Tue NVF (新方法 EMA + expanding median) 逐年
T2  Walk-forward 一致性
T3  連敗結構：current (full NVF) vs Tue-bypass

Usage:
    uv run python research/active/H078-esthl-tue-nvf-bypass/explore.py
"""

import bisect
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from backtesting import Backtest

from src.backtest.runner import load_data_for_orb_est_hl
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H078-esthl-tue-nvf-bypass/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)
plt.rcParams["font.size"] = 10

# 解除 weekday filter 以取得完整 Tue 樣本
ESTHL_PARAMS = dict(sl_ema_fraction=0.25, adx_min=0.0, long_only=True, vwap_days=2,
                    skip_thursday=False, skip_friday=False)
TUE = 1
WD = ["Mon", "Tue", "Wed", "Thu", "Fri"]


def calc(t):
    n = len(t)
    if n == 0:
        return {"N": 0, "WR": 0, "PF": np.nan, "avg": 0, "total": 0}
    w = t[t["PnL"] > 0]["PnL"].sum()
    l = abs(t[t["PnL"] <= 0]["PnL"].sum())
    pnl_pct = t["PnL"] / t["EntryPrice"] * 100
    sharpe = pnl_pct.mean() / pnl_pct.std() * np.sqrt(252) if pnl_pct.std() > 0 else 0
    return {"N": n, "WR": (t["PnL"] > 0).sum() / n,
            "PF": w / l if l > 0 else float("inf"),
            "avg": t["PnL"].mean(), "total": t["PnL"].sum(), "sharpe": sharpe}


def streak_stats(t_sorted):
    if len(t_sorted) == 0:
        return {"max_streak": 0, "avg_streak": 0, "worst_pnl": 0, "max_dd": 0}
    pnls = t_sorted["PnL"].values
    losses = (pnls <= 0).astype(int)
    streaks, cur = [], 0
    for x in losses:
        if x:
            cur += 1
        else:
            if cur > 0: streaks.append(cur)
            cur = 0
    if cur > 0: streaks.append(cur)
    worst, c = 0, 0
    for p in pnls:
        if p <= 0:
            c += p; worst = min(worst, c)
        else:
            c = 0
    cum = pnls.cumsum()
    max_dd = float((cum - np.maximum.accumulate(cum)).min())
    return {"max_streak": max(streaks) if streaks else 0,
            "avg_streak": float(np.mean(streaks)) if streaks else 0,
            "worst_pnl": worst, "max_dd": max_dd}


def compute_night():
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        dd = conn.execute("""SELECT DISTINCT timestamp::DATE AS d FROM ohlcv_1m
                             WHERE symbol='TX' AND timestamp::TIME >= '08:45'
                               AND timestamp::TIME < '13:45' ORDER BY d""").df()
        ddl = sorted(pd.to_datetime(dd["d"]).tolist())
        nr = conn.execute("""SELECT timestamp,high,low FROM ohlcv_1m WHERE symbol='TX'
                             AND (timestamp::TIME >= '15:00' OR timestamp::TIME < '05:00')
                             ORDER BY timestamp""").df()
    nr["timestamp"] = pd.to_datetime(nr["timestamp"])
    def fnxt(ts):
        t = ts.time()
        sd = (ts + pd.Timedelta(days=1)).normalize() if t >= pd.Timestamp("15:00").time() \
             else ts.normalize()
        i = bisect.bisect_left(ddl, sd)
        return ddl[i] if i < len(ddl) else None
    nr["trade_date"] = nr["timestamp"].apply(fnxt)
    nr = nr.dropna(subset=["trade_date"])
    n = nr.groupby("trade_date").agg(nh=("high", "max"), nl=("low", "min"),
                                      nb=("high", "count"))
    n["night_range"] = n["nh"] - n["nl"]
    n = n[n["nb"] >= 100].copy()
    n["ema20"] = n["night_range"].ewm(span=20, adjust=False).mean()
    n["norm_ema"] = n["night_range"] / n["ema20"]
    # causal expanding median (shift 1 to avoid look-ahead)
    n["exp_med"] = n["norm_ema"].shift(1).expanding(60).median()
    return n


def main():
    print("=" * 78)
    print("H078: EstHL Tue NVF Bypass — Phase 1")
    print("=" * 78)

    print("\nLoading + running EstHL (no weekday filter)...")
    df = load_data_for_orb_est_hl()
    bt = Backtest(df, ORBWithEstHLExitStrategy, cash=200_000, commission=0.0,
                  trade_on_close=True)
    stats = bt.run(**ESTHL_PARAMS)
    trades = stats["_trades"].copy()
    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["trade_date"] = trades["EntryTime"].dt.normalize()
    trades["weekday"] = trades["EntryTime"].dt.dayofweek
    trades["year"] = trades["EntryTime"].dt.year
    print(f"Total trades: {len(trades)}")

    print("Computing night metrics + EMA expanding median...")
    night = compute_night()
    m = trades.merge(night[["norm_ema", "exp_med"]], left_on="trade_date",
                     right_index=True, how="left").dropna(subset=["exp_med"])
    m["nvf_pass"] = m["norm_ema"] >= m["exp_med"]
    print(f"With NVF & exp_med valid: {len(m)}")

    # ── T1: Tue baseline vs Tue NVF 逐年 ──
    print("\n" + "=" * 78)
    print("T1: EstHL Tue cell — baseline vs new NVF, by year")
    print("=" * 78)
    tue = m[m["weekday"] == TUE]
    print(f"\nTotal Tue trades (with NVF valid): {len(tue)}")
    print(f"  {'Year':>4}  {'base_N':>6} {'base_PF':>7} {'base_avg':>8}  "
          f"{'NVF_N':>5} {'NVF_PF':>6} {'NVF_avg':>7}  {'Δ_PF':>7}")
    rows = []
    base_wins = 0
    n_years = 0
    for y in sorted(tue["year"].unique()):
        sub = tue[tue["year"] == y]
        nvf_sub = sub[sub["nvf_pass"]]
        b = calc(sub); n = calc(nvf_sub)
        if b["N"] >= 5:
            n_years += 1
            if (np.isfinite(b["PF"]) and np.isfinite(n["PF"]) and b["PF"] > n["PF"]) \
               or (n["N"] == 0 and b["PF"] > 0):
                base_wins += 1
        diff = n["PF"] - b["PF"] if np.isfinite(n["PF"]) and np.isfinite(b["PF"]) else np.nan
        rows.append({"year": y, "base_N": b["N"], "base_PF": b["PF"], "base_avg": b["avg"],
                     "nvf_N": n["N"], "nvf_PF": n["PF"], "nvf_avg": n["avg"], "delta": diff})
        nvf_pf_str = f"{n['PF']:.2f}" if np.isfinite(n["PF"]) else "—"
        d_str = f"{diff:+.2f}" if not np.isnan(diff) else "—"
        print(f"  {y:>4}  {b['N']:>6} {b['PF']:>7.2f} {b['avg']:>+8.0f}  "
              f"{n['N']:>5} {nvf_pf_str:>6} {n['avg']:>+7.0f}  {d_str:>7}")
    print(f"\n  Years with N≥5: {n_years}, baseline > NVF: {base_wins}/{n_years}")

    # IS / OOS
    is_tue = tue[tue["trade_date"] <= "2023-12-31"]
    oos_tue = tue[tue["trade_date"] >= "2024-01-01"]
    print("\n  IS (2021-23) vs OOS (2024-26):")
    for label, sub in [("IS", is_tue), ("OOS", oos_tue)]:
        b = calc(sub); n = calc(sub[sub["nvf_pass"]])
        d = n["PF"] - b["PF"] if np.isfinite(n["PF"]) and np.isfinite(b["PF"]) else np.nan
        print(f"  {label}: base PF={b['PF']:.2f}(N={b['N']})  "
              f"NVF PF={n['PF']:.2f}(N={n['N']})  Δ={d:+.2f}")

    pd.DataFrame(rows).to_csv(OUT_DIR / "t1_tue_yearly.csv", index=False)

    # ── T2: Walk-forward consistency (already in T1's table essentially) ──
    print("\n" + "=" * 78)
    print("T2: Walk-forward consistency 視覺化")
    print("=" * 78)

    # ── T3: Streak comparison: Config A (full NVF) vs Config B (Tue bypass NVF) ──
    print("\n" + "=" * 78)
    print("T3: 連敗結構 — Config A (full NVF) vs Config B (Tue bypass)")
    print("=" * 78)
    # m has all trades (no weekday filter). Apply current production weekday skip
    # to fairly simulate live behavior: skip Thu(3) + Fri(4).
    live_eligible = m[~m["weekday"].isin([3, 4])]
    print(f"\nLive-eligible (Mon-Wed): {len(live_eligible)}")

    # Config A: full NVF (current)
    cfg_a = live_eligible[live_eligible["nvf_pass"]].sort_values("EntryTime")
    # Config B: NVF except Tue (Tue bypass)
    is_tue_mask = live_eligible["weekday"] == TUE
    cfg_b = live_eligible[is_tue_mask | live_eligible["nvf_pass"]].sort_values("EntryTime")

    sa = streak_stats(cfg_a); sb = streak_stats(cfg_b)
    ca = calc(cfg_a); cb = calc(cfg_b)
    print(f"  {'Config':>30}  {'N':>4}  {'PF':>5}  {'WR':>6}  {'total':>8}  "
          f"{'max_streak':>10} {'worst_pnl':>9} {'max_dd':>8}")
    print(f"  {'A: full NVF (current)':>30}  {ca['N']:>4}  {ca['PF']:>5.2f}  "
          f"{ca['WR']:>6.1%}  {ca['total']:>+8,.0f}  "
          f"{sa['max_streak']:>10}  {sa['worst_pnl']:>+9,.0f}  {sa['max_dd']:>+8,.0f}")
    print(f"  {'B: Tue bypass + NVF Mon/Wed':>30}  {cb['N']:>4}  {cb['PF']:>5.2f}  "
          f"{cb['WR']:>6.1%}  {cb['total']:>+8,.0f}  "
          f"{sb['max_streak']:>10}  {sb['worst_pnl']:>+9,.0f}  {sb['max_dd']:>+8,.0f}")
    delta_total = cb["total"] - ca["total"]
    delta_streak = sb["max_streak"] - sa["max_streak"]
    print(f"\n  Δ total = {delta_total:+,.0f}  Δ max_streak = {delta_streak:+d}")

    # By year breakdown
    print("\n  By year (live-eligible only):")
    print(f"  {'Year':>4}  {'A_N':>4} {'A_PF':>5} {'A_total':>8}  "
          f"{'B_N':>4} {'B_PF':>5} {'B_total':>8}  {'Δ_total':>8}")
    yrs = sorted(live_eligible["year"].unique())
    for y in yrs:
        ya = cfg_a[cfg_a["year"] == y]; yb = cfg_b[cfg_b["year"] == y]
        ca_y = calc(ya); cb_y = calc(yb)
        d = cb_y["total"] - ca_y["total"]
        a_pf = f"{ca_y['PF']:.2f}" if np.isfinite(ca_y["PF"]) else "—"
        b_pf = f"{cb_y['PF']:.2f}" if np.isfinite(cb_y["PF"]) else "—"
        print(f"  {y:>4}  {ca_y['N']:>4} {a_pf:>5} {ca_y['total']:>+8,.0f}  "
              f"{cb_y['N']:>4} {b_pf:>5} {cb_y['total']:>+8,.0f}  {d:>+8,.0f}")

    # ── Plots ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("H078: EstHL Tue NVF Bypass", fontsize=12)
    df_t1 = pd.DataFrame(rows)
    ax = axes[0]
    yrs_list = df_t1["year"].astype(str).tolist()
    x = np.arange(len(yrs_list)); w = 0.4
    ax.bar(x - w/2, df_t1["base_PF"].clip(upper=10).values, w, label="Tue baseline (no NVF)", color="#66bb6a")
    ax.bar(x + w/2, df_t1["nvf_PF"].clip(upper=10).values, w, label="Tue NVF-filtered", color="#ef5350")
    ax.set_xticks(x); ax.set_xticklabels(yrs_list)
    ax.axhline(1.0, color="black", linewidth=0.5, linestyle="--")
    ax.set_ylabel("Tue PF (clipped at 10)")
    ax.set_title("(a) EstHL Tue: baseline vs NVF-filtered, by year")
    ax.legend(fontsize=9)

    ax = axes[1]
    yrs_b = sorted(live_eligible["year"].unique())
    diffs = []
    for y in yrs_b:
        ya = cfg_a[cfg_a["year"] == y]; yb = cfg_b[cfg_b["year"] == y]
        diffs.append(calc(yb)["total"] - calc(ya)["total"])
    colors = ["#66bb6a" if d > 0 else "#ef5350" for d in diffs]
    ax.bar(range(len(yrs_b)), diffs, color=colors)
    ax.set_xticks(range(len(yrs_b))); ax.set_xticklabels([str(y) for y in yrs_b])
    ax.axhline(0, color="black", linewidth=0.5, linestyle="--")
    ax.set_ylabel("Δ total P&L (B - A)")
    ax.set_title("(b) Tue bypass benefit by year")

    plt.tight_layout()
    p = OUT_DIR / "h078_overview.png"
    plt.savefig(p, dpi=150, bbox_inches="tight"); plt.close()
    print(f"\nSaved → {p}")
    print("\nDone.")


if __name__ == "__main__":
    main()
