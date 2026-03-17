"""
OR% × Weekday 交叉分析

檢驗：不同星期的 OR% 分佈是否不同？
各星期在不同 OR% 區間的勝率/PF 是否有顯著差異？
驗證 thu_or_pct_min=0.7 的合理性。

用法: uv run python src/analysis/weekday_orpct_analysis.py
"""
import duckdb
import numpy as np
import pandas as pd
from backtesting import Backtest

from src.backtest.runner import load_data_with_night_ma
from src.strategies.orb import ORBLongStrategy

DB_PATH = "data/futures.duckdb"
WEEKDAY_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
START = "2021-01-01"
END = "2026-03-14"


def get_daily_or():
    """取每日 OR 寬度（08:45~09:30 的 High-Low）和開盤價"""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        rows = conn.execute("""
            SELECT
                timestamp::DATE AS trade_date,
                MAX(high) - MIN(low) AS or_width,
                FIRST(open ORDER BY timestamp) AS day_open
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45:00' AND '09:30:00'
              AND timestamp::DATE >= ?
            GROUP BY trade_date
            ORDER BY trade_date
        """, [START]).fetchall()

    df = pd.DataFrame(rows, columns=["date", "or_width", "day_open"])
    for col in ["or_width", "day_open"]:
        df[col] = df[col].astype(float)
    df["date"] = pd.to_datetime(df["date"])
    df["or_pct"] = df["or_width"] / df["day_open"] * 100
    df["weekday"] = df["date"].dt.weekday
    return df


def pf(s):
    gp = s[s > 0].sum()
    gl = abs(s[s < 0].sum())
    return gp / gl if gl > 0 else float("inf")


