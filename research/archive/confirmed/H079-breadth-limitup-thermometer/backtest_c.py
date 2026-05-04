"""H079-C Phase 2 Backtest — 漲停萎縮事件作為大跌警報

Hypothesis (回顧)
------------------
當 lu_cnt_ma7 與 lu_ratio_ma7 同時 < 全期 X 分位數，並持續 N 天 →
未來 20 日內出現「單日跌 > -2%」或「累積跌 > -5%」的機率顯著高於基準。

兩個策略
--------
C-defense（防禦型）：
    Baseline: Always-long 日盤（每日 08:45 多單 → 13:45 平倉）
    防禦版: 萎縮事件觸發後 N 天內不開新多單
    比較: 累積報酬、最大回撤、Sharpe、避開的單日大跌次數

C-short（進攻型）：
    進場: 事件觸發日 → 隔日 08:45 開盤做空（連續合約 adj_open）
    出場: 持倉 N 天後 13:45 收盤平倉（adj_close）
    比較: vs random short / vs short on every day
    兩種模式: Overlap（每事件一筆，可重疊） + Sequential（單部位）

參數掃描
--------
- pct ∈ {0.10, 0.15, 0.20}
- consec ∈ {3, 5}
- N (defense skip / short hold) ∈ {10, 20, 30, 40, 50, 60}
"""

from __future__ import annotations

import argparse
import itertools
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"
RESULT_DIR = Path(__file__).parent / "results"

ROUND_TRIP_COST = 6.0


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

DAILY_SQL = """
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
),
tx AS (
    SELECT timestamp::DATE AS trade_date,
           FIRST(open  ORDER BY timestamp)               AS raw_open,
           LAST(close  ORDER BY timestamp)               AS raw_close,
           MAX(high)                                     AS raw_high,
           MIN(low)                                      AS raw_low,
           FIRST(open  + adjustment ORDER BY timestamp)  AS adj_open,
           LAST(close  + adjustment ORDER BY timestamp)  AS adj_close
    FROM ohlcv_1m
    WHERE symbol = 'TX'
      AND timestamp::DATE BETWEEN ? AND ?
      AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
    GROUP BY trade_date
)
SELECT b.trade_date, b.up_limit_count, b.total_value, lv.lu_value,
       tx.raw_open, tx.raw_close, tx.raw_high, tx.raw_low,
       tx.adj_open, tx.adj_close
FROM b LEFT JOIN lv USING (trade_date) INNER JOIN tx USING (trade_date)
ORDER BY b.trade_date
"""


def load_daily(start: date, end: date) -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        df = conn.execute(DAILY_SQL, [start, end, start, end, start, end]).fetchdf()
    df["lu_value_ratio"] = df["lu_value"] / df["total_value"]
    df["lu_cnt_ma7"] = df["up_limit_count"].rolling(7).mean()
    df["lu_ratio_ma7"] = df["lu_value_ratio"].rolling(7).mean()
    df["intraday_pnl"] = df["raw_close"] - df["raw_open"]
    df["intraday_ret_pct"] = df["intraday_pnl"] / df["raw_open"] * 100
    df["daily_close_ret"] = df["adj_close"].pct_change()
    print(f"Loaded {len(df)} days, range {df['trade_date'].min()} ~ {df['trade_date'].max()}")
    return df


# ---------------------------------------------------------------------------
# Event flag
# ---------------------------------------------------------------------------

def compute_event(df: pd.DataFrame, pct: float, consec: int,
                  logic: str = "AND", ma: int = 7) -> pd.Series:
    """萎縮事件：lu_cnt_ma 與 lu_ratio_ma 滿足 `logic` 條件持續 consec 天.

    Args:
        pct: 分位數門檻（用全期歷史的 pct quantile 作 threshold）
        consec: 連續成立的天數
        logic: 條件邏輯，可選 'AND', 'OR', 'CNT', 'RATIO'
        ma: moving average window 天數
    """
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
        raise ValueError(f"unknown logic: {logic}")
    return (cond.rolling(consec).sum() >= consec).fillna(False)


# ---------------------------------------------------------------------------
# C-defense
# ---------------------------------------------------------------------------

