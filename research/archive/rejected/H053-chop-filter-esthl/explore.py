#!/usr/bin/env python3
"""H053 — CHOP 斬波指標作為 EstHL 盤整日濾網：Phase 1 分佈探索。

分析內容：
1. 計算每日 CHOP(10/14/20)，分析分佈與區間比例
2. 比對 CHOP 分區（>61.8 / 38.2~61.8 / <38.2）的次日 EstHL 交易績效
3. 測試不同 CHOP 期間和門檻的敏感度
4. 測試 CHOP 對 S002 Reversal 的濾網效果

Usage:
    uv run python research/active/H053-chop-filter-esthl/explore.py
"""

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from backtesting import Backtest

# Project imports
from src.backtest.runner import (
    load_data_for_orb_est_hl,
    load_data_for_reversal,
    print_summary,
)
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy
from src.strategies.reversal import ReversalStrategy

DB_PATH = "data/futures.duckdb"
OUTPUT_DIR = Path("research/active/H053-chop-filter-esthl/results")


# ─── CHOP 計算 ─────────────────────────────────────────────────────────

def compute_chop(df_daily: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Choppiness Index on daily OHLCV.

    CHOP = 100 * LOG10(SUM(ATR, period) / (HH - LL)) / LOG10(period)
    """
    high = df_daily["High"].values
    low = df_daily["Low"].values
    close = df_daily["Close"].values
    n = len(df_daily)

    tr = np.full(n, np.nan)
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
    tr[0] = high[0] - low[0]  # first bar: just H-L

    sum_tr = pd.Series(tr).rolling(period, min_periods=period).sum().values
    max_high = pd.Series(high).rolling(period, min_periods=period).max().values
    min_low = pd.Series(low).rolling(period, min_periods=period).min().values

    denom = max_high - min_low
    denom[denom == 0] = np.nan
    chop = 100 * np.log10(sum_tr / denom) / np.log10(period)

    return pd.Series(chop, index=df_daily.index, name=f"CHOP_{period}")


def get_daily_ohlcv() -> pd.DataFrame:
    """從 ohlcv_1m 合成日線 OHLCV（日盤 08:45~13:45）。"""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp::DATE AS date,
                   FIRST(open ORDER BY timestamp)  AS open,
                   MAX(high)                        AS high,
                   MIN(low)                         AS low,
                   LAST(close ORDER BY timestamp)   AS close,
                   SUM(volume)                      AS volume
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            GROUP BY 1
            ORDER BY 1
        """).df()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    return df


# ─── 交易績效分析 ────────────────────────────────────────────────────────

def run_backtest_and_get_trades(strategy_name: str) -> pd.DataFrame:
    """跑回測，回傳交易 DataFrame（含 trade_date 欄位）。"""
    if strategy_name == "esthl":
        df = load_data_for_orb_est_hl()
        bt = Backtest(df, ORBWithEstHLExitStrategy,
                      cash=200_000, commission=0.0, trade_on_close=True)
        stats = bt.run(
            sl_ema_fraction=0.25, adx_min=0.0,
            long_only=True, vwap_days=2,
            skip_thursday=True, skip_friday=True,
        )
    elif strategy_name == "reversal":
        df = load_data_for_reversal()
        bt = Backtest(df, ReversalStrategy,
                      cash=200_000, commission=0.0, trade_on_close=True)
        stats = bt.run(
            vol_ratio=1.2, sl_ema_fraction=0.25,
            exhaust_fraction=0.5, signal_skip=0,
            sat_pullback_fraction=0.5,
        )
    else:
        raise ValueError(f"Unknown strategy: {strategy_name}")

    trades = stats["_trades"].copy()
    # EntryTime is datetime-like; extract date
    trades["trade_date"] = pd.to_datetime(trades["EntryTime"]).dt.normalize()
    trades["PnL_pts"] = trades["ExitPrice"] - trades["EntryPrice"]
    # For short trades, PnL is reversed
    trades.loc[trades["Size"] < 0, "PnL_pts"] *= -1
    return trades


