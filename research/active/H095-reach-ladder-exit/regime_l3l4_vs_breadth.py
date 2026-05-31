"""H095 — 用「L3/L4 行情實際出現」反推 net_adv 合理門檻，並檢查逐年穩定性。

問題：用 net_adv 分位定義「強廣度」會被多頭年扭曲。改問：
  L3/L4 上行情出現的日子，net_adv 到底長怎樣？net_adv 高 → L3/L4 機率真的高嗎？
  這關係在 2025/2026（窄幅多頭）會不會破功（指數噴但廣度弱）？

每日上行擺動(從盤中低點)達 L3/L4？(EMA-only L3=.711 L4=.977 ×EMA20) × 當日 net_adv(收盤,事後)。
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"
C_L3, C_L4 = 0.711, 0.977


def main():
    with duckdb.connect(DB, read_only=True) as c:
        bars = c.execute(
            "SELECT CAST(timestamp AS DATE) d, high, low FROM ohlcv_1m WHERE symbol='TX' "
            "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
            "AND CAST(timestamp AS DATE)>=DATE '2021-01-01' ORDER BY timestamp").df()
        b = c.execute("SELECT trade_date, up_count, down_count, listed_count "
                      "FROM market_breadth WHERE market='TWSE'").df()
    bars["d"] = pd.to_datetime(bars["d"]); bars["high"] = bars["high"].astype(float); bars["low"] = bars["low"].astype(float)
    rng = bars.groupby("d").apply(lambda g: g["high"].max() - g["low"].min()).sort_index()
    ema20 = rng.shift(1).ewm(span=20, adjust=False).mean()

    rows = []
    for d, g in bars.groupby("d"):
        e = ema20.get(d)
        if e is None or pd.isna(e):
            continue
        up = float((g["high"].to_numpy() - np.minimum.accumulate(g["low"].to_numpy())).max())
        rows.append({"d": d, "reach_l3": up >= C_L3 * e, "reach_l4": up >= C_L4 * e})
    R = pd.DataFrame(rows)
    R["date"] = R.d.dt.date
    b["date"] = pd.to_datetime(b.trade_date).dt.date
    b["net_adv"] = (b.up_count - b.down_count) / b.listed_count
    m = R.merge(b[["date", "net_adv"]], on="date", how="inner")
    m["year"] = pd.to_datetime(m.date).dt.year
    print(f"n={len(m)} 交易日，2021–2026\n")

    print("=== P(上行到 L3 / L4) by net_adv 區間（pooled）===")
    bins = [-1, -0.3, -0.1, 0.1, 0.3, 0.5, 1]
    lbl = ["<-.3", "-.3~-.1", "-.1~.1", ".1~.3", ".3~.5", ">=.5"]
    m["bin"] = pd.cut(m.net_adv, bins, labels=lbl)
    g = m.groupby("bin", observed=True).agg(n=("reach_l3", "size"),
                                            P_L3=("reach_l3", "mean"), P_L4=("reach_l4", "mean"))
    print(g.assign(P_L3=lambda x: (x.P_L3*100).round(0), P_L4=lambda x: (x.P_L4*100).round(0)).to_string())
    print(f"\n  無條件：P(L3)={m.reach_l3.mean():.0%}  P(L4)={m.reach_l4.mean():.0%}")

    # 逐年：net_adv 對 L3 的鑑別力是否穩定（高 vs 低 net_adv 的 L3 率差）
    print("\n=== 逐年 net_adv↔L3 鑑別力（門檻 net_adv≥0.3）===")
    print(f"{'年':>6}{'n':>5}{'指數年漲跌%':>12}{'net_adv均':>10}{'P(L3|高)':>10}{'P(L3|低)':>10}{'鑑別差':>8}")
    for y, sub in m.groupby("year"):
        hi = sub[sub.net_adv >= 0.3]; lo = sub[sub.net_adv < 0.3]
        ph = hi.reach_l3.mean() if len(hi) else np.nan
        pl = lo.reach_l3.mean() if len(lo) else np.nan
        # 該年期貨漲跌（用日盤收盤近似：年末-年初 / 年初）
        print(f"{y:>6}{len(sub):>5}{'':>12}{sub.net_adv.mean():>+10.2f}"
              f"{ph:>10.0%}{pl:>10.0%}{(ph-pl):>+8.0%}")

    # L3/L4 日 vs 非 L3 日的 net_adv 分佈（找門檻）
    print("\n=== L3 日 vs 非 L3 日的 net_adv 分佈（看是否分得開）===")
    for lab, sub in [("到 L3 日", m[m.reach_l3]), ("沒到 L3 日", m[~m.reach_l3]),
                     ("到 L4 日", m[m.reach_l4])]:
        print(f"  {lab:<10} n={len(sub):>4}  net_adv 中位={sub.net_adv.median():+.2f}  "
              f"p25={sub.net_adv.quantile(.25):+.2f}  p75={sub.net_adv.quantile(.75):+.2f}")


if __name__ == "__main__":
    main()