def backtest_defense(df: pd.DataFrame, event: pd.Series, skip_n: int) -> dict:
    """Baseline: 每日 long 日盤. 防禦版: 事件觸發後 skip_n 天不交易."""
    df = df.copy().reset_index(drop=True)
    event = event.reset_index(drop=True)

    # Defense flag: skip if any event triggered in past `skip_n` days (inclusive of today)
    defense_flag = event.rolling(skip_n, min_periods=1).max().astype(bool)

    base = df.copy()
    base["pnl_pts"] = base["intraday_pnl"] - ROUND_TRIP_COST
    base["ret_pct"] = base["pnl_pts"] / base["raw_open"] * 100
    base["side"] = "L"

    skip_mask = defense_flag
    var = df.loc[~skip_mask].copy()
    var["pnl_pts"] = var["intraday_pnl"] - ROUND_TRIP_COST
    var["ret_pct"] = var["pnl_pts"] / var["raw_open"] * 100
    var["side"] = "L"

    avoided = df.loc[skip_mask].copy()
    avoided["pnl_pts"] = avoided["intraday_pnl"] - ROUND_TRIP_COST  # 假設不防禦會付的
    avoided["ret_pct"] = avoided["pnl_pts"] / avoided["raw_open"] * 100

    return {
        "baseline_trades": base[["trade_date", "raw_open", "raw_close", "side", "pnl_pts", "ret_pct"]],
        "defense_trades": var[["trade_date", "raw_open", "raw_close", "side", "pnl_pts", "ret_pct"]],
        "avoided_trades": avoided[["trade_date", "raw_open", "raw_close", "pnl_pts", "ret_pct"]],
        "defense_pct_of_days": skip_mask.mean(),
    }


# ---------------------------------------------------------------------------
# C-short
# ---------------------------------------------------------------------------

def backtest_short_overlap(df: pd.DataFrame, event: pd.Series, hold_n: int) -> pd.DataFrame:
    """每個事件觸發日 → 隔日 08:45 開盤做空 → +hold_n 天 13:45 收盤平倉."""
    df = df.copy().reset_index(drop=True)
    event = event.reset_index(drop=True)

    df["entry_adj"] = df["adj_open"].shift(-1)  # 隔日早上開盤（adj-adjusted）
    df["exit_adj"] = df["adj_close"].shift(-(hold_n + 1))  # +1 是因為從隔日開始算
    df["entry_date"] = df["trade_date"].shift(-1)
    df["exit_date"] = df["trade_date"].shift(-(hold_n + 1))

    valid = event & df["entry_adj"].notna() & df["exit_adj"].notna()
    sub = df[valid].copy()
    sub["pnl_pts"] = sub["entry_adj"] - sub["exit_adj"] - ROUND_TRIP_COST  # 做空
    sub["ret_pct"] = sub["pnl_pts"] / sub["entry_adj"] * 100
    sub["side"] = "S"
    return sub[["trade_date", "entry_date", "exit_date",
                "entry_adj", "exit_adj", "pnl_pts", "ret_pct", "side"]]


def backtest_short_sequential(df: pd.DataFrame, event: pd.Series, hold_n: int) -> pd.DataFrame:
    """單部位版本：持有中不開新短倉."""
    df = df.copy().reset_index(drop=True)
    event = event.reset_index(drop=True)

    rows = []
    i = 0
    while i + hold_n + 1 < len(df):
        if not event.iloc[i]:
            i += 1
            continue
        entry_adj = df["adj_open"].iloc[i + 1]
        exit_adj = df["adj_close"].iloc[i + hold_n + 1]
        if pd.isna(entry_adj) or pd.isna(exit_adj):
            i += 1
            continue
        pnl = entry_adj - exit_adj - ROUND_TRIP_COST
        rows.append({
            "trade_date": df["trade_date"].iloc[i],
            "entry_date": df["trade_date"].iloc[i + 1],
            "exit_date": df["trade_date"].iloc[i + hold_n + 1],
            "entry_adj": entry_adj,
            "exit_adj": exit_adj,
            "pnl_pts": pnl,
            "ret_pct": pnl / entry_adj * 100,
            "side": "S",
        })
        i += hold_n + 1
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

def perf(trades: pd.DataFrame, n: int = 1) -> dict:
    if len(trades) == 0:
        return {"n_trades": 0}
    pnl = trades["pnl_pts"]
    ret = trades["ret_pct"]
    cum = pnl.cumsum()
    dd = cum - cum.cummax()
    sharpe = (ret.mean() / ret.std()) * np.sqrt(252 / n) if ret.std() > 0 else 0
    return {
        "n_trades": len(trades),
        "win_rate": (pnl > 0).mean(),
        "avg_ret_pct": ret.mean(),
        "median_ret_pct": ret.median(),
        "total_pnl_pts": pnl.sum(),
        "total_ret_pct": ret.sum(),
        "sharpe": sharpe,
        "max_dd_pts": dd.min(),
        "best_pct": ret.max(),
        "worst_pct": ret.min(),
    }


