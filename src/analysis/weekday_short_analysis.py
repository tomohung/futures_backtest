"""
星期效應分析：做空交易（EstHL + ORBLong）

分別對兩策略跑全方向回測（long_only=False），分析做多/做空在各星期的表現。
核心問題：做空是否也受週四/五影響？是否存在「做多不利但做空反而有利」的星期效應？

用法: uv run python src/analysis/weekday_short_analysis.py
"""

import pandas as pd
from backtesting import Backtest

from src.backtest.runner import load_data_with_night_ma, load_data_for_orb_est_hl
from src.strategies.orb import ORBLongStrategy
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy

WEEKDAY_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
START = "2021-01-01"
END = "2026-03-02"


def run_orb_long_both_directions():
    """Run ORBLong with long_only=0, return trades DataFrame."""
    print("Loading data for ORBLong...")
    df = load_data_with_night_ma(start=START, end=END, trend_ma_days=10)
    print(f"  {len(df):,} bars  [{df.index[0]} → {df.index[-1]}]")

    bt = Backtest(df, ORBLongStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(
        long_only=0,
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
    return stats["_trades"].copy()


def run_est_hl_both_directions():
    """Run EstHL with long_only=False, skip_thu/fri=False, return trades DataFrame."""
    print("Loading data for EstHL...")
    df = load_data_for_orb_est_hl(start=START, end=END)
    print(f"  {len(df):,} bars  [{df.index[0]} → {df.index[-1]}]")

    bt = Backtest(df, ORBWithEstHLExitStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(
        long_only=False,
        skip_thursday=False,
        skip_friday=False,
        sl_ema_fraction=0.25,
        bigcost_days=2,
    )
    return stats["_trades"].copy()


def enrich_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Add direction, weekday, year, pnl_pct columns."""
    df = trades.copy()
    df["direction"] = df["Size"].apply(lambda s: "Long" if s > 0 else "Short")
    df["EntryTime"] = pd.to_datetime(df["EntryTime"])
    df["weekday"] = df["EntryTime"].dt.weekday
    df["weekday_name"] = df["weekday"].map(WEEKDAY_NAMES)
    df["year"] = df["EntryTime"].dt.year
    df["pnl_pct"] = df["PnL"] / df["EntryPrice"].abs() * 100
    return df


def print_direction_weekday_table(df: pd.DataFrame, strategy_name: str):
    """Print direction × weekday statistics table."""
    print(f"\n{'=' * 80}")
    print(f"  {strategy_name}  —  方向 × 星期分析  (共 {len(df)} 筆)")
    print(f"{'=' * 80}")

    for direction in ["Long", "Short"]:
        sub = df[df["direction"] == direction]
        if len(sub) == 0:
            print(f"\n  [{direction}] 無交易")
            continue

        print(f"\n  [{direction}]  共 {len(sub)} 筆")
        print(f"  {'星期':<6} {'筆數':>5} {'勝率':>7} {'平均損益':>10} {'總損益':>9} {'Avg損益%':>9}")
        print(f"  {'-' * 55}")

        for wd in range(5):
            name = WEEKDAY_NAMES[wd]
            ws = sub[sub["weekday"] == wd]
            if len(ws) == 0:
                print(f"  {name:<6} {'—':>5}")
                continue
            wins = (ws["PnL"] > 0).sum()
            wr = wins / len(ws) * 100
            avg_pnl = ws["PnL"].mean()
            total_pnl = ws["PnL"].sum()
            avg_pct = ws["pnl_pct"].mean()
            print(f"  {name:<6} {len(ws):>5} {wr:>6.1f}% {avg_pnl:>+10.1f} {total_pnl:>+9.0f} {avg_pct:>+8.3f}%")

        wins_all = (sub["PnL"] > 0).sum()
        print(f"  {'-' * 55}")
        print(f"  {'Total':<6} {len(sub):>5} {wins_all/len(sub)*100:>6.1f}% "
              f"{sub['PnL'].mean():>+10.1f} {sub['PnL'].sum():>+9.0f} {sub['pnl_pct'].mean():>+8.3f}%")


def print_year_weekday_direction_table(df: pd.DataFrame, strategy_name: str):
    """Print year × weekday cross-tab for each direction."""
    for direction in ["Long", "Short"]:
        sub = df[df["direction"] == direction]
        if len(sub) == 0:
            continue

        print(f"\n  {strategy_name} [{direction}] — 年度 × 星期 總損益")
        print(f"  {'年份':<6}", end="")
        for wd in range(5):
            print(f"  {WEEKDAY_NAMES[wd]:>7}", end="")
        print(f"  {'Total':>7}")
        print(f"  {'-' * 55}")

        for year, ydf in sub.groupby("year"):
            print(f"  {year:<6}", end="")
            for wd in range(5):
                ws = ydf[ydf["weekday"] == wd]
                total = ws["PnL"].sum() if len(ws) > 0 else 0
                print(f"  {total:>+7.0f}", end="")
            print(f"  {ydf['PnL'].sum():>+7.0f}")


def print_thu_fri_focus(df: pd.DataFrame, strategy_name: str):
    """Focused comparison: Thu/Fri Long vs Short."""
    print(f"\n{'=' * 80}")
    print(f"  {strategy_name}  —  週四/五 做多 vs 做空 焦點比較")
    print(f"{'=' * 80}")
    print(f"  {'星期':<6} {'方向':<7} {'筆數':>5} {'勝率':>7} {'平均損益':>10} {'總損益':>9}")
    print(f"  {'-' * 55}")

    for wd, name in [(3, "Thu"), (4, "Fri")]:
        for direction in ["Long", "Short"]:
            ws = df[(df["weekday"] == wd) & (df["direction"] == direction)]
            if len(ws) == 0:
                print(f"  {name:<6} {direction:<7} {'—':>5}")
                continue
            wins = (ws["PnL"] > 0).sum()
            wr = wins / len(ws) * 100
            print(f"  {name:<6} {direction:<7} {len(ws):>5} {wr:>6.1f}% "
                  f"{ws['PnL'].mean():>+10.1f} {ws['PnL'].sum():>+9.0f}")


def main():
    # ── ORBLong ──
    orb_trades = run_orb_long_both_directions()
    orb_df = enrich_trades(orb_trades)
    print_direction_weekday_table(orb_df, "ORBLong")
    print_year_weekday_direction_table(orb_df, "ORBLong")
    print_thu_fri_focus(orb_df, "ORBLong")

    print("\n" + "═" * 80)

    # ── EstHL ──
    est_trades = run_est_hl_both_directions()
    est_df = enrich_trades(est_trades)
    print_direction_weekday_table(est_df, "EstHL")
    print_year_weekday_direction_table(est_df, "EstHL")
    print_thu_fri_focus(est_df, "EstHL")

    # ── Summary ──
    print(f"\n{'═' * 80}")
    print("  綜合結論")
    print(f"{'═' * 80}")
    for name, df in [("ORBLong", orb_df), ("EstHL", est_df)]:
        for direction in ["Long", "Short"]:
            sub = df[df["direction"] == direction]
            if len(sub) == 0:
                continue
            thu_fri = sub[sub["weekday"].isin([3, 4])]
            other = sub[~sub["weekday"].isin([3, 4])]
            if len(thu_fri) > 0 and len(other) > 0:
                print(f"\n  {name} [{direction}]:")
                print(f"    Mon-Wed: {len(other)} 筆, WR {(other['PnL']>0).mean()*100:.1f}%, "
                      f"Avg {other['PnL'].mean():+.1f} pts, Total {other['PnL'].sum():+.0f}")
                print(f"    Thu-Fri: {len(thu_fri)} 筆, WR {(thu_fri['PnL']>0).mean()*100:.1f}%, "
                      f"Avg {thu_fri['PnL'].mean():+.1f} pts, Total {thu_fri['PnL'].sum():+.0f}")


if __name__ == "__main__":
    main()
