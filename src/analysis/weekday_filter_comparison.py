"""
Weekday filter 方案比較回測

ORBLong 方案：
  A) 現行：thu_or_pct_min=0.7, or_pct 0.3-1.0
  B) skip_thursday=True
  C) skip_thursday=True + 月結算週三跳過（手動 post-filter）

EstHL 方案：
  A) 現行：skip_thu=True, skip_fri=True
  B) 現行 + 月結算週三跳過（手動 post-filter）
  C) 不跳 Thu/Fri（baseline，看少了多少）

用法: uv run python src/analysis/weekday_filter_comparison.py
"""
import numpy as np
import pandas as pd
from backtesting import Backtest

from src.backtest.runner import load_data_with_night_ma, load_data_for_orb_est_hl
from src.strategies.orb import ORBLongStrategy
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy

START = "2021-01-01"
END = "2026-03-14"
YEARS = range(2021, 2027)


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
    df["EntryTime"] = pd.to_datetime(df["EntryTime"])
    df["trade_date"] = df["EntryTime"].dt.date
    df["year"] = df["EntryTime"].dt.year
    df["weekday"] = df["EntryTime"].dt.weekday
    df["is_settle_wed"] = df["trade_date"].apply(lambda d: d in SETTLE_DATES)
    return df


def calc_stats(df):
    if len(df) == 0:
        return {"n": 0, "wr": 0, "pf": 0, "total": 0, "avg": 0, "sharpe": 0}
    wins = (df["PnL"] > 0).sum()
    wr = wins / len(df) * 100
    gp = df["PnL"][df["PnL"] > 0].sum()
    gl = abs(df["PnL"][df["PnL"] < 0].sum())
    pf_ = gp / gl if gl > 0 else float("inf")

    # Daily PnL for Sharpe
    daily = df.groupby("trade_date")["PnL"].sum()
    sharpe = daily.mean() / daily.std() * np.sqrt(252) if daily.std() > 0 else 0

    return {
        "n": len(df), "wr": wr, "pf": pf_,
        "total": df["PnL"].sum(), "avg": df["PnL"].mean(),
        "sharpe": sharpe,
    }


def print_comparison(label, stats):
    pf_str = f"{stats['pf']:.2f}" if stats['pf'] < 100 else "∞"
    print(f"  {label:<45} {stats['n']:>4} 筆  WR {stats['wr']:>5.1f}%  PF {pf_str:>5}  "
          f"Avg {stats['avg']:>+7.1f}  Total {stats['total']:>+7.0f}  Sharpe {stats['sharpe']:>5.2f}")


def print_yearly(label, df):
    print(f"\n  {label} — 年度損益")
    print(f"  {'年份':<6}", end="")
    for y in YEARS:
        print(f"  {y:>7}", end="")
    print(f"  {'Total':>7}")
    print(f"  {'-' * 60}")
    print(f"  {'':>6}", end="")
    for y in YEARS:
        yd = df[df["year"] == y]
        print(f"  {yd['PnL'].sum():>+7.0f}", end="")
    print(f"  {df['PnL'].sum():>+7.0f}")


def main():
    # ════════════════════════════════════════════════
    #  ORBLong
    # ════════════════════════════════════════════════
    print("Loading ORBLong data...")
    df_orb = load_data_with_night_ma(start=START, end=END, trend_ma_days=10)

    common_orb = dict(
        long_only=1, sl_pct=0.004, tp_or_multiplier=1.5, or_min_width=20.0,
        trend_ma_days=10, force_exit_minute=300,
    )

    # A) 現行：or_pct 0.3-1.0 + thu_or_pct_min=0.7
    bt = Backtest(df_orb, ORBLongStrategy, cash=200_000, commission=0.0, trade_on_close=True)
    stats_a = bt.run(**common_orb, or_pct_min=0.3, or_pct_max=1.0,
                     skip_thursday=0, thu_or_pct_min=0.7)
    trades_a = enrich(stats_a["_trades"])

    # B) or_pct 0.3-1.0 + skip_thursday=True
    stats_b = bt.run(**common_orb, or_pct_min=0.3, or_pct_max=1.0,
                     skip_thursday=1, thu_or_pct_min=0.0)
    trades_b = enrich(stats_b["_trades"])

    # C) B + 月結算週三跳過
    trades_c = trades_b[~trades_b["is_settle_wed"]].copy()

    # D) skip_thu + skip_fri (aggressive)
    stats_d_base = bt.run(**common_orb, or_pct_min=0.3, or_pct_max=1.0,
                          skip_thursday=1, thu_or_pct_min=0.0)
    trades_d = enrich(stats_d_base["_trades"])
    trades_d = trades_d[trades_d["weekday"] != 4].copy()  # also skip Fri

    # E) no filters baseline
    stats_e = bt.run(**common_orb, or_pct_min=0.0, or_pct_max=99.0,
                     skip_thursday=0, thu_or_pct_min=0.0)
    trades_e = enrich(stats_e["_trades"])

    print(f"\n{'=' * 100}")
    print(f"  ORBLong — Weekday Filter 方案比較")
    print(f"{'=' * 100}\n")

    scenarios_orb = [
        ("E) 無任何濾網 (baseline)", trades_e),
        ("A) 現行: OR% 0.3-1.0 + thu_or_pct≥0.7", trades_a),
        ("B) OR% 0.3-1.0 + skip_thursday", trades_b),
        ("C) B + 月結算週三跳過", trades_c),
        ("D) B + skip_friday (激進)", trades_d),
    ]

    for label, t in scenarios_orb:
        print_comparison(label, calc_stats(t))

    for label, t in scenarios_orb:
        print_yearly(label, t)

    # ════════════════════════════════════════════════
    #  EstHL
    # ════════════════════════════════════════════════
    print(f"\n\nLoading EstHL data...")
    df_est = load_data_for_orb_est_hl(start=START, end=END)
    bt2 = Backtest(df_est, ORBWithEstHLExitStrategy, cash=200_000, commission=0.0, trade_on_close=True)

    common_est = dict(long_only=True, sl_ema_fraction=0.25, bigcost_days=2)

    # A) 現行：skip_thu + skip_fri
    stats_ea = bt2.run(**common_est, skip_thursday=True, skip_friday=True)
    trades_ea = enrich(stats_ea["_trades"])

    # B) 現行 + 月結算週三跳過
    trades_eb = trades_ea[~trades_ea["is_settle_wed"]].copy()

    # C) 無 weekday filter (baseline)
    stats_ec = bt2.run(**common_est, skip_thursday=False, skip_friday=False)
    trades_ec = enrich(stats_ec["_trades"])

    # D) skip_thu only (不跳 Fri)
    stats_ed = bt2.run(**common_est, skip_thursday=True, skip_friday=False)
    trades_ed = enrich(stats_ed["_trades"])

    print(f"\n{'=' * 100}")
    print(f"  EstHL — Weekday Filter 方案比較")
    print(f"{'=' * 100}\n")

    scenarios_est = [
        ("C) 無 weekday filter (baseline)", trades_ec),
        ("D) skip_thursday only", trades_ed),
        ("A) 現行: skip_thu + skip_fri", trades_ea),
        ("B) A + 月結算週三跳過", trades_eb),
    ]

    for label, t in scenarios_est:
        print_comparison(label, calc_stats(t))

    for label, t in scenarios_est:
        print_yearly(label, t)


if __name__ == "__main__":
    main()
