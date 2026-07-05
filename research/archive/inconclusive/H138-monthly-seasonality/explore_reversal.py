#!/usr/bin/env python3
"""H138 衍生：季節窗口當「濾網」對 long-only 日盤策略的影響。

問題：即使日內指數漂移小，季節性偏多是否墊高既有 long-only 策略（S001/S002）
      在那幾天的條件期望值？

做法：把 S001-esthl / S002-reversal 的歷史成交（2021-2026）依進場日期標記是否落在
      季節窗口，比較窗內 vs 窗外的勝率、平均 ReturnPct、期望值。

注意：TX 僅 2021-2026，窗內成交數很少（N 小），僅方向判讀。
"""
import duckdb
import numpy as np
import pandas as pd
from pathlib import Path

DB = Path(__file__).parents[3] / "data" / "futures.duckdb"
OUT = Path(__file__).parents[3] / "output"
STRATS = {
    "S001-esthl":   OUT / "s001_esthl_2021-01-01_2026-04-30.csv",
    "S002-reversal": OUT / "s002_reversal_2021-01-01_2026-04-30.csv",
}


def tx_calendar():
    """TX 日盤交易日 + 日曆月序位（pos / rpos）。"""
    with duckdb.connect(str(DB), read_only=True) as c:
        d = c.execute("""
            SELECT DISTINCT timestamp::DATE AS d FROM ohlcv_1m
            WHERE symbol='TX' AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            ORDER BY d
        """).df()
    d["d"] = pd.to_datetime(d["d"])
    d["year"] = d["d"].dt.year
    d["mon"] = d["d"].dt.month
    g = d.groupby(["year", "mon"])
    d["pos"] = g.cumcount() + 1
    d["rpos"] = g["d"].transform("size") - g.cumcount()
    return d


def label(d):
    """回傳各種季節標記布林欄。"""
    d = d.copy()
    d["in_combined"] = ((d.mon == 7) & (d.pos <= 10)) | ((d.mon == 8) & (d.rpos <= 7))
    d["in_julhead"] = (d.mon == 7) & (d.pos <= 10)
    d["in_augtail"] = (d.mon == 8) & (d.rpos <= 7)
    d["in_julaug"] = d.mon.isin([7, 8])
    return d


def summarize(sub, name):
    if len(sub) == 0:
        return f"  {name:16s} N=0"
    r = sub["ReturnPct"].to_numpy() * 100  # %
    return (f"  {name:16s} N={len(sub):4d}  勝率{(r>0).mean()*100:4.0f}%  "
            f"平均{r.mean():+.3f}%  期望(總/交易){r.sum():+6.1f}/{r.mean():+.3f}  "
            f"中位{np.median(r):+.3f}%")


def analyze(strat, csv, cal):
    if not csv.exists():
        print(f"[skip] {strat}: 找不到 {csv}")
        return
    t = pd.read_csv(csv, parse_dates=["EntryTime"])
    t["d"] = t["EntryTime"].dt.normalize()
    t = t.merge(cal[["d", "mon", "pos", "rpos", "in_combined", "in_julhead",
                     "in_augtail", "in_julaug"]], on="d", how="left")
    print(f"\n### {strat}  （總 {len(t)} 筆，{t['d'].min().date()}~{t['d'].max().date()}）")
    print(summarize(t, "全部(baseline)"))
    print(summarize(t[t.in_combined], "組合窗內"))
    print(summarize(t[~t.in_combined], "組合窗外"))
    print(summarize(t[t.in_julhead], "七月頭10"))
    print(summarize(t[t.in_augtail], "八月末7"))
    print(summarize(t[t.in_julaug], "七+八月(整月)"))
    print(summarize(t[~t.in_julaug], "其餘10個月"))


def perm_test(strat, csv, cal, mask_col, n_perm=5000, seed=42):
    """窗內 N 筆 vs 隨機同數量子集：窗內平均/勝率的百分位。"""
    t = pd.read_csv(csv, parse_dates=["EntryTime"])
    t["d"] = t["EntryTime"].dt.normalize()
    t = t.merge(cal[["d", mask_col]], on="d", how="left")
    r = (t["ReturnPct"].to_numpy()) * 100
    inmask = t[mask_col].fillna(False).to_numpy()
    k = int(inmask.sum())
    obs_mean = r[inmask].mean(); obs_win = (r[inmask] > 0).mean() * 100
    rng = np.random.default_rng(seed)
    nm = np.empty(n_perm); nw = np.empty(n_perm)
    for i in range(n_perm):
        idx = rng.choice(len(r), k, replace=False)
        nm[i] = r[idx].mean(); nw[i] = (r[idx] > 0).mean() * 100
    print(f"  [{strat} · {mask_col}] N={k}  平均{obs_mean:+.3f}%(百分位{(nm<obs_mean).mean()*100:.1f}th) "
          f"勝率{obs_win:.0f}%(百分位{(nw<obs_win).mean()*100:.1f}th)")


if __name__ == "__main__":
    cal = label(tx_calendar())
    print(f"TX 交易日曆 {cal['d'].min().date()}~{cal['d'].max().date()}  N={len(cal)}")
    for strat, csv in STRATS.items():
        analyze(strat, csv, cal)
    print("\n### Permutation（窗內 vs 隨機同量子集，5000×）")
    for strat, csv in STRATS.items():
        for col in ["in_combined", "in_julhead"]:
            perm_test(strat, csv, cal, col)
