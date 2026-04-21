#!/usr/bin/env python3
"""H075 Phase 1: NVF Method Upgrade.

對比 4 種 NVF 方法（兩種 norm × 兩種 threshold）對 EstHL/Reversal 的影響：
  - SMA20 + 0.85 fixed (current production)
  - SMA20 + expanding median
  - EMA20 + expanding median (首選, H066 evaluation method)
  - EMA20 + 0.85 fixed

主要評估維度（**連敗結構優先於 PF**）：
  T1  expanding median trajectory（causal）
  T2  aggregate HIGH/LOW PF 對比
  T3  walk-forward 年度一致性
  T4  連敗結構（max/avg consecutive losses, worst streak P&L）
  T5  2026 Q1 高 vol regime 下的行為
  T6  實作可行性

Usage:
    uv run python research/active/H075-nvf-method-upgrade/explore.py
"""

import bisect
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from backtesting import Backtest

from src.backtest.runner import (
    load_data_for_orb_est_hl,
    load_data_for_reversal,
)
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy
from src.strategies.reversal import ReversalStrategy

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H075-nvf-method-upgrade/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)
plt.rcParams["font.size"] = 10

ESTHL_PARAMS = dict(sl_ema_fraction=0.25, adx_min=0.0, long_only=True, vwap_days=2,
                    skip_thursday=False, skip_friday=False)
REVERSAL_PARAMS = dict(vol_ratio=1.2, sl_ema_fraction=0.25, exhaust_fraction=0.5,
                       signal_skip=0, sat_pullback_fraction=0.5)

H066_CONFIRM = "2026-04-17"


# ─────────────────── helpers ───────────────────

def calc(t: pd.DataFrame) -> dict:
    n = len(t)
    if n == 0:
        return {"N": 0, "WR": 0.0, "PF": np.nan, "avg": 0.0, "total": 0.0}
    w = t[t["PnL"] > 0]["PnL"].sum()
    l = abs(t[t["PnL"] <= 0]["PnL"].sum())
    pnl_pct = t["PnL"] / t["EntryPrice"] * 100
    sharpe = pnl_pct.mean() / pnl_pct.std() * np.sqrt(252) if pnl_pct.std() > 0 else 0.0
    return {"N": n, "WR": (t["PnL"] > 0).sum() / n,
            "PF": w / l if l > 0 else float("inf"),
            "avg": t["PnL"].mean(), "total": t["PnL"].sum(), "sharpe": sharpe}


def streak_stats(trades_sorted: pd.DataFrame) -> dict:
    """Streak metrics for an ordered trade series."""
    if len(trades_sorted) == 0:
        return {"max_loss_streak": 0, "avg_loss_streak": 0, "n_streaks": 0,
                "worst_streak_pnl": 0, "max_dd": 0}
    pnls = trades_sorted["PnL"].values
    losses = (pnls <= 0).astype(int)
    streaks, cur = [], 0
    for x in losses:
        if x:
            cur += 1
        else:
            if cur > 0: streaks.append(cur)
            cur = 0
    if cur > 0: streaks.append(cur)

    worst_streak_pnl, cur_pnl = 0, 0
    for p in pnls:
        if p <= 0:
            cur_pnl += p
            worst_streak_pnl = min(worst_streak_pnl, cur_pnl)
        else:
            cur_pnl = 0
    cum = pnls.cumsum()
    max_dd = float((cum - np.maximum.accumulate(cum)).min())
    return {
        "max_loss_streak": max(streaks) if streaks else 0,
        "avg_loss_streak": float(np.mean(streaks)) if streaks else 0,
        "n_streaks": len(streaks),
        "worst_streak_pnl": worst_streak_pnl,
        "max_dd": max_dd,
    }


def run_strategy(name, runner_fn, strategy_cls, params):
    print(f"[{name}] running...")
    df = runner_fn()
    bt = Backtest(df, strategy_cls, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**params)
    trades = stats["_trades"].copy()
    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["trade_date"] = trades["EntryTime"].dt.normalize()
    trades["year"] = trades["EntryTime"].dt.year
    print(f"[{name}] trades: {len(trades)}")
    return trades


