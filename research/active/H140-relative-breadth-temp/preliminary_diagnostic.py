#!/usr/bin/env python3
"""H140 建檔動機的初步診斷（非正式 Phase 1）

起因：2026-07 S002 Reversal 連續大賠，但 H079 現行絕對門檻訊號全月綠燈。
本腳本檢查把 lu_ratio_ma 改成「過去 1 年滾動百分位」後，是否能辨識該段連敗，
並初步檢查趨勢/波動的 confound。

正式的分佈探索請見 explore.py（Phase 1），本檔僅保留建檔當下的觀測依據。

前置：
    uv run python strategies/live/S002-reversal/backtest.py --start 2021-01-01
    → output/s002_reversal_2021-01-01.csv

執行：
    MPLBACKEND=Agg uv run python research/active/H140-relative-breadth-temp/preliminary_diagnostic.py
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

from src.analysis.breadth_thermometer import load_breadth_history, annotate

TRADES_CSV = "output/s002_reversal_2021-01-01.csv"
DB_PATH = "data/futures.duckdb"
LOOKBACK = 250      # 相對溫度回看窗（交易日）
HOT_PCT = 0.80      # 熱門檻（注意：事後挑選，Phase 1 須做敏感度掃描）


def load_temperature() -> pd.DataFrame:
    """漲停成交額占比 ma7 + 其 1 年滾動百分位（僅比對過去，無前視）。"""
    th, threshold = annotate(load_breadth_history(lookback_years=9))
    th["d"] = pd.to_datetime(th["trade_date"]).astype("datetime64[ns]")
    th["pct1y"] = th["lu_ratio_ma"].rolling(LOOKBACK, min_periods=120).apply(
        lambda s: (s[:-1] < s[-1]).mean(), raw=True)
    return th, threshold


def load_price_context() -> pd.DataFrame:
    """TX 日收盤 → 前 20 日報酬 / 20 日波動，皆 shift(1) 只用到前一日為止。"""
    sql = """SELECT CAST(timestamp AS DATE) d, last(adj_close ORDER BY timestamp) c
             FROM ohlcv_1m GROUP BY 1 ORDER BY 1"""
    with duckdb.connect(DB_PATH, read_only=True) as con:
        px = con.execute(sql).fetchdf()
    px["d"] = pd.to_datetime(px["d"]).astype("datetime64[ns]")
    px["ret20"] = px["c"].pct_change(20)
    px["vol20"] = px["c"].pct_change().rolling(20).std()
    px[["ret20", "vol20"]] = px[["ret20", "vol20"]].shift(1)
    return px


def load_trades() -> pd.DataFrame:
    t = pd.read_csv(TRADES_CSV, parse_dates=["EntryTime"])
    t["d"] = t["EntryTime"].dt.normalize().astype("datetime64[ns]")
    t["pts"] = t["PnL"]          # size=1 → PnL 即點數
    return t


def bucket(df: pd.DataFrame, col: str, q: int, label: str) -> None:
    x = df.dropna(subset=[col]).copy()
    x["b"] = pd.qcut(x[col], q, duplicates="drop")
    g = x.groupby("b", observed=True)["pts"].agg(["count", "mean", "sum"])
    g["win%"] = x.groupby("b", observed=True)["pts"].apply(lambda s: 100 * (s > 0).mean())
    print(f"=== {label} ===")
    print(g.round(1).to_string(), "\n")


def main() -> None:
    th, threshold = load_temperature()
    px = load_price_context()
    t = load_trades()

    m = (t.merge(th[["d", "lu_ratio_ma", "pct1y", "up_limit_count"]], on="d", how="left")
           .merge(px[["d", "ret20", "vol20"]], on="d", how="left"))
    m = m.dropna(subset=["pct1y"])
    print(f"N={len(m)}  期望值={m.pts.mean():+.1f} pts  勝率={100*(m.pts>0).mean():.1f}%")
    print(f"（H079 絕對門檻 = {threshold*100:.2f}%）\n")

    # ── 1. 相對溫度是否分得開 ──
    bucket(m, "lu_ratio_ma", 5, "ma7 絕對值五分位")
    bucket(m, "pct1y", 5, f"ma7 的 {LOOKBACK} 日滾動百分位（相對溫度）五分位")

    x = m.dropna(subset=["ret20", "vol20"]).copy()
    x["hot"] = x.pct1y >= HOT_PCT
    x["down"] = x.ret20 < 0
    x["hivol"] = x.vol20 > x.vol20.median()
    x["yr"] = x.d.dt.year

    # ── 2. 增量檢定：溫度 vs 趨勢 / 波動 ──
    print("=== 溫度 × 趨勢（前 20 日報酬）交叉 ===")
    print(x.groupby(["hot", "down"])["pts"].agg(
        n="size", mean="mean", total="sum",
        win=lambda s: 100 * (s > 0).mean()).round(1).to_string(), "\n")

    print("=== 溫度 × 波動 交叉 ===")
    print(x.groupby(["hot", "hivol"])["pts"].agg(
        n="size", mean="mean", total="sum").round(1).to_string(), "\n")

    print("=== 只用趨勢當濾網（不看溫度）===")
    print(x.groupby("down")["pts"].agg(
        n="size", mean="mean", total="sum",
        win=lambda s: 100 * (s > 0).mean()).round(1).to_string(), "\n")

    # ── 3. 穩健性：單年主導？ ──
    print("=== 熱桶逐年 ===")
    print(x[x.hot].groupby("yr")["pts"].agg(n="size", mean="mean", total="sum").round(1).to_string(), "\n")
    print("=== 非熱桶逐年 ===")
    print(x[~x.hot].groupby("yr")["pts"].agg(n="size", mean="mean", total="sum").round(1).to_string(), "\n")

    print("=== 排除 2026 後 ===")
    pre = x[x.d < "2026-01-01"]
    print(pre.groupby("hot")["pts"].agg(
        n="size", mean="mean", total="sum",
        win=lambda s: 100 * (s > 0).mean()).round(1).to_string())
    print(pre.groupby(["hot", "down"])["pts"].agg(n="size", mean="mean", total="sum").round(1).to_string(), "\n")

    # ── 4. 濾網粗估（注意：門檻為事後挑選，僅供建檔參考）──
    def mdd(v: pd.Series) -> float:
        c = v.cumsum()
        return (c - c.cummax()).min()

    print(f"=== 規則粗估：只在 pct1y >= {HOT_PCT} 時做 S002 ===")
    for nm, lo, hi in [("IS 2021-2023", "2021-01-01", "2023-12-31"),
                       ("OOS 2024-2026", "2024-01-01", "2026-12-31"),
                       ("Full", "2021-01-01", "2026-12-31")]:
        s = x[(x.d >= lo) & (x.d <= hi)]
        f = s[s.hot]
        print(f"{nm:14s} base N={len(s):3d} total={s.pts.sum():+7.0f} mean={s.pts.mean():+6.1f} "
              f"maxDD={mdd(s.pts):+7.0f} | filt N={len(f):3d} total={f.pts.sum():+7.0f} "
              f"mean={f.pts.mean():+6.1f} maxDD={mdd(f.pts):+7.0f}")

    mid = x[(x.pct1y > .2) & (x.pct1y < .8)]
    ends = x[(x.pct1y <= .2) | (x.pct1y >= .8)]
    print("\n中間溫度 vs 兩端 t-test:", stats.ttest_ind(mid.pts, ends.pts, equal_var=False))

    # ── 5. 2026-06/07 逐日對照（建檔的直接動機）──
    print(f"\n=== 2026-06-15 起逐日溫度 vs S002 ===")
    tr = m.set_index("d")["pts"]
    for _, r in th[th.d >= "2026-06-15"].iterrows():
        p = tr.get(r["d"], None)
        if isinstance(p, pd.Series):
            ptxt = f"{p.sum():+6.0f}({len(p)})"
        elif p is None or (isinstance(p, float) and np.isnan(p)):
            ptxt = "     ."
        else:
            ptxt = f"{p:+6.0f}"
        print(f"{r['d'].date()}  ma7={r['lu_ratio_ma']*100:5.2f}%  pct1y={r['pct1y']:.2f}  "
              f"cnt={int(r['up_limit_count']):3d}  S002={ptxt}")


if __name__ == "__main__":
    main()
