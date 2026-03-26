"""
OR% × Weekday：ORBLong + EstHL 分開呈現

用法: uv run python src/analysis/weekday_orpct_both.py
"""
import duckdb
import numpy as np
import pandas as pd
from backtesting import Backtest

from src.backtest.runner import load_data_with_night_ma, load_data_for_orb_est_hl
from src.strategies.orb import ORBLongStrategy
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy

DB_PATH = "data/futures.duckdb"
WEEKDAY_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
START = "2021-01-01"
END = "2026-03-14"


def get_daily_or():
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
    df["date_key"] = df["date"].dt.date
    return df


def pf(s):
    gp = s[s > 0].sum()
    gl = abs(s[s < 0].sum())
    return gp / gl if gl > 0 else float("inf")


def enrich_with_or(trades, or_df):
    trades = trades.copy()
    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["weekday"] = trades["EntryTime"].dt.weekday
    trades["trade_date"] = trades["EntryTime"].dt.date
    trades["pnl_pct"] = trades["PnL"] / trades["EntryPrice"].abs() * 100
    trades = trades.merge(or_df[["date_key", "or_pct"]], left_on="trade_date", right_on="date_key", how="left")

    bins = [0, 0.3, 0.5, 0.7, 1.0, 99]
    labels = ["<0.3%", "0.3-0.5%", "0.5-0.7%", "0.7-1.0%", ">1.0%"]
    trades["or_bin"] = pd.cut(trades["or_pct"], bins=bins, labels=labels, right=False)
    return trades


def print_strategy_analysis(trades, strategy_name):
    print(f"\n{'=' * 80}")
    print(f"  {strategy_name} — OR% × Weekday（共 {len(trades)} 筆）")
    print(f"{'=' * 80}")

    for wd in range(5):
        wd_t = trades[trades["weekday"] == wd]
        name = WEEKDAY_NAMES[wd]
        print(f"\n  ── {name}（共 {len(wd_t)} 筆）──")
        print(f"  {'OR%區間':<12} {'筆數':>5} {'勝率':>7} {'PF':>6} {'平均損益':>9} {'總損益':>8}")
        print(f"  {'-' * 55}")

        for label in ["<0.3%", "0.3-0.5%", "0.5-0.7%", "0.7-1.0%", ">1.0%"]:
            sub = wd_t[wd_t["or_bin"] == label]
            if len(sub) == 0:
                print(f"  {label:<12}     0")
                continue
            wins = (sub["PnL"] > 0).sum()
            wr = wins / len(sub) * 100
            p = pf(sub["PnL"])
            ps = f"{p:.2f}" if p < 100 else "∞"
            print(f"  {label:<12} {len(sub):>5} {wr:>6.1f}% {ps:>6} {sub['PnL'].mean():>+9.1f} {sub['PnL'].sum():>+8.0f}")

        if len(wd_t) > 0:
            wins = (wd_t["PnL"] > 0).sum()
            wr = wins / len(wd_t) * 100
            p = pf(wd_t["PnL"])
            ps = f"{p:.2f}" if p < 100 else "∞"
            print(f"  {'-' * 55}")
            print(f"  {'Total':<12} {len(wd_t):>5} {wr:>6.1f}% {ps:>6} "
                  f"{wd_t['PnL'].mean():>+9.1f} {wd_t['PnL'].sum():>+8.0f}")

    # 最佳 OR% 門檻
    print(f"\n  ── 各星期最佳 OR% 下限掃描 ──")
    print(f"  {'星期':<6} {'最佳下限':>8} {'筆數':>5} {'勝率':>7} {'PF':>6} {'Avg':>8} {'Total':>8}  {'vs 無門檻'}")
    print(f"  {'-' * 75}")

    for wd in range(5):
        wd_t = trades[trades["weekday"] == wd]
        if len(wd_t) == 0:
            continue
        base_total = wd_t["PnL"].sum()
        best_pf = 0
        best_min = 0
        best_sub = None

        for min_pct in np.arange(0, 1.1, 0.1):
            sub = wd_t[wd_t["or_pct"] >= min_pct]
            if len(sub) < 5:
                continue
            p = pf(sub["PnL"])
            if p > best_pf:
                best_pf = p
                best_min = min_pct
                best_sub = sub

        if best_sub is not None:
            wins = (best_sub["PnL"] > 0).sum()
            wr = wins / len(best_sub) * 100
            p = pf(best_sub["PnL"])
            ps = f"{p:.2f}" if p < 100 else "∞"
            diff = best_sub["PnL"].sum() - base_total
            print(f"  {WEEKDAY_NAMES[wd]:<6} {best_min:>7.1f}% {len(best_sub):>5} {wr:>6.1f}% {ps:>6} "
                  f"{best_sub['PnL'].mean():>+8.1f} {best_sub['PnL'].sum():>+8.0f}  {diff:>+6.0f} pts")

    # 綜合：Mon-Wed vs Thu-Fri
    print(f"\n  ── Mon-Wed vs Thu-Fri ──")
    for label, wds in [("Mon-Wed", [0, 1, 2]), ("Thu-Fri", [3, 4])]:
        sub = trades[trades["weekday"].isin(wds)]
        if len(sub) == 0:
            continue
        wins = (sub["PnL"] > 0).sum()
        wr = wins / len(sub) * 100
        p = pf(sub["PnL"])
        print(f"  {label}: {len(sub)} 筆, WR {wr:.1f}%, PF {p:.2f}, "
              f"Avg {sub['PnL'].mean():+.1f}, Total {sub['PnL'].sum():+.0f}")


def main():
    or_df = get_daily_or()

    # ── ORBLong（無 OR% 門檻）──
    print("Loading ORBLong...")
    df1 = load_data_with_night_ma(start=START, end=END, trend_ma_days=10)
    bt1 = Backtest(df1, ORBLongStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats1 = bt1.run(
        long_only=1, sl_pct=0.004, tp_or_multiplier=1.5, or_min_width=20.0,
        trend_ma_days=10, or_pct_min=0.0, or_pct_max=99.0,
        force_exit_minute=300, skip_thursday=0, thu_or_pct_min=0.0,
    )
    orb_trades = enrich_with_or(stats1["_trades"], or_df)
    print_strategy_analysis(orb_trades, "ORBLong")

    # ── EstHL（無 weekday 跳過）──
    print("\nLoading EstHL...")
    df2 = load_data_for_orb_est_hl(start=START, end=END)
    bt2 = Backtest(df2, ORBWithEstHLExitStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats2 = bt2.run(
        long_only=True, skip_thursday=False, skip_friday=False,
        sl_ema_fraction=0.25, vwap_days=2,
    )
    est_trades = enrich_with_or(stats2["_trades"], or_df)
    print_strategy_analysis(est_trades, "EstHL")


if __name__ == "__main__":
    main()
