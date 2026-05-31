"""H095 — 修正版：把「洗盤後第二波」和「方向做反」分開。

前版用多空都算 → 整天反向的日子被誤計為「洗盤」。正確問法：
在『早碰 L1 且最終到 L3』的日子裡，到 L3 之前的最大回吐有多深？(才是真正的洗盤後第二波)
並把早碰 L1 分成三類：乾淨直達 / 洗盤後第二波 / 沒到 L3。
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
from explore import DB, SYMBOL

C = {"L1": 0.385, "L2": 0.497, "L3": 0.711}
GATE_0930, T_1005 = 570, 605


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


def fidx(c):
    return int(np.argmax(c)) if c.any() else None


def main():
    bars = load()
    dr_ = bars.groupby("d").apply(lambda g: g["high"].max() - g["low"].min()).sort_index()
    ema20 = dr_.shift(1).ewm(span=20, adjust=False).mean()

    rows = []
    for d, g in bars.groupby("d"):
        e = ema20.get(d)
        if e is None or pd.isna(e):
            continue
        L1d, L3d = C["L1"] * e, C["L3"] * e
        h, l, m = g["high"].to_numpy(), g["low"].to_numpy(), g["min"].to_numpy()
        for dr in ("up", "dn"):
            swing = (h - np.minimum.accumulate(l)) if dr == "up" else (np.maximum.accumulate(h) - l)
            t1 = fidx(swing >= L1d)
            if t1 is None or m[t1] >= GATE_0930:
                continue  # 只看早盤(09:30前)碰 L1
            t3 = fidx(swing >= L3d)
            reach = t3 is not None
            # 到 L3(或收盤)前，從 L1 觸及後的最大回吐(逆向)
            end = t3 if reach else len(h) - 1
            if dr == "up":
                pb = float(np.max(np.maximum.accumulate(h[t1:end + 1]) - l[t1:end + 1]))
            else:
                pb = float(np.max(h[t1:end + 1] - np.minimum.accumulate(l[t1:end + 1])))
            rows.append({"reach_l3": reach, "l3_min": m[t3] if reach else None,
                         "pb_frac": pb / L1d})
    R = pd.DataFrame(rows)
    n = len(R)
    print(f"早盤(09:30前)碰 L1：{n} 筆\n")

    # 停損代理門檻：鎖⅔L1 → 回吐 ≥⅓(33%) 就被洗；另看 50% / 100%
    for thr, lab in [(0.33, "⅓ L1(鎖⅔被洗)"), (0.50, "½ L1"), (1.0, "整個 L1(跌破起點)")]:
        washed = R[R.pb_frac >= thr]
        print(f"到 L3 前回吐 ≥{lab}：{len(washed)} 筆 ({len(washed)/n:.0%})")

    print("\n=== 早碰 L1 的三分類 ===")
    reach = R[R.reach_l3]
    clean = reach[reach.pb_frac < 0.33]      # 乾淨直達(沒被洗)
    shake = reach[reach.pb_frac >= 0.33]     # 洗盤後仍到 L3(第二波)
    nol3 = R[~R.reach_l3]
    print(f"  乾淨直達 L3（回吐<⅓L1）      ：{len(clean):>4} ({len(clean)/n:.0%})")
    print(f"  洗盤後第二波到 L3（回吐≥⅓L1）：{len(shake):>4} ({len(shake)/n:.0%})")
    print(f"  沒到 L3                       ：{len(nol3):>4} ({len(nol3)/n:.0%})")

    print(f"\n=== 真正『洗盤後第二波到 L3』({len(shake)} 筆) 的到 L3 時間 ===")
    b = (shake.l3_min <= T_1005).mean()
    print(f"  中位 {int(np.median(shake.l3_min))//60:02d}:{int(np.median(shake.l3_min))%60:02d}；"
          f"10:05 前到 {b:.0%}，10:05 後 {1-b:.0%}")
    for lab, lo, hi in [("≤10:05", 0, 605), ("10:05–11:00", 606, 660), (">11:00", 661, 9999)]:
        c = ((shake.l3_min >= lo) & (shake.l3_min <= hi)).sum()
        print(f"    {lab:<12}: {c/len(shake):.0%}")

    # 對照：沒被洗(乾淨)的回吐分佈，確認門檻合理
    print(f"\n參考：reach_l3 整體回吐中位 {np.median(reach.pb_frac):.0%} L1，"
          f"p75 {np.percentile(reach.pb_frac,75):.0%}")


if __name__ == "__main__":
    main()
