"""H079-B Phase 2 Backtest — Swing 版本（A5）

設計
----
A5: 30 日 swing-long + LC-HV 跳過為主、10 日為對照

進出場
------
- Entry: 訊號日 t 日盤收盤 13:45 (adj_close)
- Exit:  t+N 個交易日後的日盤收盤 13:45 (adj_close)
- 用 adj_close（Panama 連續合約）跨 rollover 不會有人造跳空
- 成本: 來回 6 點（2 commission + 1 slippage，雙邊）

兩種模式
--------
- Overlap: 每日都開一筆新 swing（樣本最多，用來評估訊號 alpha）
- Sequential: 持倉中不開新倉（更貼近實盤，每 N 日才 1 筆）

兩種比較
--------
- Baseline: 每筆都進場
- C3:       訊號日為 LC-HV 則跳過該筆進場

四個切片
--------
Full Sample / IS (<2025-07) / OOS (>=2025-07)
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
RESULT_DIR = Path(__file__).parent / "results"

ROUND_TRIP_COST = 6.0


# ---------------------------------------------------------------------------
# Data loading: adj_close + LC-HV flag
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
           LAST(adj_close ORDER BY timestamp) AS adj_close,
           LAST(close     ORDER BY timestamp) AS raw_close,
           ANY_VALUE(is_rollover)             AS is_rollover
    FROM ohlcv_1m
    WHERE symbol = 'TX'
      AND timestamp::DATE BETWEEN ? AND ?
      AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
    GROUP BY trade_date
)
SELECT b.trade_date, b.up_limit_count, b.total_value, lv.lu_value,
       tx.adj_close, tx.raw_close, tx.is_rollover
FROM b LEFT JOIN lv USING (trade_date) INNER JOIN tx USING (trade_date)
ORDER BY b.trade_date
"""


def load_daily(start: date, end: date) -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        df = conn.execute(DAILY_SQL, [start, end, start, end, start, end]).fetchdf()
    df["lu_value_ratio"] = df["lu_value"] / df["total_value"]
    cnt_med = df["up_limit_count"].median()
    val_med = df["lu_value_ratio"].median()
    df["is_lc_hv"] = (df["up_limit_count"] < cnt_med) & (df["lu_value_ratio"] >= val_med)
    print(f"Threshold: count_median={cnt_med:.0f}, value_ratio_median={val_med:.4f}")
    print(f"Total {len(df)} days, LC-HV {df['is_lc_hv'].sum()}")
    return df


# ---------------------------------------------------------------------------
# Backtest cores
# ---------------------------------------------------------------------------

def overlap_swing(df: pd.DataFrame, n: int, skip_lc_hv: bool) -> pd.DataFrame:
    """每日都開一筆 N 日 swing-long; skip_lc_hv 時 LC-HV 日不進場."""
    df = df.sort_values("trade_date").reset_index(drop=True)
    entries = ~df["is_lc_hv"] if skip_lc_hv else pd.Series(True, index=df.index)
    df = df[entries].copy()
    df["exit_adj"] = df["adj_close"].shift(-n) if False else None  # placeholder
    # 重新從原 df shift（不用篩掉的）
    full = pd.read_csv  # silly placeholder, drop
    # Cleaner: do shift on the full df, then filter
    return df  # not used


def overlap_swing_v2(df: pd.DataFrame, n: int, skip_lc_hv: bool) -> pd.DataFrame:
    """正確版本：在 full df 上算 fwd, 再依 entry signal 篩."""
    df = df.sort_values("trade_date").reset_index(drop=True).copy()
    df["exit_adj"] = df["adj_close"].shift(-n)
    df["exit_date"] = df["trade_date"].shift(-n)
    valid = df["exit_adj"].notna()
    if skip_lc_hv:
        valid &= ~df["is_lc_hv"]
    sub = df[valid].copy()
    sub["entry_adj"] = sub["adj_close"]
    sub["pnl_pts"] = sub["exit_adj"] - sub["entry_adj"] - ROUND_TRIP_COST
    sub["ret_pct"] = sub["pnl_pts"] / sub["entry_adj"] * 100
    return sub[["trade_date", "exit_date", "is_lc_hv",
                "entry_adj", "exit_adj", "pnl_pts", "ret_pct"]]


def sequential_swing(df: pd.DataFrame, n: int, skip_lc_hv: bool) -> pd.DataFrame:
    """持倉中不開新倉版本（單一部位）."""
    df = df.sort_values("trade_date").reset_index(drop=True)
    rows = []
    i = 0
    while i + n < len(df):
        row = df.iloc[i]
        if skip_lc_hv and row["is_lc_hv"]:
            i += 1
            continue
        exit_row = df.iloc[i + n]
        entry_adj = row["adj_close"]
        exit_adj = exit_row["adj_close"]
        pnl = exit_adj - entry_adj - ROUND_TRIP_COST
        rows.append({
            "trade_date": row["trade_date"],
            "exit_date": exit_row["trade_date"],
            "is_lc_hv": row["is_lc_hv"],
            "entry_adj": entry_adj,
            "exit_adj": exit_adj,
            "pnl_pts": pnl,
            "ret_pct": pnl / entry_adj * 100,
        })
        i += n  # 跳到 exit_date 之後再開新倉
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Performance summary
# ---------------------------------------------------------------------------

