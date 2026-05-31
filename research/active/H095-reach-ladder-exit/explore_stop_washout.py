"""H095 — 早碰 L1 後，「⅔ 鎖」vs「成本(BE)」停損，被洗出去的比例？

模型（多方，空方對稱）：
- 這波起點 base = L1 首次觸及那根的 swing 錨點(running min low)。假設進場≈base。
- 固定價目標：TgtL2 = base+L2_dist、TgtL3 = base+L3_dist。
- 兩種停損（相對 base，與進場價精確值無關的比較）：
    BE   = base                （移到成本）
    L23  = base + ⅔×L1_dist    （鎖住 ⅔ 的 L1 獲利）
- 自 L1 觸及後逐 bar：low ≤ 停損 → 被洗；high ≥ 目標 → 達標。同根都中視為先被洗(保守)。

兩個視角：
(A) 全部早碰 L1：各停損下的結局分佈。
(B) 只看「最終會到 L3」的日子：各停損會在到 L3 前把你洗掉的比例（洗掉贏家）。
關卡 EMA-only：L1=.385 L2=.497 L3=.711 ×EMA20。
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
from explore import DB, SYMBOL

C = {"L1": 0.385, "L2": 0.497, "L3": 0.711}
GATE_0930 = 570


def load():
    with duckdb.connect(DB, read_only=True) as conn:
        b = conn.execute(
            "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, high, low FROM ohlcv_1m "
            "WHERE symbol=? AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
            "AND CAST(timestamp AS DATE)>=DATE '2020-01-01' ORDER BY timestamp", [SYMBOL]).df()
    b["d"] = pd.to_datetime(b["d"]); b["high"] = b["high"].astype(float); b["low"] = b["low"].astype(float)
    tt = pd.to_datetime(b["t"].astype(str)); b["min"] = tt.dt.hour * 60 + tt.dt.minute
    return b


def fidx(c):
    return int(np.argmax(c)) if c.any() else None


def simulate(h, l, t1, base, sign, L1d, L2d, L3d, stop):
    """sign=+1 多 / -1 空。回傳 (reach_l2, reach_l3, stopped_before_l3)。價格用 sign 正規化後比較。"""
    tgt2 = base + sign * L2d
    tgt3 = base + sign * L3d
    reach2 = reach3 = False
    stopped3 = False
    for i in range(t1 + 1, len(h)):
        hi, lo = h[i], l[i]
        adverse = lo if sign > 0 else hi      # 對多方不利的是低點
        favor = hi if sign > 0 else lo        # 對多方有利的是高點
        hit_stop = (adverse <= stop) if sign > 0 else (adverse >= stop)
        if hit_stop:                          # 同根先被洗(保守)
            if not reach3:
                stopped3 = True
            break
        if sign > 0:
            if favor >= tgt2:
                reach2 = True
            if favor >= tgt3:
                reach3 = True; break
        else:
            if favor <= tgt2:
                reach2 = True
            if favor <= tgt3:
                reach3 = True; break
    return reach2, reach3, stopped3


def main():
    bars = load()
    dr_ = bars.groupby("d").apply(lambda g: g["high"].max() - g["low"].min()).sort_index()
    ema20 = dr_.shift(1).ewm(span=20, adjust=False).mean()

    rows = []
    for d, g in bars.groupby("d"):
        e = ema20.get(d)
        if e is None or pd.isna(e):
            continue
        L1d, L2d, L3d = C["L1"] * e, C["L2"] * e, C["L3"] * e
        h, l = g["high"].to_numpy(), g["low"].to_numpy()
        for sign, name in ((1, "up"), (-1, "dn")):
            swing = (h - np.minimum.accumulate(l)) if sign > 0 else (np.maximum.accumulate(h) - l)
            t1 = fidx(swing >= L1d)
            if t1 is None or g["min"].to_numpy()[t1] >= GATE_0930:
                continue
            base = np.minimum.accumulate(l)[t1] if sign > 0 else np.maximum.accumulate(h)[t1]
            rec = {}
            for stop_name, stop in (("BE", base), ("L23", base + sign * (2 / 3) * L1d)):
                r2, r3, st3 = simulate(h, l, t1, base, sign, L1d, L2d, L3d, stop)
                rec[stop_name] = (r2, r3, st3)
            # 真實是否到 L3（無停損、固定目標）
            tgt3 = base + sign * L3d
            favor_all = (np.maximum.accumulate(h[t1:]) if sign > 0 else np.minimum.accumulate(l[t1:]))
            true_l3 = (favor_all[-1] >= tgt3) if sign > 0 else (favor_all[-1] <= tgt3)
            rows.append({"BE": rec["BE"], "L23": rec["L23"], "true_l3": bool(true_l3)})
    R = pd.DataFrame(rows)
    n = len(R)
    print(f"早盤(09:30前)碰 L1：{n} 筆\n")

    print("=== (A) 各停損下的結局（全部早碰 L1）===")
    for s in ("BE", "L23"):
        r3 = R[s].apply(lambda x: x[1]).mean()
        st = R[s].apply(lambda x: x[2]).mean()
        nm = {"BE": "成本(BE)", "L23": "鎖⅔ L1"}[s]
        print(f"  {nm:<10} 到 L3 = {r3:.0%}   未到 L3 前被洗 = {st:.0%}")

    print("\n=== (B) 只看『最終會到 L3』的日子：停損把你洗掉的比例（洗掉贏家）===")
    win = R[R.true_l3]
    print(f"  最終到 L3 的日子：{len(win)} 筆")
    for s in ("BE", "L23"):
        washed = win[s].apply(lambda x: x[2]).mean()   # 到 L3 前被停損
        nm = {"BE": "成本(BE)", "L23": "鎖⅔ L1"}[s]
        print(f"  {nm:<10} 在到 L3 前被洗出去 = {washed:.0%}  → 抱住到 L3 = {1-washed:.0%}")


if __name__ == "__main__":
    main()
