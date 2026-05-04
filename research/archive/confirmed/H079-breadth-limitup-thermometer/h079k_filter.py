"""H079-K: 把 RATIO defense filter 套到既有 live 策略 (S001/S002)

設計
----
1. 跑 live 策略 baseline → 取 trades CSV (EntryTime, ExitTime, PnL, ...)
2. 從 market_breadth 算每日 defense window（用 H079-C 最佳參數）
3. 把 entry_date 落在 defense window 的交易過濾掉
4. 比較 baseline vs filtered: 總 PnL、Sharpe、MaxDD、勝率

預設參數（H079-C 最佳，平衡選擇）
- logic = RATIO only
- ma = 7
- pct = 0.15
- consec = 3
- skip_n = 10
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"


def load_defense_window(start: date, end: date,
                        pct: float = 0.15, consec: int = 3,
                        skip_n: int = 10, ma: int = 7,
                        logic: str = "RATIO") -> pd.DataFrame:
    """Return DataFrame[trade_date, in_defense] using H079-C best params."""
    sql = """
    WITH b AS (
        SELECT trade_date,
               SUM(up_limit_count) AS up_limit_count,
               SUM(total_value)    AS total_value
        FROM market_breadth WHERE trade_date BETWEEN ? AND ?
        GROUP BY trade_date
    ),
    lv AS (
        SELECT trade_date,
               SUM(CASE WHEN is_limit_up THEN value ELSE 0 END) AS lu_value
        FROM stock_day WHERE trade_date BETWEEN ? AND ?
        GROUP BY trade_date
    )
    SELECT b.trade_date, b.up_limit_count, b.total_value, lv.lu_value
    FROM b LEFT JOIN lv USING (trade_date)
    ORDER BY b.trade_date
    """
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        df = conn.execute(sql, [start, end, start, end]).fetchdf()

    df["lu_value_ratio"] = df["lu_value"] / df["total_value"]
    cnt_ma = df["up_limit_count"].rolling(ma).mean()
    rat_ma = df["lu_value_ratio"].rolling(ma).mean()
    cnt_th = cnt_ma.quantile(pct)
    rat_th = rat_ma.quantile(pct)
    cond_c = cnt_ma < cnt_th
    cond_r = rat_ma < rat_th
    if logic == "AND":
        cond = cond_c & cond_r
    elif logic == "OR":
        cond = cond_c | cond_r
    elif logic == "CNT":
        cond = cond_c
    elif logic == "RATIO":
        cond = cond_r
    else:
        raise ValueError(logic)
    event = (cond.rolling(consec).sum() >= consec).fillna(False)
    df["in_defense"] = event.rolling(skip_n, min_periods=1).max().astype(bool)
    df["event"] = event
    return df[["trade_date", "in_defense", "event"]]


def perf(trades: pd.DataFrame) -> dict:
    if len(trades) == 0:
        return {"n": 0}
    pnl = trades["PnL"]
    ret = trades["ReturnPct"] * 100
    cum = pnl.cumsum()
    dd = cum - cum.cummax()
    sharpe = (ret.mean() / ret.std()) * np.sqrt(252) if ret.std() > 0 else 0
    return {
        "n": len(trades),
        "win_rate": (pnl > 0).mean(),
        "avg_pnl": pnl.mean(),
        "avg_ret_pct": ret.mean(),
        "total_pnl": pnl.sum(),
        "sharpe": sharpe,
        "max_dd": dd.min(),
        "best": pnl.max(),
        "worst": pnl.min(),
        "long_n": (trades["Size"] > 0).sum() if "Size" in trades.columns else 0,
        "short_n": (trades["Size"] < 0).sum() if "Size" in trades.columns else 0,
    }


def fmt(d: dict) -> str:
    if d["n"] == 0:
        return "no trades"
    return (f"n={d['n']:<4} (L={d['long_n']}/S={d['short_n']})  win={d['win_rate']:.1%}  "
            f"avg={d['avg_pnl']:+.1f}pts  total={d['total_pnl']:+.0f}pts  "
            f"Sharpe={d['sharpe']:.2f}  MaxDD={d['max_dd']:+.0f}pts  "
            f"best/worst={d['best']:+.0f}/{d['worst']:+.0f}")


def analyze(strategy_name: str, trades_csv: Path, defense_df: pd.DataFrame,
            oos_start: pd.Timestamp) -> None:
    print(f"\n{'='*100}")
    print(f"{strategy_name}: {trades_csv.name}")
    print('='*100)

    trades = pd.read_csv(trades_csv, parse_dates=["EntryTime", "ExitTime"])
    trades["entry_date"] = trades["EntryTime"].dt.normalize()

    # Merge defense flag
    defense_df = defense_df.copy()
    defense_df["trade_date"] = pd.to_datetime(defense_df["trade_date"])
    trades = trades.merge(defense_df[["trade_date", "in_defense"]],
                          left_on="entry_date", right_on="trade_date", how="left")
    trades["in_defense"] = trades["in_defense"].fillna(False)

    print(f"Total trades: {len(trades)}")
    print(f"Trades inside defense window: {trades['in_defense'].sum()} "
          f"({trades['in_defense'].mean()*100:.1f}%)")

    for split_name, mask in [
        ("Full", pd.Series(True, index=trades.index)),
        ("IS (<2024-01-01)", trades["entry_date"] < oos_start),
        ("OOS (>=2024-01-01)", trades["entry_date"] >= oos_start),
    ]:
        sub = trades[mask]
        if len(sub) == 0:
            continue
        baseline = sub
        filtered = sub[~sub["in_defense"]]
        skipped = sub[sub["in_defense"]]
        print(f"\n  --- {split_name} ---")
        print(f"  Baseline: {fmt(perf(baseline))}")
        print(f"  Filtered: {fmt(perf(filtered))}")
        print(f"  Skipped:  {fmt(perf(skipped))}")
        b = perf(baseline)
        f = perf(filtered)
        s = perf(skipped)
        if b["n"] > 0 and f["n"] > 0:
            d_pnl = f["total_pnl"] - b["total_pnl"]
            d_sharpe = f["sharpe"] - b["sharpe"]
            d_dd = f["max_dd"] - b["max_dd"]
            print(f"  Δ Filter vs Base: PnL {d_pnl:+.0f}pts, Sharpe {d_sharpe:+.2f}, MaxDD {d_dd:+.0f}pts")
            if s["n"] > 0:
                print(f"  跳掉 {s['n']} 筆，平均 {s['avg_pnl']:+.1f}pts/筆")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=date.fromisoformat, default=date(2021, 1, 1))
    p.add_argument("--end", type=date.fromisoformat, default=date(2026, 4, 30))
    p.add_argument("--oos-start", type=date.fromisoformat, default=date(2024, 1, 1))
    p.add_argument("--pct", type=float, default=0.15)
    p.add_argument("--consec", type=int, default=3)
    p.add_argument("--skip-n", type=int, default=10)
    p.add_argument("--ma", type=int, default=7)
    p.add_argument("--logic", default="RATIO", choices=["AND", "OR", "CNT", "RATIO"])
    p.add_argument("--strategies", nargs="+", default=[
        "output/s001_esthl_2021-01-01_2026-04-30.csv",
        "output/s002_reversal_2021-01-01_2026-04-30.csv",
    ])
    args = p.parse_args()

    print(f"Defense params: logic={args.logic}, ma={args.ma}, pct={args.pct}, "
          f"consec={args.consec}, skip_n={args.skip_n}")

    defense = load_defense_window(args.start, args.end,
                                   pct=args.pct, consec=args.consec,
                                   skip_n=args.skip_n, ma=args.ma, logic=args.logic)
    n_def = defense["in_defense"].sum()
    n_ev = defense["event"].sum()
    print(f"Defense window: {n_def} 天 / {len(defense)} 天 ({n_def/len(defense)*100:.1f}%)")
    print(f"Event days: {n_ev} 天")

    for s in args.strategies:
        path = PROJECT_ROOT / s
        if not path.exists():
            print(f"\n{path} 不存在，跳過")
            continue
        name = path.parent.name if path.parent != PROJECT_ROOT else path.stem
        analyze(name, path, defense, pd.Timestamp(args.oos_start))


if __name__ == "__main__":
    main()
