"""
星期效應深度分析：ORBLong + EstHL

包含：
1. 各星期績效統計（勝率、PF、平均損益%）
2. 年度 × 星期 熱力圖
3. 結算日效應（普通週三 vs 月結算週三）
4. 日盤波動 × 星期（from raw data）
5. 週五結算（2025/12 後）前後比較

用法: uv run python src/analysis/weekday_deep_analysis.py
"""

import duckdb
import numpy as np
import pandas as pd
from backtesting import Backtest
from pathlib import Path

from src.backtest.runner import load_data_with_night_ma, load_data_for_orb_est_hl
from src.strategies.orb import ORBLongStrategy
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy

DB_PATH = "data/futures.duckdb"
WEEKDAY_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
START = "2021-01-01"
END = "2026-03-14"


def third_wednesdays(year_start=2021, year_end=2026):
    """計算所有第三個週三（台指結算日）"""
    dates = set()
    for y in range(year_start, year_end + 1):
        for m in range(1, 13):
            # 找第三個週三
            d = pd.Timestamp(y, m, 1)
            # 第一個週三
            first_wed = d + pd.DateOffset(weekday=2)  # 0=Mon, 2=Wed
            if first_wed.month != m:
                first_wed += pd.DateOffset(weeks=1)
            third_wed = first_wed + pd.DateOffset(weeks=2)
            dates.add(third_wed.date())
    return dates


def enrich_trades(trades: pd.DataFrame) -> pd.DataFrame:
    df = trades.copy()
    df["direction"] = df["Size"].apply(lambda s: "Long" if s > 0 else "Short")
    df["EntryTime"] = pd.to_datetime(df["EntryTime"])
    df["weekday"] = df["EntryTime"].dt.weekday
    df["weekday_name"] = df["weekday"].map(WEEKDAY_NAMES)
    df["year"] = df["EntryTime"].dt.year
    df["pnl_pct"] = df["PnL"] / df["EntryPrice"].abs() * 100
    df["trade_date"] = df["EntryTime"].dt.date

    # 標記結算日
    settle_dates = third_wednesdays()
    df["is_monthly_settle"] = df["trade_date"].apply(lambda d: d in settle_dates)
    df["is_wed"] = df["weekday"] == 2

    return df


