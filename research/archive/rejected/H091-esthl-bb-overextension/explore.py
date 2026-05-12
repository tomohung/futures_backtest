#!/usr/bin/env python3
"""H091 Phase 1 — 30m BB%B(20, open, 2σ) 在 EstHL 訊號上的分佈與假突破率分析。

雙 Pool 設計：
    Pool A — S001 filtered entries：跑 ORBWithEstHLExitStrategy（完整濾網），看實際成交筆
    Pool B — Raw ORB long breakout：純 08:58-09:15 close > OR High，無任何濾網

對每筆 entry：
    - 取 entry 當日「日盤第一根 30m bar (08:45-09:15)」的 BB%B(20, open, 2σ)
    - 計算 fixed SL = entry - EmaHL × 0.25
    - 判斷是否 hit fixed SL（Pool A：PnL ≤ -0.95×sl_dist；Pool B：1m Low ≤ SL）

輸出：
    results/distribution.md — 含分桶 / 年度 / 視覺化結果
    results/bbpct_hist.png  — Pool A & B BB%B 分佈直方圖
    results/sl_rate_bars.png — 各桶 SL hit rate 柱狀圖
    results/yearly_heatmap.png — 年 × 桶 SL hit rate 熱圖
"""
from __future__ import annotations

import sys
from datetime import time as dtime
from pathlib import Path

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from backtesting import Backtest

# 讓 import src.* 可用
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.backtest.runner import load_data_for_orb_est_hl  # noqa: E402
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy  # noqa: E402

RESULT_DIR = Path(__file__).resolve().parent / "results"
RESULT_DIR.mkdir(exist_ok=True)

START = "2021-01-01"
END   = "2026-05-12"
DB_PATH = ROOT / "data" / "futures.duckdb"

BUCKETS = [(-np.inf, 0.0), (0.0, 0.5), (0.5, 1.0), (1.0, np.inf)]
BUCKET_LABELS = ["(-∞, 0]", "(0, 0.5]", "(0.5, 1]", "(1, +∞)"]


def compute_first_30m_bbpct(df_day: pd.DataFrame) -> pd.Series:
    """Compute day-level BB%B = first 30m bar's BB%B(20, open, 2σ).

    Replicates exhaustion.py logic (runner.load_data_for_exhaustion).
    Returns a Series indexed by date (normalized timestamps).
    """
    s30_open = df_day["Open"].resample("30min", offset="15min").first().dropna()
    bb_ma  = s30_open.rolling(20, min_periods=20).mean()
    bb_std = s30_open.rolling(20, min_periods=20).std(ddof=1)
    bb_upper = bb_ma + 2 * bb_std
    bb_lower = bb_ma - 2 * bb_std
    bb_pctb  = (s30_open - bb_lower) / (bb_upper - bb_lower)

    bb_pctb_df = bb_pctb.to_frame("bbpct")
    bb_pctb_df["date"] = bb_pctb_df.index.normalize()
    first_bb = bb_pctb_df.groupby("date")["bbpct"].first()
    return first_bb


def bucket_of(x: float) -> int:
    """Return bucket index 0–3 for a BB%B value, or -1 if NaN."""
    if pd.isna(x):
        return -1
    for i, (lo, hi) in enumerate(BUCKETS):
        if lo < x <= hi:
            return i
    return -1