def fmt(d: dict) -> str:
    if d.get("n_trades", 0) == 0:
        return "no trades"
    return (f"n={d['n_trades']:<4} win={d['win_rate']:.1%} "
            f"avg/筆={d['avg_ret_pct']:+.3f}% total={d['total_ret_pct']:+.1f}% "
            f"Sharpe={d['sharpe']:.2f} MaxDD={d['max_dd_pts']:+.0f}pts "
            f"best/worst={d['best_pct']:+.1f}/{d['worst_pct']:+.1f}%")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def slice_trades(trades: pd.DataFrame, date_col: str, start, end):
    df = trades.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    if start is not None:
        df = df[df[date_col] >= start]
    if end is not None:
        df = df[df[date_col] < end]
    return df


def crash_recall(df: pd.DataFrame, defense: pd.Series,
                 crash_threshold: float = -2.0) -> dict:
    """計算 defense 對「日盤 ret < threshold%」事件的 recall."""
    is_crash = (df["intraday_ret_pct"] < crash_threshold).reset_index(drop=True)
    defense = defense.reset_index(drop=True)
    n_crash = int(is_crash.sum())
    n_caught = int((is_crash & defense).sum())
    return {
        "total_crash": n_crash,
        "caught": n_caught,
        "recall": n_caught / n_crash if n_crash > 0 else 0,
    }


def run_defense_block(df: pd.DataFrame, oos_ts: pd.Timestamp,
                      pct_list, consec_list, skip_list,
                      logic: str = "AND", ma: int = 7) -> pd.DataFrame:
    print(f"\n{'='*100}")
    print("C-defense: Always-long 日盤 + 事件後 N 天暫停做多")
    print('='*100)
    rows = []
    for pct, consec, skip_n in itertools.product(pct_list, consec_list, skip_list):
        event = compute_event(df, pct, consec, logic=logic, ma=ma)
        if event.sum() < 3:
            continue
        result = backtest_defense(df, event, skip_n)
        defense_flag = event.rolling(skip_n, min_periods=1).max().astype(bool)
        recall_full = crash_recall(df, defense_flag)
        is_mask = df["trade_date"] < oos_ts
        recall_oos = crash_recall(df.loc[~is_mask].reset_index(drop=True),
                                  defense_flag.reset_index(drop=True).loc[df.index[~is_mask]].reset_index(drop=True))
        for split_label, (s, e) in [("Full", (None, None)), ("IS", (None, oos_ts)),
                                     ("OOS", (oos_ts, None))]:
            base_t = slice_trades(result["baseline_trades"], "trade_date", s, e)
            def_t = slice_trades(result["defense_trades"], "trade_date", s, e)
            avd_t = slice_trades(result["avoided_trades"], "trade_date", s, e)
            base_p = perf(base_t)
            def_p = perf(def_t)
            avd_p = perf(avd_t)
            row = {
                "pct": pct, "consec": consec, "skip_n": skip_n, "split": split_label,
                "logic": logic, "ma": ma,
                "n_events": int(event.sum()),
                "n_avoided": avd_p.get("n_trades", 0),
                "base_total": round(base_p.get("total_pnl_pts", 0), 1),
                "def_total": round(def_p.get("total_pnl_pts", 0), 1),
                "delta_total": round(def_p.get("total_pnl_pts", 0) - base_p.get("total_pnl_pts", 0), 1),
                "base_dd": round(base_p.get("max_dd_pts", 0), 1),
                "def_dd": round(def_p.get("max_dd_pts", 0), 1),
                "base_sharpe": round(base_p.get("sharpe", 0), 2),
                "def_sharpe": round(def_p.get("sharpe", 0), 2),
                "avoided_total": round(avd_p.get("total_pnl_pts", 0), 1),
                "avoided_avg": round(avd_p.get("avg_ret_pct", 0), 3),
            }
            if split_label == "Full":
                row["recall_full"] = recall_full["recall"]
                row["caught_full"] = f"{recall_full['caught']}/{recall_full['total_crash']}"
            elif split_label == "OOS":
                row["recall_oos"] = recall_oos["recall"]
                row["caught_oos"] = f"{recall_oos['caught']}/{recall_oos['total_crash']}"
            rows.append(row)
    return pd.DataFrame(rows)