def analyze_chop_filter(trades: pd.DataFrame, chop_daily: pd.Series,
                        threshold: float, strategy_name: str) -> dict:
    """分析 CHOP 濾網對交易績效的影響。"""
    # Shift CHOP by 1 day: use yesterday's CHOP to filter today's trade
    chop_prev = chop_daily.shift(1)
    chop_prev.name = "CHOP_prev"

    # Merge trades with previous-day CHOP
    merged = trades.merge(
        chop_prev.reset_index().rename(columns={"date": "trade_date", chop_daily.name: "CHOP_prev"}),
        on="trade_date", how="left",
    )
    merged = merged.dropna(subset=["CHOP_prev"])

    total_n = len(merged)
    if total_n == 0:
        return {}

    # Split: filtered (CHOP > threshold) vs kept
    filtered = merged[merged["CHOP_prev"] > threshold]
    kept = merged[merged["CHOP_prev"] <= threshold]

    def calc_stats(df, label):
        n = len(df)
        if n == 0:
            return {f"{label}_N": 0}
        wins = (df["PnL_pts"] > 0).sum()
        total_pnl = df["PnL_pts"].sum()
        avg_pnl = df["PnL_pts"].mean()
        gross_profit = df.loc[df["PnL_pts"] > 0, "PnL_pts"].sum()
        gross_loss = abs(df.loc[df["PnL_pts"] < 0, "PnL_pts"].sum())
        pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        return {
            f"{label}_N": n,
            f"{label}_WinRate": wins / n * 100,
            f"{label}_PF": pf,
            f"{label}_AvgPnL": avg_pnl,
            f"{label}_TotalPnL": total_pnl,
        }

    result = {
        "strategy": strategy_name,
        "chop_period": int(chop_daily.name.split("_")[1]),
        "threshold": threshold,
        "total_trades": total_n,
    }
    result.update(calc_stats(merged, "all"))
    result.update(calc_stats(kept, "kept"))
    result.update(calc_stats(filtered, "filtered"))
    result["filtered_pct"] = len(filtered) / total_n * 100

    return result