# ─── Pool A: S001 filtered entries via Backtest ────────────────────────────
def run_pool_a(df_day: pd.DataFrame, bbpct_series: pd.Series) -> pd.DataFrame:
    print(f"[Pool A] Running ORBWithEstHLExitStrategy on {START}…{END}")
    bt = Backtest(df_day, ORBWithEstHLExitStrategy,
                  cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(
        sl_ema_fraction=0.25, adx_min=0.0, long_only=True,
        vwap_days=2, skip_thursday=True, skip_friday=True,
    )
    trades = stats["_trades"].copy()
    print(f"[Pool A] Got {len(trades)} trades")

    # EmaHL @ entry → sl_dist → is_sl_hit
    df_day_emahl = df_day["EmaHL"].copy()
    entry_emahl = df_day_emahl.reindex(trades["EntryTime"]).values
    trades["EmaHL"] = entry_emahl
    trades["sl_dist"] = trades["EmaHL"] * 0.25
    # SL hit = PnL ≤ -0.95 × sl_dist (i.e. exit < sl_price + tiny tolerance)
    trades["is_sl_hit"] = trades["PnL"] <= (-0.95 * trades["sl_dist"])

    # BB%B at entry day
    entry_dates = pd.DatetimeIndex(trades["EntryTime"]).normalize()
    trades["bbpct"] = bbpct_series.reindex(entry_dates).values
    trades["bucket"] = trades["bbpct"].apply(bucket_of)
    trades["year"] = pd.DatetimeIndex(trades["EntryTime"]).year
    trades["pool"] = "A"
    return trades


# ─── Pool B: Raw ORB long breakout (no filters) ────────────────────────────
def run_pool_b(df_day: pd.DataFrame, bbpct_series: pd.Series) -> pd.DataFrame:
    """For each trading day, find the first 1m bar in 08:58-09:15 where close > OR High.
    Simulate entry at that close, fixed SL = entry - 0.25 × EmaHL.
    Determine SL hit by scanning 1m Low ≤ SL until 13:30.
    """
    print(f"[Pool B] Scanning raw ORB long breakouts…")
    records: list[dict] = []

    df = df_day.copy()
    df["date"] = df.index.normalize()
    df["time"] = df.index.time

    OR_START = dtime(8, 45)
    OR_END   = dtime(8, 57)
    ENTRY_START = dtime(8, 58)
    ENTRY_END   = dtime(9, 15)
    FORCE_EXIT  = dtime(13, 30)

    for date, day_df in df.groupby("date"):
        # OR window 08:45-08:57
        or_bars = day_df[(day_df["time"] >= OR_START) & (day_df["time"] <= OR_END)]
        if or_bars.empty:
            continue
        or_high = or_bars["High"].max()
        or_low  = or_bars["Low"].min()

        # entry window 08:58-09:15
        entry_window = day_df[(day_df["time"] >= ENTRY_START) & (day_df["time"] <= ENTRY_END)]
        ema_hl_first = entry_window["EmaHL"].iloc[0] if not entry_window.empty else np.nan
        if pd.isna(ema_hl_first) or ema_hl_first <= 0:
            continue

        # First bar where close > or_high
        breakout = entry_window[entry_window["Close"] > or_high]
        if breakout.empty:
            continue

        entry_bar = breakout.iloc[0]
        entry_ts = breakout.index[0]
        entry_price = float(entry_bar["Close"])
        sl_dist = 0.25 * float(ema_hl_first)
        sl_price = entry_price - sl_dist

        # Scan from entry+1 to 13:30 for Low ≤ SL or force exit
        after = day_df[(day_df.index > entry_ts) & (day_df["time"] < FORCE_EXIT)]
        if after.empty:
            # entered too late, force exit at same bar?
            exit_price = entry_price
            is_sl_hit = False
        else:
            hit_mask = after["Low"] <= sl_price
            if hit_mask.any():
                hit_bar = after[hit_mask].iloc[0]
                exit_price = float(sl_price)  # exits at SL price (touch)
                is_sl_hit = True
            else:
                # force exit at 13:30 close (last bar < 13:30 actually since we filter < FORCE_EXIT)
                # Use close of last bar before 13:30
                exit_price = float(after.iloc[-1]["Close"])
                is_sl_hit = False

        pnl = exit_price - entry_price
        records.append({
            "EntryTime": entry_ts,
            "EntryPrice": entry_price,
            "ExitPrice": exit_price,
            "PnL": pnl,
            "EmaHL": float(ema_hl_first),
            "sl_dist": sl_dist,
            "is_sl_hit": is_sl_hit,
            "or_high": or_high,
            "or_low": or_low,
        })

    trades = pd.DataFrame.from_records(records)
    print(f"[Pool B] Got {len(trades)} ORB long breakout signals")
    if trades.empty:
        return trades

    entry_dates = pd.DatetimeIndex(trades["EntryTime"]).normalize()
    trades["bbpct"] = bbpct_series.reindex(entry_dates).values
    trades["bucket"] = trades["bbpct"].apply(bucket_of)
    trades["year"] = pd.DatetimeIndex(trades["EntryTime"]).year
    trades["pool"] = "B"
    return trades


# ─── Analysis ──────────────────────────────────────────────────────────────
def bucket_stats(trades: pd.DataFrame, group_col: str | None = None) -> pd.DataFrame:
    """Compute N + SL hit rate per bucket; optionally further grouped (e.g. by year)."""
    valid = trades[trades["bucket"] >= 0].copy()
    valid["bucket_label"] = valid["bucket"].map(dict(enumerate(BUCKET_LABELS)))

    keys = ["bucket_label"] if group_col is None else [group_col, "bucket_label"]
    grouped = valid.groupby(keys).agg(
        N=("is_sl_hit", "size"),
        sl_hits=("is_sl_hit", "sum"),
        pnl_mean=("PnL", "mean"),
    ).reset_index()
    grouped["sl_rate"] = grouped["sl_hits"] / grouped["N"]
    return grouped


def overall_stats(trades: pd.DataFrame) -> dict:
    valid = trades[trades["bucket"] >= 0]
    return {
        "N": len(valid),
        "sl_rate": valid["is_sl_hit"].mean() if len(valid) else float("nan"),
        "pnl_mean": valid["PnL"].mean() if len(valid) else float("nan"),
    }


# ─── Plots ─────────────────────────────────────────────────────────────────
def plot_bbpct_histogram(pool_a: pd.DataFrame, pool_b: pd.DataFrame, out_path: Path):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=False)
    for ax, df, title, color in zip(
        axes,
        [pool_a, pool_b],
        ["Pool A — S001 filtered entries", "Pool B — Raw ORB long breakout"],
        ["#1f77b4", "#ff7f0e"],
    ):
        valid = df[df["bbpct"].notna()]
        ax.hist(valid["bbpct"], bins=40, color=color, alpha=0.75, edgecolor="black")
        for x in (0.0, 0.5, 1.0):
            ax.axvline(x, color="gray", linestyle="--", linewidth=1)
        ax.set_title(f"{title}  (N={len(valid)})")
        ax.set_xlabel("30m BB%B(20, open, 2σ) at entry-day first bar")
        ax.set_ylabel("Trade count")
    fig.suptitle("H091 — 30m BB%B distribution at EstHL signal entries")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_sl_rate_bars(stats_a: pd.DataFrame, stats_b: pd.DataFrame,
                       overall_a: dict, overall_b: dict, out_path: Path):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    for ax, stats, overall, title, color in zip(
        axes,
        [stats_a, stats_b],
        [overall_a, overall_b],
        ["Pool A — S001 filtered", "Pool B — Raw ORB breakout"],
        ["#1f77b4", "#ff7f0e"],
    ):
        stats_sorted = stats.set_index("bucket_label").reindex(BUCKET_LABELS)
        bars = ax.bar(BUCKET_LABELS, stats_sorted["sl_rate"] * 100,
                       color=color, alpha=0.8, edgecolor="black")
        ax.axhline(overall["sl_rate"] * 100, color="red", linestyle="--",
                    linewidth=1.5, label=f"Overall {overall['sl_rate']*100:.1f}%")
        for bar, n in zip(bars, stats_sorted["N"].fillna(0)):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                     f"N={int(n)}", ha="center", fontsize=9)
        ax.set_title(f"{title}  (overall N={overall['N']})")
        ax.set_ylabel("Fixed SL hit rate (%)")
        ax.set_ylim(0, max(100, ax.get_ylim()[1]))
        ax.legend(loc="upper left")
    fig.suptitle("H091 — Fixed SL hit rate by 30m BB%B bucket")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_yearly_heatmap(trades_a: pd.DataFrame, trades_b: pd.DataFrame, out_path: Path):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for ax, trades, title in zip(
        axes,
        [trades_a, trades_b],
        ["Pool A — S001 filtered", "Pool B — Raw ORB breakout"],
    ):
        valid = trades[trades["bucket"] >= 0].copy()
        valid["bucket_label"] = valid["bucket"].map(dict(enumerate(BUCKET_LABELS)))
        pivot_rate = valid.pivot_table(
            index="year", columns="bucket_label",
            values="is_sl_hit", aggfunc="mean"
        ).reindex(columns=BUCKET_LABELS)
        pivot_n = valid.pivot_table(
            index="year", columns="bucket_label",
            values="is_sl_hit", aggfunc="size"
        ).reindex(columns=BUCKET_LABELS)

        im = ax.imshow(pivot_rate.values * 100, cmap="RdYlGn_r", vmin=0, vmax=100,
                        aspect="auto")
        ax.set_xticks(range(len(BUCKET_LABELS)))
        ax.set_xticklabels(BUCKET_LABELS, rotation=0)
        ax.set_yticks(range(len(pivot_rate.index)))
        ax.set_yticklabels(pivot_rate.index)
        ax.set_title(title)
        for i, year in enumerate(pivot_rate.index):
            for j, bk in enumerate(BUCKET_LABELS):
                v = pivot_rate.iloc[i, j]
                n = pivot_n.iloc[i, j]
                if pd.isna(v):
                    text = "—"
                else:
                    text = f"{v*100:.0f}%\n(N={int(n)})"
                ax.text(j, i, text, ha="center", va="center", fontsize=8)
        fig.colorbar(im, ax=ax, label="SL hit rate (%)")
    fig.suptitle("H091 — Yearly SL hit rate by BB%B bucket")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