def run_short_block(df: pd.DataFrame, oos_ts: pd.Timestamp,
                    pct_list, consec_list, hold_list,
                    logic: str = "AND", ma: int = 7) -> pd.DataFrame:
    print(f"\n{'='*100}")
    print("C-short: 事件觸發日隔日做空 → +N 天平倉")
    print('='*100)
    rows = []
    for pct, consec, hold_n in itertools.product(pct_list, consec_list, hold_list):
        event = compute_event(df, pct, consec, logic=logic, ma=ma)
        if event.sum() < 3:
            continue
        ovl = backtest_short_overlap(df, event, hold_n)
        seq = backtest_short_sequential(df, event, hold_n)
        for split_label, (s, e) in [("Full", (None, None)), ("IS", (None, oos_ts)),
                                     ("OOS", (oos_ts, None))]:
            ovl_s = slice_trades(ovl, "trade_date", s, e)
            seq_s = slice_trades(seq, "trade_date", s, e)
            ovl_p = perf(ovl_s, n=hold_n)
            seq_p = perf(seq_s, n=hold_n)
            rows.append({
                "pct": pct, "consec": consec, "hold_n": hold_n, "split": split_label,
                "ovl_n": ovl_p.get("n_trades", 0),
                "ovl_win": round(ovl_p.get("win_rate", 0), 3),
                "ovl_avg_pct": round(ovl_p.get("avg_ret_pct", 0), 3),
                "ovl_total_pct": round(ovl_p.get("total_ret_pct", 0), 1),
                "ovl_sharpe": round(ovl_p.get("sharpe", 0), 2),
                "ovl_dd": round(ovl_p.get("max_dd_pts", 0), 1),
                "seq_n": seq_p.get("n_trades", 0),
                "seq_win": round(seq_p.get("win_rate", 0), 3),
                "seq_total_pct": round(seq_p.get("total_ret_pct", 0), 1),
                "seq_sharpe": round(seq_p.get("sharpe", 0), 2),
            })
    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=date.fromisoformat, default=date(2018, 1, 1))
    p.add_argument("--end", type=date.fromisoformat, default=date(2026, 4, 30))
    p.add_argument("--oos-start", type=date.fromisoformat, default=date(2024, 1, 1),
                   help="OOS 起始日（補完歷史後預設 2024 起為 OOS）")
    p.add_argument("--save", action="store_true")
    p.add_argument("--logic", default="RATIO", choices=["AND", "OR", "CNT", "RATIO"],
                   help="event 條件邏輯（預設 RATIO，原版 AND）")
    p.add_argument("--ma", type=int, default=7, help="moving average window 天數（預設 7）")
    args = p.parse_args()

    df = load_daily(args.start, args.end)
    oos_ts = pd.Timestamp(args.oos_start)

    pct_list = [0.10, 0.15, 0.20]
    consec_list = [3, 5]
    n_list = [10, 20, 30, 40, 50, 60]
    print(f"\n使用 logic={args.logic}, ma={args.ma}")

    print(f"\n參數空間: pct={pct_list}, consec={consec_list}, N={n_list}")
    print(f"IS/OOS 切點: {args.oos_start}\n")

    # Print summary of event counts
    print("各參數的事件天數:")
    for pct in pct_list:
        for consec in consec_list:
            ev = compute_event(df, pct, consec, logic=args.logic, ma=args.ma)
            print(f"  pct={pct}, consec={consec}: {ev.sum()} 事件天 ({ev.mean()*100:.1f}%)")

    def_df = run_defense_block(df, oos_ts, pct_list, consec_list, n_list,
                                logic=args.logic, ma=args.ma)
    print("\n=== Defense (Full sample 子表) ===")
    print(def_df[def_df["split"] == "Full"].to_string(index=False))
    print("\n=== Defense (OOS 子表) ===")
    print(def_df[def_df["split"] == "OOS"].to_string(index=False))

    short_df = run_short_block(df, oos_ts, pct_list, consec_list, n_list,
                                logic=args.logic, ma=args.ma)
    print("\n=== Short (Full sample 子表) ===")
    print(short_df[short_df["split"] == "Full"].to_string(index=False))
    print("\n=== Short (OOS 子表) ===")
    print(short_df[short_df["split"] == "OOS"].to_string(index=False))

    if args.save:
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        def_df.to_csv(RESULT_DIR / "C_defense_summary.csv", index=False)
        short_df.to_csv(RESULT_DIR / "C_short_summary.csv", index=False)
        print(f"\nSaved summaries to {RESULT_DIR}")


if __name__ == "__main__":
    main()
