"""H095 — 早盤碰 L1 後被洗掉，是否還有「第二波」到 L3？且趕得上 10:05 進場線嗎？

情境：L1 於 09:30 前觸及（強訊號、瞄 L3），但部位被停損洗掉。問：
  (1) 這些日子仍續攻 L2 / L3 的機率？
  (2) L3 觸及時間分佈：10:05 前 vs 後（決定第二波能不能在『10:05 不再進場』下被吃到）。
  (3) L1 觸及後的最大回吐(點/占 L1 比例)：是否深到真會洗掉部位 → 第二波是否名副其實。

EMA-only 關卡：L1=0.385 L2=0.497 L3=0.711 ×EMA20。directional, pooled 多空對稱。逐 bar 路徑。
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
from explore import DB, SYMBOL

C = {"L1": 0.385, "L2": 0.497, "L3": 0.711}
GATE_0930 = 570
T_1005 = 605  # 10:05


def load():
    with duckdb.connect(DB, read_only=True) as conn:
        b = conn.execute(
            "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, high, low FROM ohlcv_1m "
            "WHERE symbol=? AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
            "AND CAST(timestamp AS DATE)>=DATE '2020-01-01' ORDER BY timestamp", [SYMBOL]).df()
    b["d"] = pd.to_datetime(b["d"])
    b["high"] = b["high"].astype(float); b["low"] = b["low"].astype(float)
    tt = pd.to_datetime(b["t"].astype(str)); b["min"] = tt.dt.hour * 60 + tt.dt.minute
    return b


def first_idx(cond):
    return int(np.argmax(cond)) if cond.any() else None


def main():
    bars = load()
    day_rng = bars.groupby("d").apply(lambda g: g["high"].max() - g["low"].min()).sort_index()
    ema20 = day_rng.shift(1).ewm(span=20, adjust=False).mean()

    recs = []
    for d, g in bars.groupby("d"):
        e = ema20.get(d)
        if e is None or pd.isna(e):
            continue
        L1d, L2d, L3d = C["L1"] * e, C["L2"] * e, C["L3"] * e
        h, l, m = g["high"].to_numpy(), g["low"].to_numpy(), g["min"].to_numpy()
        for dr in ("up", "dn"):
            if dr == "up":
                swing = h - np.minimum.accumulate(l)          # 從低點往上
            else:
                swing = np.maximum.accumulate(h) - l          # 從高點往下
            t1 = first_idx(swing >= L1d)
            if t1 is None:
                continue
            t2 = first_idx(swing >= L2d)
            t3 = first_idx(swing >= L3d)
            # L1 觸及後到 L3(或收盤)前的最大回吐(逆向)
            end = t3 if t3 is not None else len(h) - 1
            if dr == "up":
                peak = np.maximum.accumulate(h[t1:end + 1])
                pb = float(np.max(peak - l[t1:end + 1])) if end >= t1 else 0.0
            else:
                trough = np.minimum.accumulate(l[t1:end + 1])
                pb = float(np.max(h[t1:end + 1] - trough)) if end >= t1 else 0.0
            recs.append({
                "d": d, "dr": dr, "l1_min": int(m[t1]),
                "reach_l2": t2 is not None, "reach_l3": t3 is not None,
                "l3_min": int(m[t3]) if t3 is not None else None,
                "pb": pb, "L1d": L1d,
            })
    R = pd.DataFrame(recs)
    E = R[R.l1_min < GATE_0930].copy()  # 早盤(09:30前)碰 L1
    n = len(E)
    print(f"早盤(09:30前)碰 L1：{n} 筆 (day×dir)\n")

    print("=== (1) 仍續攻機率 ===")
    print(f"  P(到 L2 | 早碰 L1) = {E.reach_l2.mean():.0%}")
    print(f"  P(到 L3 | 早碰 L1) = {E.reach_l3.mean():.0%}")

    l3 = E[E.reach_l3].copy()
    print(f"\n=== (2) 到 L3 的時間（{len(l3)} 筆）===")
    before = (l3.l3_min <= T_1005).mean()
    print(f"  L3 觸及時間中位 = {int(np.median(l3.l3_min))//60:02d}:{int(np.median(l3.l3_min))%60:02d}")
    print(f"  10:05(含)前到 L3：{before:.0%}   10:05 後：{1-before:.0%}")
    for lab, lo, hi in [("≤09:30", 0, 570), ("09:30–10:05", 571, 605),
                        ("10:05–11:00", 606, 660), (">11:00", 661, 9999)]:
        c = ((l3.l3_min >= lo) & (l3.l3_min <= hi)).sum()
        print(f"    {lab:<12}: {c:>4} ({c/len(l3):.0%})")

    print(f"\n=== (3) L1 後最大回吐（占 L1 距離比例）===")
    E["pb_frac"] = E.pb / E.L1d
    print(f"  全部早碰 L1：中位回吐 {np.median(E.pb_frac):.0%} L1   p75 {np.percentile(E.pb_frac,75):.0%}")
    deep = E[E.pb_frac >= 1.0]   # 回吐 ≥ 整個 L1 距離 = 跌破 L1、典型會洗掉部位
    print(f"  回吐 ≥100% L1（跌破 L1、強烈洗盤）：{len(deep)} 筆 ({len(deep)/n:.0%})")
    print(f"    其中仍到 L3：{deep.reach_l3.mean():.0%}")
    deep_l3 = deep[deep.reach_l3]
    if len(deep_l3):
        b2 = (deep_l3.l3_min <= T_1005).mean()
        print(f"    且這些『洗盤後到 L3』中，10:05 前到的：{b2:.0%}（其餘 {1-b2:.0%} 在 10:05 後）")

    # 中度洗盤 ≥50% L1
    mid = E[E.pb_frac >= 0.5]
    print(f"  回吐 ≥50% L1：{len(mid)} 筆 ({len(mid)/n:.0%})，其中仍到 L3：{mid.reach_l3.mean():.0%}")


if __name__ == "__main__":
    main()