# ─── Main ──────────────────────────────────────────────────────────────────
def main():
    print("Loading data with load_data_for_orb_est_hl…")
    df_day = load_data_for_orb_est_hl(start=START, end=END)
    print(f"Loaded {len(df_day):,} bars  [{df_day.index[0]} → {df_day.index[-1]}]")

    print("Computing 30m BB%B(20, open, 2σ) at first day-session 30m bar…")
    bbpct = compute_first_30m_bbpct(df_day)
    print(f"  BB%B series: {bbpct.notna().sum()} valid days / {len(bbpct)} total")

    # Pools
    pool_a = run_pool_a(df_day, bbpct)
    pool_b = run_pool_b(df_day, bbpct)

    # Stats
    overall_a = overall_stats(pool_a)
    overall_b = overall_stats(pool_b)
    stats_a   = bucket_stats(pool_a)
    stats_b   = bucket_stats(pool_b)
    year_a    = bucket_stats(pool_a, group_col="year")
    year_b    = bucket_stats(pool_b, group_col="year")

    # Save raw trades
    pool_a.to_csv(RESULT_DIR / "pool_a_trades.csv", index=False)
    pool_b.to_csv(RESULT_DIR / "pool_b_trades.csv", index=False)

    # Plots
    plot_bbpct_histogram(pool_a, pool_b, RESULT_DIR / "bbpct_hist.png")
    plot_sl_rate_bars(stats_a, stats_b, overall_a, overall_b,
                       RESULT_DIR / "sl_rate_bars.png")
    plot_yearly_heatmap(pool_a, pool_b, RESULT_DIR / "yearly_heatmap.png")

    # Console summary
    def fmt(d):
        return f"N={d['N']}, SL rate={d['sl_rate']*100:.1f}%, mean PnL={d['pnl_mean']:.1f}"
    print("\n=== Pool A overall ===")
    print(fmt(overall_a))
    print(stats_a.to_string(index=False))
    print("\n=== Pool B overall ===")
    print(fmt(overall_b))
    print(stats_b.to_string(index=False))

    # Year × bucket
    print("\n=== Pool A by year × bucket ===")
    print(year_a.to_string(index=False))
    print("\n=== Pool B by year × bucket ===")
    print(year_b.to_string(index=False))

    # Save stats CSVs
    stats_a.to_csv(RESULT_DIR / "pool_a_bucket_stats.csv", index=False)
    stats_b.to_csv(RESULT_DIR / "pool_b_bucket_stats.csv", index=False)
    year_a.to_csv(RESULT_DIR / "pool_a_year_bucket_stats.csv", index=False)
    year_b.to_csv(RESULT_DIR / "pool_b_year_bucket_stats.csv", index=False)

    print(f"\nArtifacts saved → {RESULT_DIR}/")


if __name__ == "__main__":
    main()
