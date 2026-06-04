#!/usr/bin/env python3
"""H101 Phase 2 — Reversal 方向濾網四變體並排回測。

唯一變數＝方向濾網（dir_mode），其餘 reversal 邏輯與 live (S002) 完全相同。
  base : 5m 120MA 斜率（只日盤）          ← live
  A    : 5m 240MA 斜率（連續日+夜盤）
  B    : 1H MACD 12/26/9，MACD 線 vs Signal 線（連續日+夜盤）
  C    : A 且 B 同向

新濾網欄位（MA5m_240/_Prev, MACD_1h, Signal_1h）在本腳本以連續 1m close
計算後 merge 進 load_data_for_reversal 的 df，皆 shift 避免未來函數。

指標：交易筆數 / 損益%(sum) / 平均損益% / Sharpe(per-trade) / PF / 勝率 /
      最大連敗 / 最大回撤(損益% 累積)。
分割：in-sample 前 70% 交易日 / out-of-sample 後 30% + 年度分段。

Usage:
    uv run python research/active/H101-reversal-direction-filter/backtest.py
"""
import argparse

import duckdb
import numpy as np
import pandas as pd
from backtesting import Backtest

from src.backtest.runner import load_data_for_reversal
from src.strategies.reversal import ReversalStrategy

DB = "data/futures.duckdb"
MODES = ["base", "A", "B", "C"]

LIVE_PARAMS = dict(
    vol_ratio=1.2,
    sl_ema_fraction=0.25,
    exhaust_fraction=0.5,
    signal_skip=0,
    sat_pullback_fraction=0.5,
)


def load(start=None, end=None):
    df = load_data_for_reversal(start=start, end=end)
    with duckdb.connect(DB, read_only=True) as c:
        s = c.execute("""
            SELECT timestamp, close FROM ohlcv_1m
            WHERE symbol='TX' ORDER BY timestamp
        """).df().set_index("timestamp")["close"]

    # A: 5m 240MA continuous (day+night), slope via shift1 vs shift2
    s5 = s.resample("5min").last().dropna()
    ma240 = s5.rolling(240, min_periods=240).mean()
    df["MA5m_240"]      = ma240.shift(1).reindex(df.index, method="ffill")
    df["MA5m_240_Prev"] = ma240.shift(2).reindex(df.index, method="ffill")

    # B: 1H MACD 12/26/9 continuous, shift1 (use last completed 1H bar)
    s1h = s.resample("1h").last().dropna()
    macd = (s1h.ewm(span=12, adjust=False).mean()
            - s1h.ewm(span=26, adjust=False).mean())
    sig = macd.ewm(span=9, adjust=False).mean()
    df["MACD_1h"]   = macd.shift(1).reindex(df.index, method="ffill")
    df["Signal_1h"] = sig.shift(1).reindex(df.index, method="ffill")
    return df


def run_mode(df, mode):
    bt = Backtest(df, ReversalStrategy,
                  cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(dir_mode=mode, **LIVE_PARAMS)
    t = stats["_trades"].copy()
    # 損益% = PnL / EntryPrice * 100  (size=±1, PnL 已含方向)
    t["ret_pct"] = t["PnL"] / t["EntryPrice"] * 100.0
    return t


def max_consec_losses(ret):
    mx = cur = 0
    for r in ret:
        if r < 0:
            cur += 1
            mx = max(mx, cur)
        else:
            cur = 0
    return mx


def max_drawdown_pct(ret):
    """最大回撤：以損益% 累積成權益曲線（單位＝累積損益%）。"""
    eq = np.cumsum(ret)
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    return float(dd.min()) if len(dd) else 0.0


def metrics(t):
    n = len(t)
    if n == 0:
        return dict(n=0, total=0, avg=0, sharpe=0, pf=0, win=0, mcl=0, mdd=0)
    r = t["ret_pct"].values
    wins = r[r > 0].sum()
    losses = -r[r < 0].sum()
    return dict(
        n=n,
        total=r.sum(),
        avg=r.mean(),
        sharpe=(r.mean() / r.std(ddof=1)) if r.std(ddof=1) > 0 else 0,
        pf=(wins / losses) if losses > 0 else float("inf"),
        win=(r > 0).mean() * 100,
        mcl=max_consec_losses(r),
        mdd=max_drawdown_pct(r),
    )


def fmt_row(label, m):
    pf = f"{m['pf']:.2f}" if np.isfinite(m["pf"]) else "inf"
    return (f"  {label:<14} n={m['n']:>4}  總損益%={m['total']:>8.2f}  "
            f"avg={m['avg']:>6.3f}  Sharpe={m['sharpe']:>6.3f}  "
            f"PF={pf:>5}  勝率={m['win']:>5.1f}%  "
            f"最大連敗={m['mcl']:>2}  最大回撤%={m['mdd']:>8.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    args = ap.parse_args()

    print("Loading data + building direction-filter columns...")
    df = load(args.start, args.end)
    print(f"Loaded {len(df):,} bars  [{df.index[0]} → {df.index[-1]}]\n")

    # 70/30 split by trading days
    dates = pd.DatetimeIndex(np.unique(pd.DatetimeIndex(df.index).normalize()))
    cutoff = dates[int(len(dates) * 0.70)]
    print(f"IS/OOS cutoff = {cutoff.date()}  "
          f"(IS {dates[0].date()}~{(cutoff - pd.Timedelta(days=1)).date()}, "
          f"OOS {cutoff.date()}~{dates[-1].date()})\n")

    trades = {m: run_mode(df, m) for m in MODES}

    def section(title, mask_fn):
        print(f"━━ {title} ━━")
        for m in MODES:
            t = trades[m]
            tt = t[mask_fn(t)] if len(t) else t
            print(fmt_row(m, metrics(tt)))
        print()

    section("ALL（全期）", lambda t: pd.Series(True, index=t.index))
    section("IN-SAMPLE（前 70%）",
            lambda t: t["EntryTime"] < cutoff)
    section("OUT-OF-SAMPLE（後 30%）",
            lambda t: t["EntryTime"] >= cutoff)

    # 年度分段
    print("━━ 年度分段（總損益% / 筆數）━━")
    years = sorted({ts.year for ts in df.index})
    header = "  year   " + "".join(f"{m:>18}" for m in MODES)
    print(header)
    for y in years:
        cells = ""
        for m in MODES:
            t = trades[m]
            ty = t[pd.DatetimeIndex(t["EntryTime"]).year == y] if len(t) else t
            mm = metrics(ty)
            cells += f"{mm['total']:>10.1f}(n={mm['n']:>3})"
        print(f"  {y}  {cells}")
    print()

    # save per-trade csvs
    base_dir = "research/active/H101-reversal-direction-filter/results"
    for m in MODES:
        trades[m].to_csv(f"{base_dir}/trades_{m}.csv", index=False)
    print(f"[saved] per-trade CSVs → {base_dir}/trades_*.csv")


if __name__ == "__main__":
    main()
