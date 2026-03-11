"""
sweep_force_exit.py — 掃描 ORBLongStrategy 強制出場時間的影響

測試 force_exit_minute = 300/315/330/340/345
（對應 13:00 / 13:15 / 13:30 / 13:40 / 13:45）

固定其他參數：
    sl_pct=0.004, tp_or_multiplier=1.5, or_min_width=20,
    trend_ma_days=10, or_pct_min=0.3, or_pct_max=1.0

Usage:
    uv run python src/backtest/sweep_force_exit.py --start 2021-01-01
"""

import argparse

import numpy as np
import pandas as pd
from backtesting import Backtest

from src.backtest.runner import load_data_with_night_ma
from src.strategies.orb import ORBLongStrategy

# force_exit_minute → label
CANDIDATES = {
    210: "11:30",
    240: "12:00",
    270: "12:30",
    300: "13:00",
    330: "13:30 (baseline)",
    345: "13:45",
}

BASE_PARAMS = dict(
    sl_pct=0.004,
    tp_or_multiplier=1.5,
    or_min_width=20.0,
    trend_ma_days=10,
    or_pct_min=0.3,
    or_pct_max=1.0,
)


def year_pnl(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {}
    t = trades.copy()
    t["year"] = pd.to_datetime(t["ExitTime"]).dt.year
    return t.groupby("year")["PnL"].sum().to_dict()


def sharpe(trades: pd.DataFrame, equity_curve: pd.Series) -> float:
    """年化 Sharpe（基於日 PnL%）。"""
    if trades.empty:
        return float("nan")
    t = trades.copy()
    t["exit_date"] = pd.to_datetime(t["ExitTime"]).dt.date
    t["entry_price"] = t["EntryPrice"]
    t["pnl_pct"] = t["PnL"] / t["entry_price"] * 100
    daily = t.groupby("exit_date")["pnl_pct"].sum()
    if daily.std() == 0:
        return float("nan")
    return daily.mean() / daily.std() * (248 ** 0.5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end",   default=None)
    args = parser.parse_args()

    print(f"載入資料 {args.start} ~ {args.end or 'latest'} ...")
    df = load_data_with_night_ma(
        start=args.start,
        end=args.end,
        trend_ma_days=BASE_PARAMS["trend_ma_days"],
    )

    years = sorted(df.index.year.unique())
    rows = []

    for fe_min, label in CANDIDATES.items():
        params = {**BASE_PARAMS, "force_exit_minute": fe_min}
        bt = Backtest(df, ORBLongStrategy, cash=10_000_000, commission=0)
        stats = bt.run(**params)
        trades = stats["_trades"]
        yp = year_pnl(trades)
        sh = sharpe(trades, stats["_equity_curve"]["Equity"])

        row = {
            "強制出場": label,
            "交易數": len(trades),
            "Sharpe": round(sh, 2),
            "合計": int(trades["PnL"].sum()) if not trades.empty else 0,
        }
        for y in years:
            row[str(y)] = int(yp.get(y, 0))
        rows.append(row)
        print(f"  {label:20s}  trades={row['交易數']:3d}  sharpe={sh:.2f}  total={row['合計']:+,}")

    df_out = pd.DataFrame(rows)
    print()
    print(df_out.to_markdown(index=False))


if __name__ == "__main__":
    main()
