"""
月結算週三：做多 vs 做空分析

用法: uv run python src/analysis/settle_wed_direction.py
"""
import pandas as pd
from backtesting import Backtest

from src.backtest.runner import load_data_with_night_ma, load_data_for_orb_est_hl
from src.strategies.orb import ORBLongStrategy
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy

WEEKDAY_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
START = "2021-01-01"
END = "2026-03-14"


def third_wednesdays(year_start=2021, year_end=2026):
    dates = set()
    for y in range(year_start, year_end + 1):
        for m in range(1, 13):
            d = pd.Timestamp(y, m, 1)
            first_wed = d + pd.DateOffset(weekday=2)
            if first_wed.month != m:
                first_wed += pd.DateOffset(weeks=1)
            third_wed = first_wed + pd.DateOffset(weeks=2)
            dates.add(third_wed.date())
    return dates


SETTLE_DATES = third_wednesdays()


def enrich(trades):
    df = trades.copy()
    df["direction"] = df["Size"].apply(lambda s: "Long" if s > 0 else "Short")
    df["EntryTime"] = pd.to_datetime(df["EntryTime"])
    df["weekday"] = df["EntryTime"].dt.weekday
    df["year"] = df["EntryTime"].dt.year
    df["trade_date"] = df["EntryTime"].dt.date
    df["is_settle"] = df["trade_date"].apply(lambda d: d in SETTLE_DATES)
    df["pnl_pct"] = df["PnL"] / df["EntryPrice"].abs() * 100
    return df


def pf(s):
    gp = s[s > 0].sum()
    gl = abs(s[s < 0].sum())
    return gp / gl if gl > 0 else float("inf")


def print_group(label, sub):
    if len(sub) == 0:
        print(f"  {label:<20} —")
        return
    wins = (sub["PnL"] > 0).sum()
    wr = wins / len(sub) * 100
    p = pf(sub["PnL"])
    ps = f"{p:.2f}" if p < 100 else "∞"
    print(f"  {label:<20} {len(sub):>4} 筆  WR {wr:>5.1f}%  PF {ps:>5}  "
          f"Avg {sub['PnL'].mean():>+7.1f}  Total {sub['PnL'].sum():>+7.0f}")


def analyze(name, trades_df):
    df = enrich(trades_df)
    wed = df[df["weekday"] == 2]
    settle = wed[wed["is_settle"]]
    normal = wed[~wed["is_settle"]]

    print(f"\n{'=' * 80}")
    print(f"  {name}（雙向）— 週三分析")
    print(f"{'=' * 80}")

    print(f"\n  ── 普通週三 ──")
    print_group("Long", normal[normal["direction"] == "Long"])
    print_group("Short", normal[normal["direction"] == "Short"])

    print(f"\n  ── 月結算週三 ──")
    print_group("Long", settle[settle["direction"] == "Long"])
    print_group("Short", settle[settle["direction"] == "Short"])

    print(f"\n  ── 非週三（參考） ──")
    non_wed = df[df["weekday"] != 2]
    print_group("Long", non_wed[non_wed["direction"] == "Long"])
    print_group("Short", non_wed[non_wed["direction"] == "Short"])

    # 逐年月結算週三明細
    print(f"\n  ── 月結算週三逐筆 ──")
    print(f"  {'日期':<12} {'方向':<6} {'Entry':>7} {'Exit':>7} {'PnL':>7} {'PnL%':>7}")
    print(f"  {'-' * 55}")
    for _, row in settle.sort_values("EntryTime").iterrows():
        print(f"  {str(row['trade_date']):<12} {row['direction']:<6} "
              f"{row['EntryPrice']:>7.0f} {row['ExitPrice']:>7.0f} "
              f"{row['PnL']:>+7.0f} {row['pnl_pct']:>+6.3f}%")


def main():
    # ORBLong 雙向
    print("Loading ORBLong (bidirectional)...")
    df1 = load_data_with_night_ma(start=START, end=END, trend_ma_days=10)
    bt1 = Backtest(df1, ORBLongStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats1 = bt1.run(
        long_only=0, sl_pct=0.004, tp_or_multiplier=1.5, or_min_width=20.0,
        trend_ma_days=10, or_pct_min=0.3, or_pct_max=1.0,
        force_exit_minute=300, skip_thursday=0, thu_or_pct_min=0.0,
    )
    analyze("ORBLong", stats1["_trades"])

    # EstHL 雙向
    print("\nLoading EstHL (bidirectional)...")
    df2 = load_data_for_orb_est_hl(start=START, end=END)
    bt2 = Backtest(df2, ORBWithEstHLExitStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats2 = bt2.run(
        long_only=False, skip_thursday=False, skip_friday=False,
        sl_ema_fraction=0.25, bigcost_days=2,
    )
    analyze("EstHL", stats2["_trades"])


if __name__ == "__main__":
    main()
