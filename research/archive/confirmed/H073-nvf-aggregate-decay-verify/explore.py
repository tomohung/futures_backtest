#!/usr/bin/env python3
"""H073 Phase 1: NVF Aggregate Signal Decay Verification.

驗證 H072 觀察到的「NVF aggregate 訊號 4 天衰減 4×」是否為方法學差異。

關鍵差異（根據 explore.py grep）：
  H066 (EstHL): night_range / **EMA20**, threshold = **median**
  H067 (Reversal): night_range / **SMA20**, threshold = **median**
  H072: night_range / SMA20, threshold = **0.85 fixed**  ← 與 H066 不同方法

Tasks:
  T1  H072 setup 重現（sanity check）
  T2  Median split 方法重做（兩種 norm 都試）
  T3  cutoff 2026-04-17（H066/H067 confirm 日）
  T4  Expanding window: 每週 cutoff
  T5  Algorithm cross-check 表

Usage:
    uv run python research/active/H073-nvf-aggregate-decay-verify/explore.py
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
    load_data_for_exhaustion,
)
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy
from src.strategies.reversal import ReversalStrategy
from src.strategies.exhaustion import ExhaustionStrategy

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H073-nvf-aggregate-decay-verify/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

H066_CONFIRM_DATE = "2026-04-17"

ESTHL_PARAMS = dict(sl_ema_fraction=0.25, adx_min=0.0, long_only=True, vwap_days=2,
                    skip_thursday=False, skip_friday=False)
REVERSAL_PARAMS = dict(vol_ratio=1.2, sl_ema_fraction=0.25, exhaust_fraction=0.5,
                       signal_skip=0, sat_pullback_fraction=0.5)
EXHAUSTION_PARAMS = dict(skip_wed=False, skip_thu=False)


# ─────────────────────────── helpers ───────────────────────────

def calc(t: pd.DataFrame) -> dict:
    n = len(t)
    if n == 0:
        return {"N": 0, "WR": 0.0, "PF": np.nan, "avg": 0.0}
    w = t[t["PnL"] > 0]["PnL"].sum()
    l = abs(t[t["PnL"] <= 0]["PnL"].sum())
    return {"N": n, "WR": (t["PnL"] > 0).sum() / n,
            "PF": w / l if l > 0 else float("inf"),
            "avg": t["PnL"].mean()}


def run_strategy(name, runner_fn, strategy_cls, params):
    print(f"[{name}] running...")
    df = runner_fn()
    bt = Backtest(df, strategy_cls, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**params)
    trades = stats["_trades"].copy()
    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["trade_date"] = trades["EntryTime"].dt.normalize()
    return trades


def compute_night_metrics() -> pd.DataFrame:
    """計算夜盤 H/L、SMA20、EMA20 兩種 norm。"""
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

    night = nr.groupby("trade_date").agg(
        nh=("high", "max"), nl=("low", "min"), nb=("high", "count")
    )
    night["night_range"] = night["nh"] - night["nl"]
    night = night[night["nb"] >= 100].copy()
    night["sma20"] = night["night_range"].rolling(20).mean()
    night["ema20"] = night["night_range"].ewm(span=20, adjust=False).mean()
    night["norm_sma"] = night["night_range"] / night["sma20"]
    night["norm_ema"] = night["night_range"] / night["ema20"]
    return night


def aggregate_diff(trades: pd.DataFrame, night: pd.DataFrame, *,
                   norm_col: str, threshold) -> dict:
    """
    threshold: float (固定) or 'median'
    norm_col: 'norm_sma' or 'norm_ema'
    回傳 HIGH/LOW PF + diff%
    """
    m = trades.merge(night[[norm_col]], left_on="trade_date",
                     right_index=True, how="inner")
    m = m.dropna(subset=[norm_col])
    if isinstance(threshold, str) and threshold == "median":
        thr = m[norm_col].median()
    else:
        thr = float(threshold)
    hi = calc(m[m[norm_col] >= thr])
    lo = calc(m[m[norm_col] < thr])
    if not (np.isfinite(lo["PF"]) and lo["PF"] > 0):
        diff = np.nan
    else:
        diff = (hi["PF"] - lo["PF"]) / lo["PF"] * 100
    return {"thr": thr, "hi_N": hi["N"], "hi_PF": hi["PF"], "hi_WR": hi["WR"],
            "lo_N": lo["N"], "lo_PF": lo["PF"], "lo_WR": lo["WR"],
            "diff_pct": diff, "total_N": len(m)}


def fmt_row(label, r):
    pf_h = f"{r['hi_PF']:.2f}" if np.isfinite(r['hi_PF']) else "—"
    pf_l = f"{r['lo_PF']:.2f}" if np.isfinite(r['lo_PF']) else "—"
    diff = f"{r['diff_pct']:+.1f}%" if not np.isnan(r['diff_pct']) else "—"
    return (f"  {label:<35}  thr={r['thr']:.3f}  "
            f"HIGH N={r['hi_N']:>3} PF={pf_h:>5}  "
            f"LOW N={r['lo_N']:>3} PF={pf_l:>5}  diff={diff:>8}")


# ─────────────────────────── tasks ────────────────────────────

def task1_t2_baseline_replicate(strats: dict, night: pd.DataFrame):
    """T1+T2: 重現 H072 + 用 median split 兩種 norm"""
    print("\n" + "=" * 80)
    print("T1+T2: Aggregate diff — 4 個方法組合（每策略 4 行）")
    print("=" * 80)
    print("  (norm × threshold) → HIGH/LOW PF + diff%")
    h066_h067_target = {
        "EstHL": "H066 reported diff = +83.6% (EMA + median)",
        "Reversal": "H067 reported diff = +64.3% (SMA + median)",
        "Exhaustion": "(no published baseline)",
    }
    rows = []
    for name, trades in strats.items():
        print(f"\n── {name} ──   {h066_h067_target[name]}")
        combos = [
            ("SMA, fixed 0.85 (H072 method)", "norm_sma", 0.85),
            ("SMA, median split (H067 method)", "norm_sma", "median"),
            ("EMA, fixed 0.85", "norm_ema", 0.85),
            ("EMA, median split (H066 method)", "norm_ema", "median"),
        ]
        for lbl, col, thr in combos:
            r = aggregate_diff(trades, night, norm_col=col, threshold=thr)
            print(fmt_row(lbl, r))
            rows.append({"strategy": name, "method": lbl, **r})
    return pd.DataFrame(rows)


def task3_cutoff_2026_04_17(strats: dict, night: pd.DataFrame):
    """T3: 限制資料截至 2026-04-17 重做"""
    print("\n" + "=" * 80)
    print(f"T3: Cutoff at {H066_CONFIRM_DATE} (H066/H067 confirm 日)")
    print("=" * 80)
    cutoff = pd.Timestamp(H066_CONFIRM_DATE)
    rows = []
    for name, trades in strats.items():
        sub_trades = trades[trades["trade_date"] <= cutoff]
        sub_night = night[night.index <= cutoff]
        print(f"\n── {name}  (trades={len(sub_trades)} of {len(trades)}) ──")
        combos = [
            ("SMA, fixed 0.85", "norm_sma", 0.85),
            ("SMA, median (H067 method)", "norm_sma", "median"),
            ("EMA, median (H066 method)", "norm_ema", "median"),
        ]
        for lbl, col, thr in combos:
            r = aggregate_diff(sub_trades, sub_night, norm_col=col, threshold=thr)
            print(fmt_row(lbl, r))
            rows.append({"strategy": name, "method": lbl, **r})
    return pd.DataFrame(rows)


def task4_expanding_window(strats: dict, night: pd.DataFrame):
    """T4: 每週 cutoff，看 aggregate diff 隨時間變化"""
    print("\n" + "=" * 80)
    print("T4: Expanding window (每週 cutoff)")
    print("=" * 80)
    # Range: from 2025-12-01 (5 months before H066) to 2026-04-21
    cutoffs = pd.date_range("2025-12-01", "2026-04-21", freq="W-MON")
    print(f"  Windows: {len(cutoffs)}  ({cutoffs[0].date()} → {cutoffs[-1].date()})")

    rows = []
    methods = [
        ("SMA, fixed 0.85", "norm_sma", 0.85),
        ("SMA, median", "norm_sma", "median"),
        ("EMA, median (H066)", "norm_ema", "median"),
    ]
    for name, trades in strats.items():
        print(f"\n── {name} ──")
        print("  cutoff      " + "  ".join(f"{m[0][:18]:>20}" for m in methods))
        for c in cutoffs:
            sub_trades = trades[trades["trade_date"] <= c]
            sub_night = night[night.index <= c]
            cells = []
            for lbl, col, thr in methods:
                r = aggregate_diff(sub_trades, sub_night, norm_col=col, threshold=thr)
                cells.append(f"{r['diff_pct']:>+7.1f}% (N={r['total_N']:>3})")
                rows.append({
                    "strategy": name, "cutoff": c.date(), "method": lbl,
                    "diff_pct": r["diff_pct"], "total_N": r["total_N"],
                    "hi_PF": r["hi_PF"], "lo_PF": r["lo_PF"], "thr": r["thr"],
                })
            print(f"  {c.date()}  " + "  ".join(f"{cell:>20}" for cell in cells))
    return pd.DataFrame(rows)


def task5_algo_diff_summary():
    """T5: print algorithm comparison."""
    print("\n" + "=" * 80)
    print("T5: 演算法差異總表")
    print("=" * 80)
    print("""
  項目                         H066 explore.py     H067 explore.py     H072 explore.py
  ───────────────────────────  ─────────────────   ─────────────────   ─────────────────
  Norm 分母                    EMA(20)             SMA(20)             SMA(20)
  Threshold 方法                median split        median split        固定 0.85
  夜盤 trade_date 對齊邏輯       下一日盤日          下一日盤日          下一日盤日
  夜盤 bar 數最低門檻             100                100                100
  weekday filter                解除（同 H072）       解除                 解除

  關鍵差異（H066 vs H072）：
    1. EMA vs SMA：EMA 對近期波動更敏感
    2. median 隨資料變化、固定 0.85 不變
    3. EstHL 在 H072 同時換了兩個維度（EMA→SMA, median→0.85）

  H067 vs H072：
    只差 threshold 方法（median vs 0.85）
