"""H097 後續 — 在 EMA-only 關卡定義下，重算 L1/L2/L3 觸及時間對續航的影響。

關卡距離一改成 c×EMA20，觸及時間就變，故 daystats 的三張續航表必須重算：
  _CONT_L2        : P(觸 L2 | L1 於時間 t 觸)
  _CONT_L3        : P(觸 L3 | L1 於時間 t 觸)   → 同時檢查 09:30 L3 時間閘是否仍成立
  _CONT_L3_FROM_L2: P(觸 L3 | L2 於時間 t 觸)
方法論同 H096（directional swing, pooled 多空對稱, 2021-2026）。

EMA-only 係數（H097 全樣本擬合）：L1=0.385 L2=0.497 L3=0.711（×EMA20）。
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
from explore import DB, SYMBOL  # 重用絕對 DB 路徑

# EMA-only 關卡係數（×EMA20）
C = {"L1": 0.385, "L2": 0.497, "L3": 0.711}
BUCKETS = [525, 540, 555, 570, 585, 600, 615, 630, 645]
LBL = {525: "08:45", 540: "09:00", 555: "09:15", 570: "09:30", 585: "09:45",
       600: "10:00", 615: "10:15", 630: "10:30", 645: "10:45"}


def load():
    with duckdb.connect(DB, read_only=True) as conn:
        bars = conn.execute(
            "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, high, low FROM ohlcv_1m "
            "WHERE symbol=? AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
            "AND CAST(timestamp AS DATE) >= DATE '2020-01-01' ORDER BY timestamp", [SYMBOL]).df()
    bars["d"] = pd.to_datetime(bars["d"])
    bars["high"] = bars["high"].astype(float)
    bars["low"] = bars["low"].astype(float)
    tt = pd.to_datetime(bars["t"].astype(str))
    bars["min"] = tt.dt.hour * 60 + tt.dt.minute
    return bars


def first_touches(g, dists):
    h, l, m = g["high"].to_numpy(), g["low"].to_numpy(), g["min"].to_numpy()
    up = np.maximum.accumulate(h - np.minimum.accumulate(l))
    dn = np.maximum.accumulate(np.maximum.accumulate(h) - l)
    out = {}
    for lvl, dist in dists.items():
        iu = np.argmax(up >= dist) if (up >= dist).any() else None
        idd = np.argmax(dn >= dist) if (dn >= dist).any() else None
        out[("bull", lvl)] = int(m[iu]) if iu is not None else None
        out[("bear", lvl)] = int(m[idd]) if idd is not None else None
    return out


def bucket(minute):
    b = BUCKETS[0]
    for s in BUCKETS:
        if minute >= s:
            b = s
        else:
            break
    return b


def main():
    bars = load()
    day_rng = bars.groupby("d").apply(lambda g: g["high"].max() - g["low"].min()).sort_index()
    ema20 = day_rng.shift(1).ewm(span=20, adjust=False).mean()

    recs = []
    for d, g in bars.groupby("d"):
        e = ema20.get(d)
        if e is None or pd.isna(e):
            continue
        ft = first_touches(g, {lvl: c * e for lvl, c in C.items()})
        for dr in ("bull", "bear"):
            recs.append({"d": d, "dir": dr, "L1": ft[(dr, "L1")],
                         "L2": ft[(dr, "L2")], "L3": ft[(dr, "L3")]})
    R = pd.DataFrame(recs)
    print(f"樣本 {len(R)} (day×dir)  {R['d'].min().date()}~{R['d'].max().date()}")
    print(f"  碰L1 {R['L1'].notna().mean():.0%} / 碰L2 {R['L2'].notna().mean():.0%} / 碰L3 {R['L3'].notna().mean():.0%}")
    print(f"  基準 P(L3|碰L1)={R[R.L1.notna()].L3.notna().mean():.0%}  "
          f"P(L3|碰L2)={R[R.L2.notna()].L3.notna().mean():.0%}  "
          f"P(L2|碰L1)={R[R.L1.notna()].L2.notna().mean():.0%}")

    def table(cond_col, target_col):
        sub = R[R[cond_col].notna()].copy()
        sub["bkt"] = sub[cond_col].apply(bucket)
        out = []
        for b in BUCKETS:
            s = sub[sub.bkt == b]
            p = round(s[target_col].notna().mean() * 100) if len(s) else None
            out.append((b, p, len(s)))
        return out

    def show(name, tbl, old):
        print(f"\n=== {name} ===")
        print(f"{'time':<7}{'新':>5}{'n':>6}   {'舊(雙參數)':>10}")
        for (b, p, n), o in zip(tbl, old):
            print(f"{LBL[b]:<7}{('—' if p is None else p):>5}{n:>6}   {o:>10}")
        print(f"  py: [{', '.join(f'({b}, {p})' for b,p,_ in tbl)}]")

    old_l2 = [87, 78, 78, 74, 68, 67, 66, 63, 42]
    old_l3 = [69, 58, 59, 56, 41, 44, 43, 39, 28]
    old_l3f2 = [90, 78, 83, 86, 80, 69, 72, 68, 54]
    show("_CONT_L2  P(觸L2 | L1於t觸)", table("L1", "L2"), old_l2)
    show("_CONT_L3  P(觸L3 | L1於t觸)", table("L1", "L3"), old_l3)
    show("_CONT_L3_FROM_L2  P(觸L3 | L2於t觸)", table("L2", "L3"), old_l3f2)

    # 09:30 L3 閘檢查：_CONT_L3 何時跌破 50%
    l3 = table("L1", "L3")
    cross = next((LBL[b] for b, p, _ in l3 if p is not None and p < 50), None)
    print(f"\n09:30 L3 時間閘檢查：_CONT_L3 首次跌破 50% 於 {cross}（舊定義為 09:45 那格 41%，閘設 09:30）")


if __name__ == "__main__":
    main()