def run_orb_long():
    print("Loading ORBLong data...")
    df = load_data_with_night_ma(start=START, end=END, trend_ma_days=10)
    bt = Backtest(df, ORBLongStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(
        long_only=1,
        sl_pct=0.004,
        tp_or_multiplier=1.5,
        or_min_width=20.0,
        trend_ma_days=10,
        or_pct_min=0.3,
        or_pct_max=1.0,
        force_exit_minute=300,
        skip_thursday=0,
        thu_or_pct_min=0.0,
    )
    return enrich_trades(stats["_trades"])


def run_est_hl():
    print("Loading EstHL data...")
    df = load_data_for_orb_est_hl(start=START, end=END)
    bt = Backtest(df, ORBWithEstHLExitStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(
        long_only=True,
        skip_thursday=False,
        skip_friday=False,
        sl_ema_fraction=0.25,
        vwap_days=2,
    )
    return enrich_trades(stats["_trades"])


def get_daily_range_by_weekday():
    """從 raw data 取日盤波動（High-Low），按星期分組"""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        rows = conn.execute("""
            SELECT
                timestamp::DATE AS trade_date,
                MAX(high) - MIN(low) AS range_pt,
                MAX(high)::INT AS day_high,
                MIN(low)::INT AS day_low,
                FIRST(open ORDER BY timestamp)::INT AS day_open
            FROM ohlcv_1m
            WHERE symbol = 'TX'
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
              AND timestamp::DATE >= ?
            GROUP BY trade_date
            ORDER BY trade_date
        """, [START]).fetchall()

    df = pd.DataFrame(rows, columns=["date", "range_pt", "high", "low", "open"])
    df["date"] = pd.to_datetime(df["date"])
    for col in ["range_pt", "high", "low", "open"]:
        df[col] = df[col].astype(float)
    df["weekday"] = df["date"].dt.weekday
    df["range_pct"] = df["range_pt"] / df["open"] * 100
    df["year"] = df["date"].dt.year
    return df


def calc_pf(pnl_series):
    gross_profit = pnl_series[pnl_series > 0].sum()
    gross_loss = abs(pnl_series[pnl_series < 0].sum())
    return gross_profit / gross_loss if gross_loss > 0 else float("inf")


def print_weekday_stats(df, strategy_name):
    """核心：各星期績效表"""
    print(f"\n{'=' * 90}")
    print(f"  {strategy_name}  —  星期績效分析（{START} ~ {END}，共 {len(df)} 筆）")
    print(f"{'=' * 90}")

    header = f"  {'星期':<6} {'筆數':>5} {'勝率':>7} {'PF':>6} {'平均損益':>9} {'平均損益%':>9} {'總損益':>8} {'最大獲利':>8} {'最大虧損':>8}"
    print(header)
    print(f"  {'-' * len(header)}")

    for wd in range(5):
        name = WEEKDAY_NAMES[wd]
        ws = df[df["weekday"] == wd]
        if len(ws) == 0:
            print(f"  {name:<6} {'—':>5}")
            continue

        wins = (ws["PnL"] > 0).sum()
        wr = wins / len(ws) * 100
        pf = calc_pf(ws["PnL"])
        avg_pnl = ws["PnL"].mean()
        avg_pct = ws["pnl_pct"].mean()
        total_pnl = ws["PnL"].sum()
        max_win = ws["PnL"].max()
        max_loss = ws["PnL"].min()
        pf_str = f"{pf:.2f}" if pf < 100 else "∞"

        print(f"  {name:<6} {len(ws):>5} {wr:>6.1f}% {pf_str:>6} {avg_pnl:>+9.1f} {avg_pct:>+8.3f}% {total_pnl:>+8.0f} {max_win:>+8.0f} {max_loss:>+8.0f}")

    # Total
    wins_all = (df["PnL"] > 0).sum()
    pf_all = calc_pf(df["PnL"])
    print(f"  {'-' * len(header)}")
    print(f"  {'Total':<6} {len(df):>5} {wins_all/len(df)*100:>6.1f}% {pf_all:>6.2f} "
          f"{df['PnL'].mean():>+9.1f} {df['pnl_pct'].mean():>+8.3f}% {df['PnL'].sum():>+8.0f}")


def print_year_weekday_table(df, strategy_name):
    """年度 × 星期 損益交叉表"""
    print(f"\n  {strategy_name} — 年度 × 星期 總損益（pts）")
    print(f"  {'年份':<6}", end="")
    for wd in range(5):
        print(f"  {WEEKDAY_NAMES[wd]:>7}", end="")
    print(f"  {'Total':>7}")
    print(f"  {'-' * 55}")

    for year in sorted(df["year"].unique()):
        ydf = df[df["year"] == year]
        print(f"  {year:<6}", end="")
        for wd in range(5):
            ws = ydf[ydf["weekday"] == wd]
            total = ws["PnL"].sum() if len(ws) > 0 else 0
            print(f"  {total:>+7.0f}", end="")
        print(f"  {ydf['PnL'].sum():>+7.0f}")


def print_year_weekday_wr_table(df, strategy_name):
    """年度 × 星期 勝率交叉表"""
    print(f"\n  {strategy_name} — 年度 × 星期 勝率")
    print(f"  {'年份':<6}", end="")
    for wd in range(5):
        print(f"  {WEEKDAY_NAMES[wd]:>7}", end="")
    print(f"  {'Total':>7}")
    print(f"  {'-' * 55}")

    for year in sorted(df["year"].unique()):
        ydf = df[df["year"] == year]
        print(f"  {year:<6}", end="")
        for wd in range(5):
            ws = ydf[ydf["weekday"] == wd]
            if len(ws) > 0:
                wr = (ws["PnL"] > 0).sum() / len(ws) * 100
                print(f"  {wr:>6.0f}%", end="")
            else:
                print(f"  {'—':>7}", end="")
        wr_all = (ydf["PnL"] > 0).sum() / len(ydf) * 100
        print(f"  {wr_all:>6.0f}%")


def print_settlement_analysis(df, strategy_name):
    """結算日效應：普通週三 vs 月結算週三"""
    print(f"\n{'=' * 90}")
    print(f"  {strategy_name}  —  結算日效應")
    print(f"{'=' * 90}")

    wed = df[df["is_wed"]]
    settle_wed = wed[wed["is_monthly_settle"]]
    normal_wed = wed[~wed["is_monthly_settle"]]

    print(f"\n  {'類型':<16} {'筆數':>5} {'勝率':>7} {'PF':>6} {'平均損益':>9} {'總損益':>8}")
    print(f"  {'-' * 60}")

    for label, sub in [("普通週三", normal_wed), ("月結算週三", settle_wed), ("非週三", df[~df["is_wed"]])]:
        if len(sub) == 0:
            print(f"  {label:<16} {'—':>5}")
            continue
        wins = (sub["PnL"] > 0).sum()
        wr = wins / len(sub) * 100
        pf = calc_pf(sub["PnL"])
        pf_str = f"{pf:.2f}" if pf < 100 else "∞"
        print(f"  {label:<16} {len(sub):>5} {wr:>6.1f}% {pf_str:>6} {sub['PnL'].mean():>+9.1f} {sub['PnL'].sum():>+8.0f}")


def print_daily_range_analysis(range_df):
    """日盤波動 × 星期"""
    print(f"\n{'=' * 90}")
    print(f"  日盤波動（High - Low）× 星期  ({START} ~)")
    print(f"{'=' * 90}")

    print(f"\n  {'星期':<6} {'天數':>5} {'平均波動':>8} {'平均波動%':>9} {'中位數':>7} {'StdDev':>7} {'最大':>7} {'最小':>7}")
    print(f"  {'-' * 70}")

    for wd in range(5):
        name = WEEKDAY_NAMES[wd]
        ws = range_df[range_df["weekday"] == wd]
        if len(ws) == 0:
            continue
        print(f"  {name:<6} {len(ws):>5} {ws['range_pt'].mean():>8.0f} {ws['range_pct'].mean():>8.2f}% "
              f"{ws['range_pt'].median():>7.0f} {ws['range_pt'].std():>7.0f} "
              f"{ws['range_pt'].max():>7.0f} {ws['range_pt'].min():>7.0f}")

    print(f"  {'-' * 70}")
    print(f"  {'Total':<6} {len(range_df):>5} {range_df['range_pt'].mean():>8.0f} "
          f"{range_df['range_pct'].mean():>8.2f}% {range_df['range_pt'].median():>7.0f}")

    # 年度 × 星期 波動
    print(f"\n  年度 × 星期 平均波動（pts）")
    print(f"  {'年份':<6}", end="")
    for wd in range(5):
        print(f"  {WEEKDAY_NAMES[wd]:>7}", end="")
    print(f"  {'Total':>7}")
    print(f"  {'-' * 55}")

    for year in sorted(range_df["year"].unique()):
        ydf = range_df[range_df["year"] == year]
        print(f"  {year:<6}", end="")
        for wd in range(5):
            ws = ydf[ydf["weekday"] == wd]
            if len(ws) > 0:
                print(f"  {ws['range_pt'].mean():>7.0f}", end="")
            else:
                print(f"  {'—':>7}", end="")
        print(f"  {ydf['range_pt'].mean():>7.0f}")


def print_mon_wed_fri_deep(df, strategy_name):
    """深入：Mon/Wed/Fri 特殊日的細分"""
    print(f"\n{'=' * 90}")
    print(f"  {strategy_name}  —  特殊日細分")
    print(f"{'=' * 90}")

    # 週一：跳空大小 vs 績效
    mon = df[df["weekday"] == 0].copy()
    if len(mon) > 0:
        print(f"\n  [週一] 共 {len(mon)} 筆")
        # 用 EntryPrice 與前一日的關係太複雜，這裡簡化為上半年/下半年比較
        for year in sorted(mon["year"].unique()):
            ym = mon[mon["year"] == year]
            if len(ym) > 0:
                wr = (ym["PnL"] > 0).sum() / len(ym) * 100
                print(f"    {year}: {len(ym)} 筆, WR {wr:.0f}%, Avg {ym['PnL'].mean():+.0f}, Total {ym['PnL'].sum():+.0f}")


def main():
    # ── 1. 日盤波動 ──
    print("=" * 90)
    print("  PART 1：日盤波動 × 星期")
    print("=" * 90)
    range_df = get_daily_range_by_weekday()
    print_daily_range_analysis(range_df)

    # ── 2. ORBLong ──
    print("\n\n")
    print("=" * 90)
    print("  PART 2：ORBLong 策略（long-only，無 weekday filter）")
    print("=" * 90)
    orb_df = run_orb_long()
    print_weekday_stats(orb_df, "ORBLong")
    print_year_weekday_table(orb_df, "ORBLong")
    print_year_weekday_wr_table(orb_df, "ORBLong")
    print_settlement_analysis(orb_df, "ORBLong")

    # ── 3. EstHL ──
    print("\n\n")
    print("=" * 90)
    print("  PART 3：EstHL 策略（long-only，無 weekday filter）")
    print("=" * 90)
    est_df = run_est_hl()
    print_weekday_stats(est_df, "EstHL")
    print_year_weekday_table(est_df, "EstHL")
    print_year_weekday_wr_table(est_df, "EstHL")
    print_settlement_analysis(est_df, "EstHL")

    # ── 4. 綜合比較 ──
    print(f"\n\n{'=' * 90}")
    print("  PART 4：綜合比較 — Mon~Wed vs Thu~Fri")
    print(f"{'=' * 90}")

    for name, tdf in [("ORBLong", orb_df), ("EstHL", est_df)]:
        mw = tdf[tdf["weekday"].isin([0, 1, 2])]
        tf = tdf[tdf["weekday"].isin([3, 4])]
        print(f"\n  {name}:")
        for label, sub in [("Mon-Wed", mw), ("Thu-Fri", tf)]:
            if len(sub) == 0:
                continue
            wins = (sub["PnL"] > 0).sum()
            wr = wins / len(sub) * 100
            pf = calc_pf(sub["PnL"])
            print(f"    {label}: {len(sub)} 筆, WR {wr:.1f}%, PF {pf:.2f}, "
                  f"Avg {sub['PnL'].mean():+.1f} pts ({sub['pnl_pct'].mean():+.3f}%), "
                  f"Total {sub['PnL'].sum():+.0f}")


if __name__ == "__main__":
    main()
