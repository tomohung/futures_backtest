"""H095 — 加權廣度 / 前20大 vs equal-weight net_adv，對 L3/L4 的鑑別力對比。

動機：equal-weight net_adv 在窄幅多頭年(2024/2026)鑑別 L3/L4 破功。試三個指標：
  net_adv     : (漲-跌)/家數                          equal-weight 計數
  vw_net      : Σ sign(漲跌)×成交值 / Σ成交值           成交值加權（偏權值股）
  top20_vw    : 同上但只取當日成交值前 20 大            前20大方向
比較：對「上行到 L3」的 point-biserial 相關，pooled + 逐年（看 2024/2026 是否補起來）。
成交值為市值代理（無流通股數）；皆收盤值，事後驗證機制用。
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"
C_L3, C_L4 = 0.711, 0.977


def main():
    with duckdb.connect(DB, read_only=True) as c:
        sd = c.execute("""
            SELECT trade_date,
              SUM(CASE WHEN change>0 THEN 1 ELSE 0 END) up,
              SUM(CASE WHEN change<0 THEN 1 ELSE 0 END) dn,
              COUNT(*) n,
              SUM(SIGN(change)*value)/NULLIF(SUM(value),0) vw_net
            FROM stock_day WHERE market='TWSE' AND change IS NOT NULL AND value IS NOT NULL
            GROUP BY trade_date""").df()
        t20 = c.execute("""
            WITH r AS (SELECT trade_date, change, value,
                         ROW_NUMBER() OVER (PARTITION BY trade_date ORDER BY value DESC) rn
                       FROM stock_day WHERE market='TWSE' AND value IS NOT NULL AND change IS NOT NULL)
            SELECT trade_date,
              SUM(SIGN(change)*value)/NULLIF(SUM(value),0) top20_vw,
              (SUM(CASE WHEN change>0 THEN 1 ELSE 0 END)-SUM(CASE WHEN change<0 THEN 1 ELSE 0 END))/20.0 top20_cnt
            FROM r WHERE rn<=20 GROUP BY trade_date""").df()
        bars = c.execute(
            "SELECT CAST(timestamp AS DATE) d, high, low FROM ohlcv_1m WHERE symbol='TX' "
            "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
            "AND CAST(timestamp AS DATE)>=DATE '2021-01-01' ORDER BY timestamp").df()

    sd["net_adv"] = (sd.up - sd.dn) / sd.n
    s = sd.merge(t20, on="trade_date")
    s["date"] = pd.to_datetime(s.trade_date).dt.date

    bars["d"] = pd.to_datetime(bars["d"]); bars["high"] = bars["high"].astype(float); bars["low"] = bars["low"].astype(float)
    rng = bars.groupby("d").apply(lambda g: g["high"].max() - g["low"].min()).sort_index()
    ema20 = rng.shift(1).ewm(span=20, adjust=False).mean()
    rows = []
    for d, g in bars.groupby("d"):
        e = ema20.get(d)
        if e is None or pd.isna(e):
            continue
        up = float((g["high"].to_numpy() - np.minimum.accumulate(g["low"].to_numpy())).max())
        rows.append({"date": d.date(), "l3": int(up >= C_L3 * e), "l4": int(up >= C_L4 * e)})
    R = pd.DataFrame(rows)
    m = R.merge(s[["date", "net_adv", "vw_net", "top20_vw", "top20_cnt"]], on="date", how="inner")
    m["year"] = pd.to_datetime(m.date).dt.year
    inds = ["net_adv", "vw_net", "top20_vw", "top20_cnt"]
    print(f"n={len(m)}，2021–2026\n")

    print("=== 各指標 vs L3 的相關（point-biserial）pooled + 逐年 ===")
    print(f"{'指標':<10}{'pooled':>8}" + "".join(f"{y:>7}" for y in sorted(m.year.unique())))
    for ind in inds:
        line = f"{ind:<10}{m[ind].corr(m.l3):>8.2f}"
        for y in sorted(m.year.unique()):
            sub = m[m.year == y]
            line += f"{sub[ind].corr(sub.l3):>7.2f}"
        print(line)

    print("\n=== 各指標 vs L4 的相關 pooled + 逐年 ===")
    print(f"{'指標':<10}{'pooled':>8}" + "".join(f"{y:>7}" for y in sorted(m.year.unique())))
    for ind in inds:
        line = f"{ind:<10}{m[ind].corr(m.l4):>8.2f}"
        for y in sorted(m.year.unique()):
            sub = m[m.year == y]
            line += f"{sub[ind].corr(sub.l4):>7.2f}"
        print(line)

    print("\n=== P(到 L3) by 指標四分位（pooled）===")
    for ind in inds:
        m["q"] = pd.qcut(m[ind], 4, labels=["Q1低", "Q2", "Q3", "Q4高"])
        g = m.groupby("q", observed=True).l3.mean()
        print(f"  {ind:<10} " + "  ".join(f"{q}={v:.0%}" for q, v in g.items())
              + f"   高-低差={g.iloc[-1]-g.iloc[0]:+.0%}")


if __name__ == "__main__":
    main()
