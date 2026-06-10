"""H111 補充 — ext_long 對「達 L4」的召回/精度（按到達時點 + 純 forward）。

回答：ext_long@09:30 強(≥0.08) 真正抓到多少大漲日？用「到 L4 的時點」拆解，
顯示它是早盤趨勢訊號（午盤行情抓不到是先天極限）。源自 H113 追問。
資料：H113 ht_panel.csv（有 W50_09:30=ext_long、ema20、up_full）+ TX 各時點上行擺幅。
用法：uv run python research/active/H111-dci-long-reach-map/ext_long_recall.py
"""
from __future__ import annotations

from datetime import date, time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DB = str(HERE.parents[2] / "data" / "futures.duckdb")
LO, HI = date(2025, 6, 2), date(2026, 6, 30)     # 全資料窗（含 OOS）
IS_END = date(2026, 2, 26)                        # OOS = 2026-03-01 起
MARKS = {"0930": time(9, 30), "1000": time(10, 0), "1030": time(10, 30),
         "1100": time(11, 0), "1130": time(11, 30), "1345": time(13, 45)}
HT_PANEL = HERE / "results" / "reach_map_panel.csv"   # 自足：用 H111 自己的 panel（有 W50_09:30/ema20/up_full）


def tx_upswing():
    with duckdb.connect(DB, read_only=True) as c:
        bars = c.execute(
            "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, high, low FROM ohlcv_1m "
            "WHERE symbol='TX' AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
            "AND CAST(timestamp AS DATE) BETWEEN ? AND ? ORDER BY d,t", [LO, HI]).df()
    bars["high"] = bars["high"].astype(float); bars["low"] = bars["low"].astype(float)
    rows = []
    for d, g in bars.groupby("d"):
        g = g.sort_values("t"); hi, lo, t = g["high"].values, g["low"].values, list(g["t"].values)
        up = np.maximum.accumulate(hi - np.minimum.accumulate(lo))
        rec = {"d": pd.Timestamp(d).date()}
        for k, tm in MARKS.items():
            rec[k] = up[max(np.searchsorted(t, tm, side="right") - 1, 0)]
        rows.append(rec)
    return pd.DataFrame(rows).set_index("d")


def main():
    tx = tx_upswing()
    p = pd.read_csv(HT_PANEL)
    p["d"] = pd.to_datetime(p.iloc[:, 0]).dt.date
    p = p.set_index("d").join(tx)
    ema = p["ema20"]; strong = p["W50_09:30"] >= 0.08; nS = int(strong.sum()); N = len(p)
    L4 = 0.977 * ema

    print(f"ext_long(W50@09:30) 強(≥0.08) 對「達 L4」召回/精度  N={N}  強訊號日={nS}")
    print(f"{'到L4時點':>9}{'達標天':>7}{'抓到':>6}{'召回':>7}{'精度':>7}{'base→強':>11}")
    for k in ("1000", "1030", "1100", "1130", "1345"):
        hit = p[k] >= L4; n = int(hit.sum()); tp = int((hit & strong).sum())
        print(f"{k[:2]+':'+k[2:]+'前':>9}{n:>7}{tp:>6}{tp/n:>6.0%}{tp/nS:>7.0%}"
              f"{f'{n/N:.0%}→{tp/nS:.0%}':>11}")

    # 純 forward（排 gap-and-go：09:30 已到 L4）— 全窗 + IS/OOS 分割複驗
    notyet = p["0930"] < L4
    p_is = p.index <= IS_END
    print(f"\n純 forward（排 09:30 前已到 L4 的 {int((~notyet).sum())} 天 gap-and-go；母體 {int(notyet.sum())}）：")
    for seg_lab, seg in (("全窗", np.ones(len(p), bool)), ("IS", p_is), ("OOS", ~p_is)):
        ny_mask = notyet & seg
        for k, lab in (("1130", "09:30→11:30"),):
            fwd = ny_mask & (p[k] >= L4)
            y = fwd[ny_mask]; s = strong[ny_mask]
            ny = int(y.sum())
            if ny == 0:
                print(f"  [{seg_lab}] {lab} 新到L4 0 天（無樣本）"); continue
            tp = int((y & s).sum())
            print(f"  [{seg_lab}] {lab} 新到L4 {ny} 天｜強抓 {tp}（召回 {tp/ny:.0%}）｜"
                  f"base={y.mean():.0%}→強={y[s].mean():.0%}(lift {y[s].mean()-y.mean():+.0%}, N強={int(s.sum())})")


if __name__ == "__main__":
    main()