def compute_night_metrics() -> pd.DataFrame:
    """night_range, SMA20, EMA20, norm_sma, norm_ema."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        dd = conn.execute("""
            SELECT DISTINCT timestamp::DATE AS d FROM ohlcv_1m WHERE symbol='TX'
              AND timestamp::TIME >= '08:45' AND timestamp::TIME < '13:45'
            ORDER BY d
        """).df()
        ddl = sorted(pd.to_datetime(dd["d"]).tolist())
        nr = conn.execute("""
            SELECT timestamp,high,low FROM ohlcv_1m WHERE symbol='TX'
              AND (timestamp::TIME >= '15:00' OR timestamp::TIME < '05:00')
            ORDER BY timestamp
        """).df()
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
    n["sma20"] = n["night_range"].rolling(20).mean()
    n["ema20"] = n["night_range"].ewm(span=20, adjust=False).mean()
    n["norm_sma"] = n["night_range"] / n["sma20"]
    n["norm_ema"] = n["night_range"] / n["ema20"]
    return n


def add_expanding_medians(night: pd.DataFrame, min_warmup: int = 60) -> pd.DataFrame:
    """Causal expanding median: for date d, use median of values STRICTLY BEFORE d."""
    night = night.sort_index().copy()
    for col in ["norm_sma", "norm_ema"]:
        s = night[col]
        # shift(1): use only past values, not today's value
        night[f"{col}_exp_med"] = s.shift(1).expanding(min_periods=min_warmup).median()
    return night


# ─────────────────── tasks ───────────────────

def task1_trajectory(night: pd.DataFrame):
    print("\n" + "=" * 80)
    print("T1: Expanding median trajectory")
    print("=" * 80)
    print(f"\nLong-term median (full data):")
    print(f"  norm_sma median = {night['norm_sma'].median():.3f}")
    print(f"  norm_ema median = {night['norm_ema'].median():.3f}")

    n = night.dropna(subset=["norm_sma_exp_med"])
    print(f"\nExpanding median (causal, warmup=60 nights, N valid={len(n)}):")
    samples = [pd.Timestamp(d) for d in
               ["2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31",
                "2025-12-31", H066_CONFIRM, "2026-04-21"]]
    print(f"  {'Date':>12}  {'SMA exp_med':>12}  {'EMA exp_med':>12}")
    for d in samples:
        sub = n[n.index <= d]
        if len(sub) > 0:
            row = sub.iloc[-1]
            print(f"  {d.date()}  {row['norm_sma_exp_med']:>12.3f}  {row['norm_ema_exp_med']:>12.3f}")

    # Monthly drift rate
    print(f"\nMonth-over-month median change (last 12 months):")
    monthly = n[["norm_sma_exp_med", "norm_ema_exp_med"]].resample("ME").last().dropna()
    last12 = monthly.iloc[-12:].copy()
    last12["sma_Δ"] = last12["norm_sma_exp_med"].diff()
    last12["ema_Δ"] = last12["norm_ema_exp_med"].diff()
    print(f"  {'Month':>10}  {'SMA':>7}  {'Δ':>8}  {'EMA':>7}  {'Δ':>8}")
    for d, r in last12.iterrows():
        print(f"  {d.strftime('%Y-%m')}  {r['norm_sma_exp_med']:>7.3f}  "
              f"{(r['sma_Δ'] if not np.isnan(r['sma_Δ']) else 0):+8.3f}  "
              f"{r['norm_ema_exp_med']:>7.3f}  "
              f"{(r['ema_Δ'] if not np.isnan(r['ema_Δ']) else 0):+8.3f}")


def merge_night(trades: pd.DataFrame, night: pd.DataFrame) -> pd.DataFrame:
    cols = ["norm_sma", "norm_ema", "norm_sma_exp_med", "norm_ema_exp_med"]
    return trades.merge(night[cols], left_on="trade_date", right_index=True, how="left")


def filter_trades(merged: pd.DataFrame, method: str) -> pd.DataFrame:
    """Apply NVF based on method name."""
    if method == "SMA + 0.85":
        return merged[merged["norm_sma"] >= 0.85]
    if method == "EMA + 0.85":
        return merged[merged["norm_ema"] >= 0.85]
    if method == "SMA + exp_med":
        return merged[merged["norm_sma"] >= merged["norm_sma_exp_med"]]
    if method == "EMA + exp_med":
        return merged[merged["norm_ema"] >= merged["norm_ema_exp_med"]]
    if method == "ALL":
        return merged
    raise ValueError(method)


METHODS = ["SMA + 0.85", "SMA + exp_med", "EMA + exp_med", "EMA + 0.85"]


def task2_aggregate(strats: dict, night: pd.DataFrame):
    print("\n" + "=" * 80)
    print("T2: Aggregate HIGH/LOW PF by method")
    print("=" * 80)
    rows = []
    for sname, trades in strats.items():
        m = merge_night(trades, night).dropna(subset=["norm_sma_exp_med"])
        all_s = calc(m)
        print(f"\n── {sname} ── (with NVF & expanding median valid: N={len(m)})")
        print(f"  ALL baseline: PF={all_s['PF']:.2f} WR={all_s['WR']:.1%} "
              f"avg={all_s['avg']:+.0f} total={all_s['total']:+,.0f}")
        print(f"  {'Method':>20}  {'HIGH N':>6} {'HIGH PF':>7} {'HIGH WR':>7}  "
              f"{'LOW N':>5} {'LOW PF':>6} {'diff%':>6}")
        for method in METHODS:
            hi = filter_trades(m, method)
            lo = m.drop(hi.index)
            sh = calc(hi); sl = calc(lo)
            diff = ((sh["PF"] - sl["PF"]) / sl["PF"] * 100
                    if (np.isfinite(sl["PF"]) and sl["PF"] > 0) else np.nan)
            rows.append({"strategy": sname, "method": method,
                         "hi_N": sh["N"], "hi_PF": sh["PF"], "hi_WR": sh["WR"],
                         "hi_total": sh["total"], "hi_sharpe": sh["sharpe"],
                         "lo_N": sl["N"], "lo_PF": sl["PF"], "diff_pct": diff})
            pf_h = f"{sh['PF']:.2f}" if np.isfinite(sh["PF"]) else "—"
            pf_l = f"{sl['PF']:.2f}" if np.isfinite(sl["PF"]) else "—"
            d_str = f"{diff:+.1f}" if not np.isnan(diff) else "—"
            print(f"  {method:>20}  {sh['N']:>6} {pf_h:>7} {sh['WR']:>7.1%}  "
                  f"{sl['N']:>5} {pf_l:>6} {d_str:>6}")
    return pd.DataFrame(rows)


def task3_walk_forward(strats: dict, night: pd.DataFrame):
    print("\n" + "=" * 80)
    print("T3: Walk-forward 年度 PF (HIGH 組 only)")
    print("=" * 80)
    rows = []
    for sname, trades in strats.items():
        m = merge_night(trades, night).dropna(subset=["norm_sma_exp_med"])
        years = sorted(m["year"].unique())
        print(f"\n── {sname} ──")
        print(f"  {'Year':>6}  " + "  ".join(f"{mtd:>15}" for mtd in METHODS))
        win_count = {mtd: 0 for mtd in METHODS}
        for y in years:
            sy = m[m["year"] == y]
            cells = []
            base_pf = calc(sy)["PF"]
            for method in METHODS:
                hi = filter_trades(sy, method)
                s = calc(hi)
                rows.append({"strategy": sname, "year": y, "method": method,
                             "N": s["N"], "PF": s["PF"], "total": s["total"]})
                if s["N"] >= 5 and np.isfinite(s["PF"]) and np.isfinite(base_pf) and s["PF"] > base_pf:
                    win_count[method] += 1
                pf_str = f"{s['PF']:.2f}({s['N']:>2})" if s["N"] > 0 else "—"
                cells.append(f"{pf_str:>15}")
            print(f"  {y:>6}  " + "  ".join(cells))
        print(f"  Years HIGH PF > baseline (N≥5):")
        for method in METHODS:
            print(f"    {method:>20}: {win_count[method]} / {len(years)}")
    return pd.DataFrame(rows)


def task4_streaks(strats: dict, night: pd.DataFrame):
    print("\n" + "=" * 80)
    print("T4: 連敗結構（最高優先 — 升級不能讓 max streak 增加 ≥ 2 筆）")
    print("=" * 80)
    rows = []
    for sname, trades in strats.items():
        m = merge_night(trades, night).dropna(subset=["norm_sma_exp_med"])
        m = m.sort_values("EntryTime").reset_index(drop=True)
        print(f"\n── {sname} ──")
        print(f"  {'Method':>20}  {'N':>4}  {'max_streak':>10}  {'avg_streak':>10}  "
              f"{'worst_pnl':>10}  {'max_dd':>8}  {'total':>8}")
        # baseline (no NVF)
        all_s = streak_stats(m)
        print(f"  {'NO_NVF (baseline)':>20}  {len(m):>4}  {all_s['max_loss_streak']:>10}  "
              f"{all_s['avg_loss_streak']:>10.2f}  {all_s['worst_streak_pnl']:>10,.0f}  "
              f"{all_s['max_dd']:>8,.0f}  {m['PnL'].sum():>+8,.0f}")
        rows.append({"strategy": sname, "method": "NO_NVF",
                     "N": len(m), **all_s, "total": m["PnL"].sum()})
        for method in METHODS:
            hi = filter_trades(m, method).sort_values("EntryTime").reset_index(drop=True)
            ss = streak_stats(hi)
            rows.append({"strategy": sname, "method": method,
                         "N": len(hi), **ss, "total": hi["PnL"].sum()})
            print(f"  {method:>20}  {len(hi):>4}  {ss['max_loss_streak']:>10}  "
                  f"{ss['avg_loss_streak']:>10.2f}  {ss['worst_streak_pnl']:>10,.0f}  "
                  f"{ss['max_dd']:>8,.0f}  {hi['PnL'].sum():>+8,.0f}")
    return pd.DataFrame(rows)


def task5_q1_2026(strats: dict, night: pd.DataFrame):
    print("\n" + "=" * 80)
    print("T5: 2026 Q1+Q2 高 vol regime 下 4 方法行為")
    print("=" * 80)
    rows = []
    for sname, trades in strats.items():
        m = merge_night(trades, night).dropna(subset=["norm_sma_exp_med"])
        q1 = m[m["EntryTime"] >= "2026-01-01"]
        print(f"\n── {sname} (2026 Q1+Q2 trades, N={len(q1)}) ──")
        print(f"  {'Method':>20}  {'pass_N':>6} {'pass_rate':>9}  {'PF':>5}  {'WR':>6}  {'avg':>6}  {'total':>8}")
        base = calc(q1)
        print(f"  {'ALL (no filter)':>20}  {base['N']:>6} {1.0:>9.1%}  "
              f"{base['PF']:>5.2f}  {base['WR']:>6.1%}  {base['avg']:>+6.0f}  {base['total']:>+8,.0f}")
        for method in METHODS:
            hi = filter_trades(q1, method)
            s = calc(hi)
            rate = s["N"] / len(q1) if len(q1) > 0 else 0
            rows.append({"strategy": sname, "method": method, "period": "2026Q1+",
                         "pass_N": s["N"], "pass_rate": rate, **s})
            pf_str = f"{s['PF']:.2f}" if np.isfinite(s["PF"]) else "—"
            print(f"  {method:>20}  {s['N']:>6} {rate:>9.1%}  {pf_str:>5}  "
                  f"{s['WR']:>6.1%}  {s['avg']:>+6.0f}  {s['total']:>+8,.0f}")
    return pd.DataFrame(rows)


def task6_implementability(night: pd.DataFrame):
    print("\n" + "=" * 80)
    print("T6: 實作可行性")
    print("=" * 80)
    n = night.dropna(subset=["norm_sma_exp_med"])
    print(f"""
  Expanding median 計算需求：
    - 歷史 night_norm 資料：{len(night)} 個夜盤資料點
    - 每天計算量：median of N values（很輕，<1ms）
    - warmup 期：60 個夜盤值（約 3 個月），目前 {len(n)} 個有效計算日

  生產實作方式（建議）：
    在 src/analysis/key_prices.py:_compute_night_vol_filter 內：
      1. 從 DuckDB 讀取所有歷史 night_range
      2. 計算 EMA20 序列
      3. 計算 norm_ema 序列
      4. expanding_median = norm_ema.shift(1).expanding(60).median().iloc[-1]
      5. tonight_norm_ema = tonight_range / EMA20[-1]
      6. pass = tonight_norm_ema >= expanding_median

  風險：
    - warmup 期內無 median 可用：若無 60 夜盤資料則 fallback 到 fixed 0.93
    - DuckDB 讀取量增加：每次都要全歷史 → 可 cache 在 morning_briefing 起算時計算
    - 與 H066 實際使用方法一致，無 untested 風險