""")


def plot_expanding(df: pd.DataFrame):
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle("H073 (T4): Aggregate diff by cutoff date", fontsize=13)
    for ax, strat in zip(axes, ["EstHL", "Reversal", "Exhaustion"]):
        sub = df[df["strategy"] == strat]
        for method in sub["method"].unique():
            mm = sub[sub["method"] == method].sort_values("cutoff")
            ax.plot(mm["cutoff"], mm["diff_pct"], marker="o", label=method)
        ax.axhline(0, color="black", linewidth=0.7, linestyle="--")
        ax.axvline(pd.Timestamp(H066_CONFIRM_DATE), color="red", linewidth=1,
                   linestyle="--", alpha=0.5, label="H066/H067 confirm")
        ax.set_title(strat); ax.set_ylabel("HIGH/LOW PF diff%")
        ax.legend(fontsize=8); ax.grid(alpha=0.3)
        ax.tick_params(axis="x", rotation=45)
    plt.tight_layout()
    p = OUT_DIR / "h073_t4_expanding.png"
    plt.savefig(p, dpi=150, bbox_inches="tight"); plt.close()
    print(f"\nSaved → {p}")


# ─────────────────────────── main ────────────────────────────

def main():
    print("=" * 80)
    print("H073: NVF Aggregate Signal Decay Verification — Phase 1")
    print("=" * 80)
    strats = {}
    strats["EstHL"]      = run_strategy("EstHL", load_data_for_orb_est_hl,
                                        ORBWithEstHLExitStrategy, ESTHL_PARAMS)
    strats["Reversal"]   = run_strategy("Reversal", load_data_for_reversal,
                                        ReversalStrategy, REVERSAL_PARAMS)
    strats["Exhaustion"] = run_strategy("Exhaustion", load_data_for_exhaustion,
                                        ExhaustionStrategy, EXHAUSTION_PARAMS)

    print("\nComputing night metrics (SMA20 + EMA20)...")
    night = compute_night_metrics()
    print(f"  night days: {len(night)}")
    print(f"  norm_sma  median = {night['norm_sma'].median():.3f}, mean = {night['norm_sma'].mean():.3f}")
    print(f"  norm_ema  median = {night['norm_ema'].median():.3f}, mean = {night['norm_ema'].mean():.3f}")

    df_t12 = task1_t2_baseline_replicate(strats, night)
    df_t12.to_csv(OUT_DIR / "t1_t2_baseline.csv", index=False)

    df_t3 = task3_cutoff_2026_04_17(strats, night)
    df_t3.to_csv(OUT_DIR / "t3_cutoff_h066_date.csv", index=False)

    df_t4 = task4_expanding_window(strats, night)
    df_t4.to_csv(OUT_DIR / "t4_expanding_window.csv", index=False)

    task5_algo_diff_summary()
    plot_expanding(df_t4)

    print("\nDone.")


if __name__ == "__main__":
    main()
