#!/usr/bin/env python3
"""H053 — CHOP(10) > 61.8 濾網：Phase 2 回測驗證。

驗證內容：
1. IS/OOS 驗證（2021-2023 IS / 2024-2026 OOS）
2. 與現有濾網（weekday / VWAP / ORB width）的交互效果
3. Reversal 策略的 CHOP 濾網驗證
4. 門檻穩定性（50 / 55 / 61.8 / 65）

Usage:
    uv run python research/active/H053-chop-filter-esthl/backtest.py
"""

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from backtesting import Backtest

from src.backtest.runner import load_data_for_orb_est_hl, load_data_for_reversal
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy
from src.strategies.reversal import ReversalStrategy

DB_PATH = "data/futures.duckdb"
OUTPUT_DIR = Path("research/active/H053-chop-filter-esthl/results")


# ─── CHOP 計算 ─────────────────────────────────────────────────────────

def compute_chop10() -> pd.Series:
    """計算每日 CHOP(10)，回傳 Series indexed by date。"""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute("""
            SELECT timestamp::DATE AS date,
                   FIRST(open ORDER BY timestamp) AS open,
                   MAX(high) AS high, MIN(low) AS low,
                   LAST(close ORDER BY timestamp) AS close
            FROM ohlcv_1m WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN TIME '08:45:00' AND TIME '13:45:00'
            GROUP BY 1 ORDER BY 1
        """).df()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")

    period = 10
    high, low, close = df["high"].values, df["low"].values, df["close"].values
    n = len(df)
    tr = np.full(n, np.nan)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                     abs(high[i] - close[i - 1]),
                     abs(low[i] - close[i - 1]))

    sum_tr = pd.Series(tr).rolling(period, min_periods=period).sum().values
    max_high = pd.Series(high).rolling(period, min_periods=period).max().values
    min_low = pd.Series(low).rolling(period, min_periods=period).min().values
    denom = max_high - min_low
    denom[denom == 0] = np.nan
    chop = 100 * np.log10(sum_tr / denom) / np.log10(period)

    return pd.Series(chop, index=df.index, name="CHOP_10")


# ─── 工具函式 ──────────────────────────────────────────────────────────

def prepare_trades(stats, chop_prev: pd.Series) -> pd.DataFrame:
    """從 backtesting stats 提取交易並附加前一日 CHOP。"""
    trades = stats["_trades"].copy()
    trades["trade_date"] = pd.to_datetime(trades["EntryTime"]).dt.normalize()
    trades["PnL_pts"] = trades["ExitPrice"] - trades["EntryPrice"]
    trades.loc[trades["Size"] < 0, "PnL_pts"] *= -1
    trades["PnL_pct"] = trades["PnL_pts"] / trades["EntryPrice"] * 100

    merged = trades.merge(
        chop_prev.reset_index().rename(
            columns={"date": "trade_date", chop_prev.name: "CHOP_prev"}
        ),
        on="trade_date", how="left",
    )
    return merged.dropna(subset=["CHOP_prev"])


def calc_metrics(df: pd.DataFrame, label: str = "") -> dict:
    """計算績效指標。"""
    n = len(df)
    if n == 0:
        return {"label": label, "N": 0, "WR%": 0, "PF": 0,
                "AvgPnL": 0, "TotalPnL": 0, "Sharpe": 0}
    wins = (df["PnL_pts"] > 0).sum()
    gp = df.loc[df["PnL_pts"] > 0, "PnL_pts"].sum()
    gl = abs(df.loc[df["PnL_pts"] < 0, "PnL_pts"].sum())
    pf = gp / gl if gl > 0 else float("inf")
    sharpe = (df["PnL_pct"].mean() / df["PnL_pct"].std() * (252 ** 0.5)
              if df["PnL_pct"].std() > 0 else 0)
    return {
        "label": label, "N": n,
        "WR%": round(wins / n * 100, 1),
        "PF": round(pf, 2),
        "AvgPnL": round(df["PnL_pts"].mean(), 1),
        "TotalPnL": round(df["PnL_pts"].sum(), 0),
        "Sharpe": round(sharpe, 2),
    }


