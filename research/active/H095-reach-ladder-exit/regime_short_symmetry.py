"""H095 — regime 指標的多空對稱性檢查。

多方驗證過：indicator 正向 → 上行到 L3/L4。空方是否只是反號對稱？
檢查 indicator 與「下行到 L3/L4」的相關（若對稱，應為與上行相反號、同強度）。
台股有上漲漂移 + 跌勢通常較廣（賣壓齊跌），故預期不完全對稱。
indicators: net_adv / vw_net / top20_vw（同前；皆收盤值、事後）。
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
              (SUM(CASE WHEN change>0 THEN 1 ELSE 0 END)-SUM(CASE WHEN change<0 THEN 1 ELSE 0 END))*1.0/COUNT(*) net_adv,
              SUM(SIGN(change)*value)/NULLIF(SUM(value),0) vw_net
            FROM stock_day WHERE market='TWSE' AND change IS NOT NULL AND value IS NOT NULL
            GROUP BY trade_date""").df()
        t20 = c.execute("""
            WITH r AS (SELECT trade_date, change, value,
                         ROW_NUMBER() OVER (PARTITION BY trade_date ORDER BY value DESC) rn
                       FROM stock_day WHERE market='TWSE' AND value IS NOT NULL AND change IS NOT NULL)
            SELECT trade_date, SUM(SIGN(change)*value)/NULLIF(SUM(value),0) top20_vw
            FROM r WHERE rn<=20 GROUP BY trade_date""").df()
        bars = c.execute(
            "SELECT CAST(timestamp AS DATE) d, high, low FROM ohlcv_1m WHERE symbol='TX' "
            "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
            "AND CAST(timestamp AS DATE)>=DATE '2021-01-01' ORDER BY timestamp").df()
    s = sd.merge(t20, on="trade_date"); s["date"] = pd.to_datetime(s.trade_date).dt.date

    bars["d"] = pd.to_datetime(bars["d"]); bars["high"] = bars["high"].astype(float); bars["low"] = bars["low"].astype(float)
    rng = bars.groupby("d").apply(lambda g: g["high"].max() - g["low"].min()).sort_index()
    ema20 = rng.shift(1).ewm(span=20, adjust=False).mean()
    rows = []
    for d, g in bars.groupby("d"):
        e = ema20.get(d)
        if e is None or pd.isna(e):
            continue
        h, l = g["high"].to_numpy(), g["low"].to_numpy()
        up = float((h - np.minimum.accumulate(l)).max())
        dn = float((np.maximum.accumulate(h) - l).max())
        rows.append({"date": d.date(), "up_l3": int(up >= C_L3*e), "up_l4": int(up >= C_L4*e),
                     "dn_l3": int(dn >= C_L3*e), "dn_l4": int(dn >= C_L4*e)})
    R = pd.DataFrame(rows)
    m = R.merge(s[["date", "net_adv", "vw_net", "top20_vw"]], on="date", how="inner")
    m["year"] = pd.to_datetime(m.date).dt.year
    print(f"n={len(m)}，2021–2026")
    print(f"基準率：上行到L3={m.up_l3.mean():.0%} L4={m.up_l4.mean():.0%}  |  "
          f"下行到L3={m.dn_l3.mean():.0%} L4={m.dn_l4.mean():.0%}\n")

    print("=== indicator 與 上行/下行 到 L3/L4 的相關（對稱 → 上行+、下行−、同強度）===")
    print(f"{'指標':<10}{'up_L3':>8}{'dn_L3':>8}{'up_L4':>8}{'dn_L4':>8}{'  |對稱?':>10}")
    for ind in ["net_adv", "vw_net", "top20_vw"]:
        u3, d3 = m[ind].corr(m.up_l3), m[ind].corr(m.dn_l3)
        u4, d4 = m[ind].corr(m.up_l4), m[ind].corr(m.dn_l4)
        sym = "對稱" if abs(abs(u3)-abs(d3)) < 0.05 else ("空方弱" if abs(d3) < abs(u3) else "空方強")
        print(f"{ind:<10}{u3:>+8.2f}{d3:>+8.2f}{u4:>+8.2f}{d4:>+8.2f}{sym:>10}")

    # 哪個指標對空方最好（下行）；以及跌勢是否較廣（家數 vs 加權 對空方的相對表現）
    print("\n=== 下行 L3：P(下行到L3) by 指標四分位（最低分位=最空）===")
    for ind in ["net_adv", "vw_net", "top20_vw"]:
        m["q"] = pd.qcut(m[ind], 4, labels=["Q1最空", "Q2", "Q3", "Q4最多"])
        g = m.groupby("q", observed=True).dn_l3.mean()
        print(f"  {ind:<10} " + "  ".join(f"{q}={v:.0%}" for q, v in g.items())
              + f"   最空-最多={g.iloc[0]-g.iloc[-1]:+.0%}")
    print("\n  （多方對照：見前一腳本，net_adv Q4高 66% / Q1低 43%）")


if __name__ == "__main__":
    main()