def summarize(trades: pd.DataFrame, n: int, label: str) -> dict:
    if len(trades) == 0:
        return {"label": label, "n_trades": 0}
    pnl = trades["pnl_pts"]
    ret = trades["ret_pct"]
    cum = pnl.cumsum()
    dd = cum - cum.cummax()
    # Sharpe annualized: (mean/std) * sqrt(252/n) for non-overlapping
    sharpe = (ret.mean() / ret.std()) * np.sqrt(252 / n) if ret.std() > 0 else 0
    return {
        "label": label,
        "n_trades": len(trades),
        "win_rate": (pnl > 0).mean(),
        "avg_ret_pct": ret.mean(),
        "median_ret_pct": ret.median(),
        "total_ret_pct": ret.sum(),
        "total_pnl_pts": pnl.sum(),
        "sharpe": sharpe,
        "max_dd_pts": dd.min(),
        "max_dd_pct": (dd / cum.cummax().abs().clip(lower=1)).min() * 100,
        "best_pct": ret.max(),
        "worst_pct": ret.min(),
    }


def print_block(d: dict) -> None:
    if d["n_trades"] == 0:
        print(f"  {d['label']}: no trades")
        return
    print(f"  {d['label']:<32} n={d['n_trades']:<5} win={d['win_rate']:.1%}  "
          f"avg/筆={d['avg_ret_pct']:+.3f}%  total={d['total_ret_pct']:+.1f}%  "
          f"Sharpe={d['sharpe']:.2f}  MaxDD={d['max_dd_pts']:+.0f}pts  "
          f"best/worst={d['best_pct']:+.1f}/{d['worst_pct']:+.1f}%")


# ---------------------------------------------------------------------------
# Block runner: full / IS / OOS
# ---------------------------------------------------------------------------

def slice_by_entry(trades: pd.DataFrame, start: pd.Timestamp | None,
                   end: pd.Timestamp | None) -> pd.DataFrame:
    df = trades.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    if start is not None:
        df = df[df["trade_date"] >= start]
    if end is not None:
        df = df[df["trade_date"] < end]
    return df


def run_horizon(df: pd.DataFrame, n: int, oos_start: pd.Timestamp) -> dict:
    print(f"\n{'='*88}")
    print(f"HORIZON = {n} 日 swing-long")
    print(f"{'='*88}")

    overlap_base = overlap_swing_v2(df, n, skip_lc_hv=False)
    overlap_c3 = overlap_swing_v2(df, n, skip_lc_hv=True)
    seq_base = sequential_swing(df, n, skip_lc_hv=False)
    seq_c3 = sequential_swing(df, n, skip_lc_hv=True)

    splits = {
        "Full":  (None, None),
        "IS":    (None, oos_start),
        "OOS":   (oos_start, None),
    }

    results = {}
    for split_name, (s, e) in splits.items():
        print(f"\n  --- {split_name} ---")
        b = summarize(slice_by_entry(overlap_base, s, e), n, f"Overlap-Baseline")
        c = summarize(slice_by_entry(overlap_c3, s, e), n, f"Overlap-C3 (skip LC-HV)")
        sb = summarize(slice_by_entry(seq_base, s, e), n, f"Seq-Baseline")
        sc = summarize(slice_by_entry(seq_c3, s, e), n, f"Seq-C3 (skip LC-HV)")
        for d in [b, c, sb, sc]:
            print_block(d)
        # delta
        if b["n_trades"] > 0 and c["n_trades"] > 0:
            print(f"  Δ avg/筆 (Overlap C3-Base): {c['avg_ret_pct']-b['avg_ret_pct']:+.3f}%, "
                  f"Δ Sharpe: {c['sharpe']-b['sharpe']:+.2f}")
        if sb["n_trades"] > 0 and sc["n_trades"] > 0:
            print(f"  Δ avg/筆 (Seq C3-Base):     {sc['avg_ret_pct']-sb['avg_ret_pct']:+.3f}%, "
                  f"Δ Sharpe: {sc['sharpe']-sb['sharpe']:+.2f}")
        results[split_name] = {
            "overlap_base": b, "overlap_c3": c,
            "seq_base": sb, "seq_c3": sc,
        }

    return {
        "results": results,
        "trades": {
            "overlap_base": overlap_base,
            "overlap_c3": overlap_c3,
            "seq_base": seq_base,
            "seq_c3": seq_c3,
        }
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=date.fromisoformat, default=date(2024, 1, 1))
    p.add_argument("--end", type=date.fromisoformat, default=date(2026, 4, 30))
    p.add_argument("--oos-start", type=date.fromisoformat, default=date(2025, 7, 1))
    p.add_argument("--horizons", type=int, nargs="+", default=[10, 30])
    p.add_argument("--save", action="store_true")
    args = p.parse_args()

    df = load_daily(args.start, args.end)
    oos_ts = pd.Timestamp(args.oos_start)

    all_results = {}
    for n in args.horizons:
        all_results[n] = run_horizon(df, n, oos_ts)

    if args.save:
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        for n, blk in all_results.items():
            for name, trades in blk["trades"].items():
                trades.to_csv(RESULT_DIR / f"swing_{n}d_{name}.csv", index=False)
        print(f"\nSaved trade CSVs to {RESULT_DIR}")


if __name__ == "__main__":
    main()