def print_comparison(rows: list[dict]):
    """印出比較表。"""
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    return df


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    chop = compute_chop10()
    chop_prev = chop.shift(1)
    chop_prev.name = "CHOP_prev"

    # ── 1. EstHL IS/OOS ───────────────────────────────────────────────
    print("=" * 70)
    print("1. EstHL IS/OOS 驗證：CHOP(10) > 61.8")
    print("   IS: 2021-01-01 ~ 2023-12-31 / OOS: 2024-01-01 ~ 2026-12-31")
    print("=" * 70)

    thresholds = [50, 55, 61.8, 65]

    for period_label, start, end in [
        ("IS (2021-2023)", "2021-01-01", "2023-12-31"),
        ("OOS (2024-2026)", "2024-01-01", None),
        ("FULL", None, None),
    ]:
        print(f"\n--- {period_label} ---")
        df_e = load_data_for_orb_est_hl(start=start, end=end)
        bt = Backtest(df_e, ORBWithEstHLExitStrategy,
                      cash=200_000, commission=0.0, trade_on_close=True)
        stats = bt.run(sl_ema_fraction=0.25, adx_min=0.0,
                       long_only=True, vwap_days=2,
                       skip_thursday=True, skip_friday=True)
        trades = prepare_trades(stats, chop_prev)

        rows = [calc_metrics(trades, "Baseline (no CHOP)")]
        for t in thresholds:
            kept = trades[trades["CHOP_prev"] <= t]
            rows.append(calc_metrics(kept, f"CHOP(10)≤{t}"))
        print_comparison(rows)

    # ── 2. 被過濾交易的品質（全期間）──────────────────────────────────
    print("\n" + "=" * 70)
    print("2. 被 CHOP(10) > 61.8 過濾的 EstHL 交易明細")
    print("=" * 70)

    df_e_full = load_data_for_orb_est_hl()
    bt_full = Backtest(df_e_full, ORBWithEstHLExitStrategy,
                       cash=200_000, commission=0.0, trade_on_close=True)
    stats_full = bt_full.run(sl_ema_fraction=0.25, adx_min=0.0,
                             long_only=True, vwap_days=2,
                             skip_thursday=True, skip_friday=True)
    trades_full = prepare_trades(stats_full, chop_prev)

    filtered = trades_full[trades_full["CHOP_prev"] > 61.8]
    if len(filtered) > 0:
        print(f"\n被過濾交易 (N={len(filtered)}):")
        for _, row in filtered.iterrows():
            print(f"  {row['trade_date'].date()} "
                  f"CHOP={row['CHOP_prev']:.1f}  "
                  f"Entry={row['EntryPrice']:.0f}  "
                  f"Exit={row['ExitPrice']:.0f}  "
                  f"PnL={row['PnL_pts']:+.0f}")
        print(f"\n  合計：{filtered['PnL_pts'].sum():.0f} pts  "
              f"WR={((filtered['PnL_pts'] > 0).sum() / len(filtered) * 100):.0f}%")
    else:
        print("  無被過濾的交易")

    # ── 3. 與現有濾網的交互效果 ───────────────────────────────────────
    print("\n" + "=" * 70)
    print("3. CHOP 與現有濾網的交互效果（EstHL 全期間）")
    print("=" * 70)

    # Check if CHOP filter is redundant with existing filters
    # by looking at the CHOP distribution of filtered-out trades
    all_trades_no_skip = prepare_trades(
        Backtest(df_e_full, ORBWithEstHLExitStrategy,
                 cash=200_000, commission=0.0, trade_on_close=True).run(
            sl_ema_fraction=0.25, adx_min=0.0, long_only=True, vwap_days=2,
            skip_thursday=False, skip_friday=False),
        chop_prev,
    )

    # Compare: weekday-only vs CHOP-only vs both
    rows = []
    # Baseline: all trades (no filter)
    rows.append(calc_metrics(all_trades_no_skip, "No filter"))
    # Weekday only
    wd_only = all_trades_no_skip[all_trades_no_skip["trade_date"].dt.weekday < 3]
    rows.append(calc_metrics(wd_only, "Weekday only (Mon~Wed)"))
    # CHOP only
    chop_only = all_trades_no_skip[all_trades_no_skip["CHOP_prev"] <= 61.8]
    rows.append(calc_metrics(chop_only, "CHOP(10)≤61.8 only"))
    # Both
    both = all_trades_no_skip[
        (all_trades_no_skip["trade_date"].dt.weekday < 3) &
        (all_trades_no_skip["CHOP_prev"] <= 61.8)
    ]
    rows.append(calc_metrics(both, "Weekday + CHOP(10)≤61.8"))

    print_comparison(rows)

    # ── 4. Reversal IS/OOS ────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("4. Reversal IS/OOS 驗證：CHOP(10) > 61.8")
    print("=" * 70)

    for period_label, start, end in [
        ("IS (2021-2023)", "2021-01-01", "2023-12-31"),
        ("OOS (2024-2026)", "2024-01-01", None),
        ("FULL", None, None),
    ]:
        print(f"\n--- {period_label} ---")
        df_r = load_data_for_reversal(start=start, end=end)
        bt_r = Backtest(df_r, ReversalStrategy,
                        cash=200_000, commission=0.0, trade_on_close=True)
        stats_r = bt_r.run(vol_ratio=1.2, sl_ema_fraction=0.25,
                           exhaust_fraction=0.5, signal_skip=0,
                           sat_pullback_fraction=0.5)
        trades_r = prepare_trades(stats_r, chop_prev)

        rows = [calc_metrics(trades_r, "Baseline (no CHOP)")]
        for t in thresholds:
            kept = trades_r[trades_r["CHOP_prev"] <= t]
            rows.append(calc_metrics(kept, f"CHOP(10)≤{t}"))
        print_comparison(rows)

    # ── 5. 年度一致性（EstHL） ────────────────────────────────────────
    print("\n" + "=" * 70)
    print("5. EstHL 年度一致性：Baseline vs CHOP(10)≤61.8")
    print("=" * 70)

    trades_full["year"] = trades_full["trade_date"].dt.year
    rows = []
    for year in sorted(trades_full["year"].unique()):
        yr_all = trades_full[trades_full["year"] == year]
        yr_kept = yr_all[yr_all["CHOP_prev"] <= 61.8]
        m_all = calc_metrics(yr_all, f"{year} baseline")
        m_kept = calc_metrics(yr_kept, f"{year} +CHOP")
        rows.append({
            "Year": year,
            "Base_N": m_all["N"], "Base_PF": m_all["PF"],
            "Base_WR%": m_all["WR%"], "Base_Total": m_all["TotalPnL"],
            "CHOP_N": m_kept["N"], "CHOP_PF": m_kept["PF"],
            "CHOP_WR%": m_kept["WR%"], "CHOP_Total": m_kept["TotalPnL"],
            "Δ_PF": round(m_kept["PF"] - m_all["PF"], 2),
        })
    yr_df = pd.DataFrame(rows)
    print(yr_df.to_string(index=False))

    print("\nDone!")


if __name__ == "__main__":
    main()
