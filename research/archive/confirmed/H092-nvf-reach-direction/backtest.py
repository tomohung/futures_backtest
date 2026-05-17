#!/usr/bin/env python3
"""H092 Phase 2 — Strong-GO direction bias 策略應用驗證.

從 Phase 1 distribution 發現:
    - Strong-GO (night_norm ≥ 1.20) 顯示 −8.9pp lower bias at 1.0× reach
    - Cross-year 5/6 一致,2025 是 bull regime 反例

Phase 2 驗證:strong-GO lower bias 能否轉成 S001 EstHL long-only 策略改進?

三個測試:
    Test 1: S001 long trades 在 strong-GO 天 vs 其他天的 PF / win / EV
    Test 2: 加 strong-GO long-skip filter → S001 整體績效變化
    Test 3: Cross-year 拆解(特別檢驗 2025 regime exception)

OOS 設計:
    IS: 2021-2024 (4 年)
    OOS: 2025-2026 (1.4 年, 包含 2025 regime 反例)

使用方式:
    uv run python research/active/H092-nvf-reach-direction/backtest.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).parent))
from explore import load_data  # provides night_norm, threshold, nvf_pass

from src.backtest.runner import load_data_for_orb_est_hl
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy

OUT_DIR = Path("research/active/H092-nvf-reach-direction/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

STRONG_GO_CUTOFF = 1.20  # H092 sensitivity 最強點

LIVE_PARAMS = dict(
    sl_ema_fraction=0.25,
    adx_min=0.0,
    long_only=True,
    vwap_days=2,
    skip_thursday=True,
    skip_friday=True,
)


def run_s001(start=None, end=None):
    """執行 S001 baseline 回測,回傳 trades DataFrame。"""
    df = load_data_for_orb_est_hl(start=start, end=end)
    bt = Backtest(df, ORBWithEstHLExitStrategy,
                  cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**LIVE_PARAMS)
    return stats["_trades"].copy(), stats


def annotate_trades_with_nvf(trades, nvf_df):
    """把 trades 用 entry date 對 night_norm/threshold/strong_go flag。"""
    trades = trades.copy()
    trades["entry_date"] = pd.to_datetime(trades["EntryTime"]).dt.normalize()
    nvf_lookup = nvf_df[["night_norm", "threshold", "nvf_pass"]].copy()
    nvf_lookup.index = pd.to_datetime(nvf_lookup.index).normalize()
    # align
    trades["night_norm"] = trades["entry_date"].map(nvf_lookup["night_norm"])
    trades["threshold"] = trades["entry_date"].map(nvf_lookup["threshold"])
    trades["nvf_pass"] = trades["entry_date"].map(nvf_lookup["nvf_pass"]).astype(bool)
    trades["strong_go"] = trades["night_norm"] >= STRONG_GO_CUTOFF
    trades["pnl_pct"] = trades["PnL"] / trades["EntryPrice"] * 100
    return trades


def stats(t):
    """Compute trade summary stats for a subset."""
    n = len(t)
    if n == 0:
        return {"N": 0, "win_rate": np.nan, "total_pnl": 0.0,
                "ev_pts": np.nan, "ev_pct": np.nan, "pf": np.nan,
                "total_pct": 0.0, "max_dd_pct": np.nan, "sharpe": np.nan}
    pnl = t["PnL"]
    pnl_pct = t["pnl_pct"]
    wins = pnl[pnl > 0].sum()
    losses = pnl[pnl < 0].sum()
    pf = wins / abs(losses) if losses < 0 else np.inf
    cum = pnl_pct.cumsum()
    dd = cum - cum.cummax()
    sharpe = pnl_pct.mean() / pnl_pct.std() * np.sqrt(252) if pnl_pct.std() > 0 else np.nan
    return {
        "N": n,
        "win_rate": (pnl > 0).mean(),
        "total_pnl": pnl.sum(),
        "ev_pts": pnl.mean(),
        "ev_pct": pnl_pct.mean(),
        "pf": pf,
        "total_pct": pnl_pct.sum(),
        "max_dd_pct": dd.min(),
        "sharpe": sharpe,
    }


def print_stats(label, s):
    print(f"  {label:24s} N={s['N']:>3} win={s['win_rate']:.1%}  "
          f"total={s['total_pnl']:+7.0f} pts ({s['total_pct']:+6.2f}%)  "
          f"EV={s['ev_pts']:+5.1f} pts ({s['ev_pct']:+.3f}%)  "
          f"PF={s['pf']:.2f}  Sharpe={s['sharpe']:.2f}")


def main():
    print("=" * 90)
    print(f"H092 Phase 2 — Strong-GO direction bias 策略應用 (cutoff = {STRONG_GO_CUTOFF})")
    print("=" * 90)

    print("\nLoading night_norm dataset (H092 explore)...")
    nvf_df = load_data()
    print(f"  NVF days: {len(nvf_df)}")

    print("\nRunning S001 EstHL baseline backtest (2021-01-01 ~ 2026-05-14)...")
    trades, raw_stats = run_s001(start="2021-01-01", end="2026-05-14")
    print(f"  baseline N={len(trades)}, total={trades['PnL'].sum():+.0f} pts, win={(trades['PnL'] > 0).mean():.1%}")

    trades = annotate_trades_with_nvf(trades, nvf_df)
    trades.to_csv(OUT_DIR / "s001_trades_annotated.csv", index=False)
    print(f"  annotated trades saved: {OUT_DIR / 's001_trades_annotated.csv'}")

    # Sanity: how many trades in each bucket?
    n_strong = int(trades["strong_go"].sum())
    n_other = int((~trades["strong_go"]).sum())
    n_missing_nvf = int(trades["night_norm"].isna().sum())
    print(f"  Strong-GO trades (≥{STRONG_GO_CUTOFF}): {n_strong} | other: {n_other} | missing NVF: {n_missing_nvf}")
    # Drop NaN NVF rows (e.g. weekends / warmup days)
    trades_valid = trades.dropna(subset=["night_norm"]).copy()
    print(f"  After NVF filter: N={len(trades_valid)}")

    # ── TEST 1: Strong-GO vs Other (pooled) ──
    print("\n" + "─" * 90)
    print("TEST 1: S001 long entries — strong-GO vs other day (pooled IS+OOS)")
    print("─" * 90)
    sg = trades_valid[trades_valid["strong_go"]]
    other = trades_valid[~trades_valid["strong_go"]]
    s_all = stats(trades_valid)
    s_sg = stats(sg)
    s_other = stats(other)
    print_stats("Baseline all", s_all)
    print_stats("Strong-GO (≥1.20)", s_sg)
    print_stats("Other days", s_other)

    pf_drop = s_sg["pf"] - s_other["pf"]
    ev_drop_pts = s_sg["ev_pts"] - s_other["ev_pts"]
    print(f"\n  Strong-GO vs Other: ΔPF={pf_drop:+.2f}, ΔEV={ev_drop_pts:+.1f} pts/trade")

    # ── TEST 2: Filter simulation ──
    print("\n" + "─" * 90)
    print("TEST 2: S001 with strong-GO long-skip filter")
    print("─" * 90)
    filtered = trades_valid[~trades_valid["strong_go"]]
    print_stats("Baseline (no filter)", s_all)
    print_stats("Strong-GO skipped", stats(filtered))
    diff_total = stats(filtered)["total_pnl"] - s_all["total_pnl"]
    diff_total_pct = stats(filtered)["total_pct"] - s_all["total_pct"]
    diff_sharpe = stats(filtered)["sharpe"] - s_all["sharpe"]
    print(f"\n  Filter effect: Δtotal={diff_total:+.0f} pts ({diff_total_pct:+.2f}%), ΔSharpe={diff_sharpe:+.2f}")

    # ── TEST 3: Yearly breakdown ──
    print("\n" + "─" * 90)
    print("TEST 3: Yearly breakdown — Baseline vs Strong-GO-filtered")
    print("─" * 90)
    trades_valid["year"] = pd.to_datetime(trades_valid["EntryTime"]).dt.year
    rows = []
    for y in sorted(trades_valid["year"].unique()):
        yt = trades_valid[trades_valid["year"] == y]
        yt_sg = yt[yt["strong_go"]]
        yt_other = yt[~yt["strong_go"]]
        rows.append({
            "year": y,
            "N_all": len(yt),
            "all_total": yt["PnL"].sum(),
            "all_total_pct": yt["pnl_pct"].sum(),
            "all_win": (yt["PnL"] > 0).mean(),
            "N_sg": len(yt_sg),
            "sg_total": yt_sg["PnL"].sum() if len(yt_sg) else 0,
            "sg_total_pct": yt_sg["pnl_pct"].sum() if len(yt_sg) else 0,
            "sg_win": (yt_sg["PnL"] > 0).mean() if len(yt_sg) else np.nan,
            "sg_ev": yt_sg["PnL"].mean() if len(yt_sg) else np.nan,
            "N_other": len(yt_other),
            "other_total": yt_other["PnL"].sum() if len(yt_other) else 0,
            "other_total_pct": yt_other["pnl_pct"].sum() if len(yt_other) else 0,
            "other_win": (yt_other["PnL"] > 0).mean() if len(yt_other) else np.nan,
            "other_ev": yt_other["PnL"].mean() if len(yt_other) else np.nan,
        })
    yearly_df = pd.DataFrame(rows)
    yearly_df.to_csv(OUT_DIR / "yearly_breakdown.csv", index=False)
    print(yearly_df.to_string(index=False, formatters={
        "all_total": lambda v: f"{v:+6.0f}",
        "sg_total": lambda v: f"{v:+6.0f}",
        "other_total": lambda v: f"{v:+6.0f}",
        "all_total_pct": lambda v: f"{v:+5.2f}",
        "sg_total_pct": lambda v: f"{v:+5.2f}",
        "other_total_pct": lambda v: f"{v:+5.2f}",
        "all_win": lambda v: f"{v:.1%}" if not pd.isna(v) else "—",
        "sg_win": lambda v: f"{v:.1%}" if not pd.isna(v) else "—",
        "other_win": lambda v: f"{v:.1%}" if not pd.isna(v) else "—",
        "sg_ev": lambda v: f"{v:+.1f}" if not pd.isna(v) else "—",
        "other_ev": lambda v: f"{v:+.1f}" if not pd.isna(v) else "—",
    }))

    # ── TEST 4: IS / OOS split ──
    print("\n" + "─" * 90)
    print("TEST 4: IS (2021-2024) vs OOS (2025-2026)")
    print("─" * 90)
    is_t = trades_valid[trades_valid["year"] <= 2024]
    oos_t = trades_valid[trades_valid["year"] >= 2025]

    is_all = stats(is_t)
    is_sg = stats(is_t[is_t["strong_go"]])
    is_other = stats(is_t[~is_t["strong_go"]])
    is_filtered = stats(is_t[~is_t["strong_go"]])
    print("IS (2021-2024):")
    print_stats("  Baseline", is_all)
    print_stats("  Strong-GO", is_sg)
    print_stats("  Other days", is_other)
    print(f"  IS strong-GO drag vs other: ΔPF={is_sg['pf']-is_other['pf']:+.2f}, "
          f"ΔEV={is_sg['ev_pts']-is_other['ev_pts']:+.1f}")

    oos_all = stats(oos_t)
    oos_sg = stats(oos_t[oos_t["strong_go"]])
    oos_other = stats(oos_t[~oos_t["strong_go"]])
    print("\nOOS (2025-2026):")
    print_stats("  Baseline", oos_all)
    print_stats("  Strong-GO", oos_sg)
    print_stats("  Other days", oos_other)
    print(f"  OOS strong-GO drag vs other: ΔPF={oos_sg['pf']-oos_other['pf']:+.2f}, "
          f"ΔEV={oos_sg['ev_pts']-oos_other['ev_pts']:+.1f}")

    # Filter improvement IS / OOS
    print("\n  Filter simulation (skip strong-GO longs):")
    print(f"    IS  baseline {is_all['total_pnl']:+.0f} ({is_all['total_pct']:+.2f}%) → "
          f"filtered {is_other['total_pnl']:+.0f} ({is_other['total_pct']:+.2f}%)  "
          f"Δ={is_other['total_pnl']-is_all['total_pnl']:+.0f} pts")
    print(f"    OOS baseline {oos_all['total_pnl']:+.0f} ({oos_all['total_pct']:+.2f}%) → "
          f"filtered {oos_other['total_pnl']:+.0f} ({oos_other['total_pct']:+.2f}%)  "
          f"Δ={oos_other['total_pnl']-oos_all['total_pnl']:+.0f} pts")

    # ── Save summary ──
    summary = {
        "cutoff": STRONG_GO_CUTOFF,
        "pooled_baseline_total": s_all["total_pnl"],
        "pooled_baseline_pct": s_all["total_pct"],
        "pooled_baseline_sharpe": s_all["sharpe"],
        "pooled_strong_go_pf": s_sg["pf"],
        "pooled_other_pf": s_other["pf"],
        "pooled_pf_drop": s_sg["pf"] - s_other["pf"],
        "pooled_ev_drop_pts": s_sg["ev_pts"] - s_other["ev_pts"],
        "pooled_filter_delta_pts": diff_total,
        "pooled_filter_delta_pct": diff_total_pct,
        "is_strong_go_pf": is_sg["pf"],
        "is_other_pf": is_other["pf"],
        "is_filter_delta_pts": is_other["total_pnl"] - is_all["total_pnl"],
        "oos_strong_go_pf": oos_sg["pf"],
        "oos_other_pf": oos_other["pf"],
        "oos_filter_delta_pts": oos_other["total_pnl"] - oos_all["total_pnl"],
    }
    pd.Series(summary).to_csv(OUT_DIR / "backtest_summary.csv")
    print(f"\nSummary saved: {OUT_DIR / 'backtest_summary.csv'}")


if __name__ == "__main__":
    main()