def analyze_chop_zones(trades: pd.DataFrame, chop_daily: pd.Series,
                       strategy_name: str) -> pd.DataFrame:
    """將交易依前一日 CHOP 分成三區分析。"""
    chop_prev = chop_daily.shift(1)

    merged = trades.merge(
        chop_prev.reset_index().rename(columns={"date": "trade_date", chop_daily.name: "CHOP_prev"}),
        on="trade_date", how="left",
    )
    merged = merged.dropna(subset=["CHOP_prev"])

    def zone(val):
        if val > 61.8:
            return "Choppy (>61.8)"
        elif val < 38.2:
            return "Trending (<38.2)"
        else:
            return "Neutral (38.2~61.8)"

    merged["zone"] = merged["CHOP_prev"].apply(zone)

    rows = []
    for z in ["Trending (<38.2)", "Neutral (38.2~61.8)", "Choppy (>61.8)"]:
        sub = merged[merged["zone"] == z]
        n = len(sub)
        if n == 0:
            rows.append({"zone": z, "N": 0})
            continue
        wins = (sub["PnL_pts"] > 0).sum()
        gp = sub.loc[sub["PnL_pts"] > 0, "PnL_pts"].sum()
        gl = abs(sub.loc[sub["PnL_pts"] < 0, "PnL_pts"].sum())
        rows.append({
            "zone": z,
            "N": n,
            "WinRate%": round(wins / n * 100, 1),
            "PF": round(gp / gl, 2) if gl > 0 else float("inf"),
            "AvgPnL": round(sub["PnL_pts"].mean(), 1),
            "TotalPnL": round(sub["PnL_pts"].sum(), 0),
        })

    return pd.DataFrame(rows)


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. 日線 OHLCV → CHOP ──────────────────────────────────────────
    print("=" * 60)
    print("Step 1: 計算每日 CHOP 指標")
    print("=" * 60)

    df_daily = get_daily_ohlcv()
    print(f"日線資料：{len(df_daily)} 天  [{df_daily.index[0].date()} → {df_daily.index[-1].date()}]")

    chop_series = {}
    for period in [10, 14, 20]:
        chop = compute_chop(df_daily, period=period)
        chop_series[period] = chop
        valid = chop.dropna()
        print(f"\nCHOP({period}) 分佈 (N={len(valid)}):")
        print(f"  Mean: {valid.mean():.1f}  Median: {valid.median():.1f}  Std: {valid.std():.1f}")
        print(f"  Min: {valid.min():.1f}  Max: {valid.max():.1f}")
        # Zone breakdown
        choppy = (valid > 61.8).sum()
        trending = (valid < 38.2).sum()
        neutral = len(valid) - choppy - trending
        print(f"  Choppy (>61.8): {choppy} ({choppy/len(valid)*100:.1f}%)")
        print(f"  Neutral (38.2~61.8): {neutral} ({neutral/len(valid)*100:.1f}%)")
        print(f"  Trending (<38.2): {trending} ({trending/len(valid)*100:.1f}%)")

    # Save CHOP data
    chop_df = pd.DataFrame({
        f"CHOP_{p}": chop_series[p] for p in [10, 14, 20]
    })
    chop_df.to_csv(OUTPUT_DIR / "chop_daily.csv")
    print(f"\nCHOP 資料已存 → {OUTPUT_DIR / 'chop_daily.csv'}")

    # ── 2. 跑 EstHL 回測 ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Step 2: 跑 EstHL 回測取得交易紀錄")
    print("=" * 60)

    trades_esthl = run_backtest_and_get_trades("esthl")
    print(f"EstHL 交易筆數：{len(trades_esthl)}")
    print(f"  時間範圍：{trades_esthl['trade_date'].min().date()} → {trades_esthl['trade_date'].max().date()}")
    total_pnl = trades_esthl["PnL_pts"].sum()
    wins = (trades_esthl["PnL_pts"] > 0).sum()
    print(f"  總損益：{total_pnl:.0f} pts  勝率：{wins/len(trades_esthl)*100:.1f}%")

    # ── 3. CHOP 分區 × EstHL 績效 ─────────────────────────────────────
    print("\n" + "=" * 60)
    print("Step 3: CHOP(14) 分區 × EstHL 交易績效")
    print("=" * 60)

    chop14 = chop_series[14]
    zone_df = analyze_chop_zones(trades_esthl, chop14, "esthl")
    print(zone_df.to_string(index=False))

    # ── 4. 參數敏感度測試 ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Step 4: CHOP 參數敏感度（EstHL）")
    print("=" * 60)

    sensitivity_rows = []
    for period in [10, 14, 20]:
        for thresh in [55.0, 58.0, 61.8, 65.0]:
            result = analyze_chop_filter(
                trades_esthl, chop_series[period], thresh, "esthl"
            )
            if result:
                sensitivity_rows.append(result)

    sens_df = pd.DataFrame(sensitivity_rows)
    cols = ["chop_period", "threshold", "total_trades",
            "filtered_pct", "all_PF", "kept_PF", "filtered_PF",
            "kept_N", "kept_WinRate", "kept_AvgPnL",
            "filtered_N", "filtered_WinRate", "filtered_AvgPnL"]
    print(sens_df[cols].to_string(index=False))

    sens_df.to_csv(OUTPUT_DIR / "sensitivity_esthl.csv", index=False)
    print(f"\n敏感度結果已存 → {OUTPUT_DIR / 'sensitivity_esthl.csv'}")

    # ── 5. S002 Reversal 的 CHOP 濾網效果 ─────────────────────────────
    print("\n" + "=" * 60)
    print("Step 5: CHOP 濾網對 S002 Reversal 的效果")
    print("=" * 60)

    trades_rev = run_backtest_and_get_trades("reversal")
    print(f"Reversal 交易筆數：{len(trades_rev)}")

    zone_rev = analyze_chop_zones(trades_rev, chop14, "reversal")
    print("\nCHOP(14) 分區 × Reversal 績效：")
    print(zone_rev.to_string(index=False))

    rev_rows = []
    for period in [10, 14, 20]:
        for thresh in [55.0, 58.0, 61.8, 65.0]:
            result = analyze_chop_filter(
                trades_rev, chop_series[period], thresh, "reversal"
            )
            if result:
                rev_rows.append(result)

    rev_df = pd.DataFrame(rev_rows)
    print(f"\nReversal 敏感度：")
    print(rev_df[cols].to_string(index=False))

    rev_df.to_csv(OUTPUT_DIR / "sensitivity_reversal.csv", index=False)
    print(f"\n敏感度結果已存 → {OUTPUT_DIR / 'sensitivity_reversal.csv'}")

    # ── 6. Summary ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    # Best filter for EstHL
    best_esthl = sens_df.loc[sens_df["kept_PF"].idxmax()]
    print(f"\n[EstHL] 最佳濾網：CHOP({int(best_esthl['chop_period'])}) > {best_esthl['threshold']}")
    print(f"  過濾 {best_esthl['filtered_pct']:.1f}% 交易")
    print(f"  PF: {best_esthl['all_PF']:.2f} → {best_esthl['kept_PF']:.2f}")
    print(f"  被過濾交易 PF: {best_esthl['filtered_PF']:.2f}")

    # Best filter for Reversal
    best_rev = rev_df.loc[rev_df["kept_PF"].idxmax()]
    print(f"\n[Reversal] 最佳濾網：CHOP({int(best_rev['chop_period'])}) > {best_rev['threshold']}")
    print(f"  過濾 {best_rev['filtered_pct']:.1f}% 交易")
    print(f"  PF: {best_rev['all_PF']:.2f} → {best_rev['kept_PF']:.2f}")
    print(f"  被過濾交易 PF: {best_rev['filtered_PF']:.2f}")

    print("\nDone!")


if __name__ == "__main__":
    main()