def main():
    # ── Part 1: OR% 分佈 × 星期 ──
    or_df = get_daily_or()

    print("=" * 80)
    print("  Part 1: 每日 OR% 分佈 × 星期（所有交易日，不限策略觸發）")
    print("=" * 80)
    print(f"\n  {'星期':<6} {'天數':>5} {'OR%均':>7} {'OR%中位':>8} {'StdDev':>7} {'<0.3%':>6} {'0.3-0.7%':>8} {'0.7-1.0%':>8} {'>1.0%':>6}")
    print(f"  {'-' * 72}")

    for wd in range(5):
        ws = or_df[or_df["weekday"] == wd]
        n = len(ws)
        pct = ws["or_pct"]
        b1 = (pct < 0.3).sum()
        b2 = ((pct >= 0.3) & (pct < 0.7)).sum()
        b3 = ((pct >= 0.7) & (pct < 1.0)).sum()
        b4 = (pct >= 1.0).sum()
        print(f"  {WEEKDAY_NAMES[wd]:<6} {n:>5} {pct.mean():>6.3f}% {pct.median():>7.3f}% {pct.std():>6.3f}% "
              f"{b1:>5}({b1/n*100:>3.0f}%) {b2:>5}({b2/n*100:>3.0f}%) {b3:>5}({b3/n*100:>3.0f}%) {b4:>5}({b4/n*100:>3.0f}%)")

    # ── Part 2: ORBLong 回測，無 weekday filter，取 trades ──
    print(f"\n\n{'=' * 80}")
    print("  Part 2: ORBLong 交易 × OR% 區間 × 星期")
    print("=" * 80)

    print("\nLoading ORBLong (no weekday filter)...")
    df = load_data_with_night_ma(start=START, end=END, trend_ma_days=10)
    bt = Backtest(df, ORBLongStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(
        long_only=1, sl_pct=0.004, tp_or_multiplier=1.5, or_min_width=20.0,
        trend_ma_days=10, or_pct_min=0.0, or_pct_max=99.0,  # 不設 OR% 門檻
        force_exit_minute=300, skip_thursday=0, thu_or_pct_min=0.0,
    )
    trades = stats["_trades"].copy()
    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["weekday"] = trades["EntryTime"].dt.weekday
    trades["trade_date"] = trades["EntryTime"].dt.date
    trades["pnl_pct"] = trades["PnL"] / trades["EntryPrice"].abs() * 100

    # 合併 OR%
    or_df["date_key"] = or_df["date"].dt.date
    trades = trades.merge(or_df[["date_key", "or_pct"]], left_on="trade_date", right_on="date_key", how="left")

    # OR% bins
    bins = [0, 0.3, 0.5, 0.7, 1.0, 99]
    labels = ["<0.3%", "0.3-0.5%", "0.5-0.7%", "0.7-1.0%", ">1.0%"]
    trades["or_bin"] = pd.cut(trades["or_pct"], bins=bins, labels=labels, right=False)

    # 各星期 × OR% bin
    for wd in range(5):
        wd_trades = trades[trades["weekday"] == wd]
        name = WEEKDAY_NAMES[wd]
        print(f"\n  ── {name}（共 {len(wd_trades)} 筆）──")
        print(f"  {'OR%區間':<12} {'筆數':>5} {'勝率':>7} {'PF':>6} {'平均損益':>9} {'總損益':>8}")
        print(f"  {'-' * 55}")

        for label in labels:
            sub = wd_trades[wd_trades["or_bin"] == label]
            if len(sub) == 0:
                print(f"  {label:<12}     0")
                continue
            wins = (sub["PnL"] > 0).sum()
            wr = wins / len(sub) * 100
            p = pf(sub["PnL"])
            ps = f"{p:.2f}" if p < 100 else "∞"
            print(f"  {label:<12} {len(sub):>5} {wr:>6.1f}% {ps:>6} {sub['PnL'].mean():>+9.1f} {sub['PnL'].sum():>+8.0f}")

        # subtotal
        if len(wd_trades) > 0:
            wins = (wd_trades["PnL"] > 0).sum()
            wr = wins / len(wd_trades) * 100
            p = pf(wd_trades["PnL"])
            print(f"  {'-' * 55}")
            print(f"  {'Total':<12} {len(wd_trades):>5} {wr:>6.1f}% {p:>6.2f} "
                  f"{wd_trades['PnL'].mean():>+9.1f} {wd_trades['PnL'].sum():>+8.0f}")

    # ── Part 3: 最佳 OR% 門檻 × 星期 ──
    print(f"\n\n{'=' * 80}")
    print("  Part 3: 各星期最佳 OR% 下限（掃描 0.0~1.0，步長 0.1）")
    print("=" * 80)

    print(f"\n  {'星期':<6} {'最佳下限':>8} {'筆數':>5} {'勝率':>7} {'PF':>6} {'Avg':>8} {'Total':>8}  {'vs 無門檻'}")
    print(f"  {'-' * 75}")

    for wd in range(5):
        wd_trades = trades[trades["weekday"] == wd]
        if len(wd_trades) == 0:
            continue

        best_pf = 0
        best_min = 0
        best_row = None
        base_total = wd_trades["PnL"].sum()

        for min_pct in np.arange(0, 1.1, 0.1):
            sub = wd_trades[wd_trades["or_pct"] >= min_pct]
            if len(sub) < 5:
                continue
            p = pf(sub["PnL"])
            if p > best_pf:
                best_pf = p
                best_min = min_pct
                best_row = sub

        if best_row is not None:
            sub = best_row
            wins = (sub["PnL"] > 0).sum()
            wr = wins / len(sub) * 100
            p = pf(sub["PnL"])
            ps = f"{p:.2f}" if p < 100 else "∞"
            diff = sub["PnL"].sum() - base_total
            print(f"  {WEEKDAY_NAMES[wd]:<6} {best_min:>7.1f}% {len(sub):>5} {wr:>6.1f}% {ps:>6} "
                  f"{sub['PnL'].mean():>+8.1f} {sub['PnL'].sum():>+8.0f}  {diff:>+6.0f} pts")


if __name__ == "__main__":
    main()