""")
    print(f"  目前 EMA exp_med（最後一天）= {n['norm_ema_exp_med'].iloc[-1]:.3f}")
    print(f"  目前 SMA exp_med（最後一天）= {n['norm_sma_exp_med'].iloc[-1]:.3f}")


# ─────────────────── plotting ───────────────────

def plot_trajectory(night: pd.DataFrame):
    n = night.dropna(subset=["norm_sma_exp_med"])
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(n.index, n["norm_sma_exp_med"], label="SMA expanding median", color="#1f77b4")
    ax.plot(n.index, n["norm_ema_exp_med"], label="EMA expanding median", color="#ff7f0e")
    ax.axhline(0.85, color="gray", linewidth=1, linestyle="--", label="prod fixed 0.85")
    ax.axvline(pd.Timestamp(H066_CONFIRM), color="red", linewidth=1, linestyle=":",
               label="H066 confirm 2026-04-17")
    ax.set_ylabel("Threshold value")
    ax.set_title("H075 (T1): Expanding median trajectory (causal, warmup=60)")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    p = OUT_DIR / "h075_t1_trajectory.png"
    plt.savefig(p, dpi=150, bbox_inches="tight"); plt.close()
    print(f"\nSaved → {p}")


def plot_walk_forward(df: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(16, 5))
    fig.suptitle("H075 (T3): Walk-forward HIGH PF by method", fontsize=12)
    for ax, sname in zip(axes, ["EstHL", "Reversal"]):
        sub = df[df["strategy"] == sname]
        years = sorted(sub["year"].unique())
        x = np.arange(len(years))
        w = 0.2
        for i, method in enumerate(METHODS):
            ms = sub[sub["method"] == method].sort_values("year")
            pfs = ms["PF"].clip(upper=10).values  # cap for plot readability
            ax.bar(x + (i - 1.5) * w, pfs, w, label=method)
        ax.set_xticks(x); ax.set_xticklabels(years)
        ax.axhline(1.0, color="red", linewidth=0.5, linestyle="--")
        ax.set_ylabel("HIGH PF (clipped at 10)")
        ax.set_title(sname)
        ax.legend(fontsize=8)
    plt.tight_layout()
    p = OUT_DIR / "h075_t3_walkforward.png"
    plt.savefig(p, dpi=150, bbox_inches="tight"); plt.close()
    print(f"Saved → {p}")


def plot_streaks(df: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("H075 (T4): Streak structure by method (lower max_streak = better protection)",
                 fontsize=12)
    methods_with_baseline = ["NO_NVF"] + METHODS
    for ax, sname in zip(axes, ["EstHL", "Reversal"]):
        sub = df[df["strategy"] == sname]
        sub = sub.set_index("method").reindex(methods_with_baseline).reset_index()
        x = np.arange(len(methods_with_baseline))
        w = 0.35
        ax.bar(x - w/2, sub["max_loss_streak"].values, w, label="max streak", color="#d62728")
        ax.bar(x + w/2, sub["avg_loss_streak"].values, w, label="avg streak", color="#ff9896")
        ax.set_xticks(x)
        ax.set_xticklabels(methods_with_baseline, rotation=15, ha="right", fontsize=9)
        ax.set_ylabel("Consecutive losses")
        ax.set_title(sname)
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, axis="y")
    plt.tight_layout()
    p = OUT_DIR / "h075_t4_streaks.png"
    plt.savefig(p, dpi=150, bbox_inches="tight"); plt.close()
    print(f"Saved → {p}")


# ─────────────────── main ───────────────────

def main():
    print("=" * 80)
    print("H075: NVF Method Upgrade — Phase 1")
    print("=" * 80)

    print("\nComputing night metrics + expanding medians (causal)...")
    night = compute_night_metrics()
    night = add_expanding_medians(night, min_warmup=60)
    print(f"  night days: {len(night)}, with expanding median valid: "
          f"{night['norm_sma_exp_med'].notna().sum()}")

    strats = {}
    strats["EstHL"] = run_strategy("EstHL", load_data_for_orb_est_hl,
                                   ORBWithEstHLExitStrategy, ESTHL_PARAMS)
    strats["Reversal"] = run_strategy("Reversal", load_data_for_reversal,
                                      ReversalStrategy, REVERSAL_PARAMS)

    task1_trajectory(night)
    plot_trajectory(night)

    df_t2 = task2_aggregate(strats, night)
    df_t2.to_csv(OUT_DIR / "t2_aggregate.csv", index=False)

    df_t3 = task3_walk_forward(strats, night)
    df_t3.to_csv(OUT_DIR / "t3_walkforward.csv", index=False)
    plot_walk_forward(df_t3)

    df_t4 = task4_streaks(strats, night)
    df_t4.to_csv(OUT_DIR / "t4_streaks.csv", index=False)
    plot_streaks(df_t4)

    df_t5 = task5_q1_2026(strats, night)
    df_t5.to_csv(OUT_DIR / "t5_q1_2026.csv", index=False)

    task6_implementability(night)

    # Save night data
    night.to_csv(OUT_DIR / "night_metrics.csv")

    print("\nDone.")


if __name__ == "__main__":
    main()
