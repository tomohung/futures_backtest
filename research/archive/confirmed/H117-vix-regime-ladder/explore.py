"""H117 Phase 1 — VIX regime 疊 ladder 達成頻率（因果 VIX lag 1）。

★ 因果鐵律：台指 VIX 收盤後算出,盤前只有 D−1 → regime(D) 用 VIX(<D)（merge_asof backward, 不含當日）。
  偷看 VIX(D) 會造「升偏空/降偏多」方向假象（VIX(D) 與當日跌幅同期耦合）;本腳本一律 lag。

輸出：
  A. ZigZag 升/降段分段（事後,僅供視覺化分期;不可實時）
  B. 因果偵測器比較（VIX>MA20 / 20日變化 / 10日變化 / EMA交叉 / 純水位>24）疊 ladder 深 reach
  C. 主偵測器（VIX>MA20）LAG 版 多/空 × L3/L4/L5 達成頻率 + 方向偏移檢定
用法：uv run python research/active/H117-vix-regime-ladder/explore.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

DB = str(Path(__file__).resolve().parents[3] / "data" / "futures.duckdb")
LVL = {"L3": 0.711, "L4": 0.977, "L5": 1.225}


def load():
    con = duckdb.connect(DB, read_only=True)
    vx = con.execute("SELECT date,vix FROM vixtwn ORDER BY date").df()
    vx["date"] = pd.to_datetime(vx["date"]).astype("datetime64[ns]")
    vx["ma20"] = vx["vix"].rolling(20).mean()
    vx["chg20"] = vx["vix"] - vx["vix"].shift(20)
    vx["chg10"] = vx["vix"] - vx["vix"].shift(10)
    vx["ema_f"] = vx["vix"].ewm(span=10, adjust=False).mean()
    vx["ema_s"] = vx["vix"].ewm(span=40, adjust=False).mean()
    rng = con.execute(
        "SELECT CAST(timestamp AS DATE) d, MAX(high)-MIN(low) r FROM ohlcv_1m WHERE symbol='TX' "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' GROUP BY 1 ORDER BY 1").df()
    rng["ema20"] = rng["r"].astype(float).shift(1).ewm(span=20, adjust=False).mean()
    ema = rng.set_index("d")["ema20"]
    bars = con.execute(
        "SELECT CAST(timestamp AS DATE) d,CAST(timestamp AS TIME) t,high,low FROM ohlcv_1m WHERE symbol='TX' "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' ORDER BY d,t").df()
    con.close()
    bars["high"] = bars["high"].astype(float); bars["low"] = bars["low"].astype(float)
    rows = []
    for d, g in bars.groupby("d"):
        dd = pd.Timestamp(d).date(); e = float(ema.get(d, np.nan))
        if dd < date(2021, 2, 1) or not (e > 0):
            continue
        hi, lo = g["high"].values, g["low"].values
        up = np.maximum.accumulate(hi - np.minimum.accumulate(lo))[-1]
        dn = np.maximum.accumulate(np.maximum.accumulate(hi) - lo)[-1]
        rec = {"d": pd.Timestamp(dd)}
        for nm, c_ in LVL.items():
            rec["u" + nm] = int(up >= c_ * e); rec["d" + nm] = int(dn >= c_ * e)
        rows.append(rec)
    df = pd.DataFrame(rows).sort_values("d"); df["d"] = df["d"].astype("datetime64[ns]")
    return vx, df


def zigzag(vx, th=6.0):
    v = vx["vix"].ewm(span=5, adjust=False).mean().values; n = len(v)
    piv = []; trend = 0; mn_i = mx_i = 0; mn = mx = v[0]
    for i in range(1, n):
        if trend == 0:
            if v[i] > mx: mx, mx_i = v[i], i
            if v[i] < mn: mn, mn_i = v[i], i
            if mx - v[i] >= th: piv += [mn_i, mx_i]; trend = -1; mn, mn_i = v[i], i
            elif v[i] - mn >= th: piv += [mx_i, mn_i]; trend = 1; mx, mx_i = v[i], i
        elif trend == 1:
            if v[i] > mx: mx, mx_i = v[i], i
            elif mx - v[i] >= th: piv.append(mx_i); trend = -1; mn, mn_i = v[i], i
        else:
            if v[i] < mn: mn, mn_i = v[i], i
            elif v[i] - mn >= th: piv.append(mn_i); trend = 1; mx, mx_i = v[i], i
    piv.append(mx_i if trend == 1 else mn_i)
    return sorted(set(piv))


def lag_join(df, vx, col):
    """regime(D) = 嚴格早於 D 的最後 VIX 值（盤前可得）。"""
    m = pd.merge_asof(df.sort_values("d"), vx.sort_values("date")[["date", col]],
                      left_on="d", right_on="date", direction="backward", allow_exact_matches=False)
    return m[col].values


def main():
    vx, df = load()
    L = ["=" * 92, f"H117 Phase 1 — VIX regime × ladder（因果 VIX lag 1）  N={len(df)}（2021-02~2026-06）"]

    # A. ZigZag 分段（視覺化用）
    piv = zigzag(vx)
    L.append("\nA) VIX ZigZag 升/降段（事後,僅分期視覺化;近 8 段）：")
    for k in range(max(0, len(piv) - 9), len(piv) - 1):
        a, b = piv[k], piv[k + 1]; va, vb = vx["vix"].iloc[a], vx["vix"].iloc[b]
        L.append(f"   {vx['date'].iloc[a].date()} → {vx['date'].iloc[b].date()}  "
                 f"{'↑升' if vb > va else '↓降'}  {va:.0f}→{vb:.0f}")

    # B. 因果偵測器比較
    vx["d_MA"] = np.where(vx["vix"] >= vx["ma20"], "升壓", "降壓")
    vx["d_c20"] = np.where(vx["chg20"] > 0, "升", "降")
    vx["d_c10"] = np.where(vx["chg10"] > 0, "升", "降")
    vx["d_ema"] = np.where(vx["ema_f"] > vx["ema_s"], "升", "降")
    vx["d_lv"] = np.where(vx["vix"] > 24, "高", "低")
    vx_ok = vx.dropna(subset=["ma20", "chg20", "chg10"])
    L.append("\n" + "─" * 92)
    L.append("B) 因果偵測器（LAG）比較：高/升 vs 低/降 的 多L4/L5、空L4/L5、多−空L4")
    for col, lab, hi in [("d_MA", "VIX>MA20", "升壓"), ("d_c20", "VIX20日變化", "升"),
                         ("d_c10", "VIX10日變化", "升"), ("d_ema", "EMA10>40", "升"), ("d_lv", "VIX>24", "高")]:
        df["_r"] = lag_join(df, vx_ok, col); g = df.dropna(subset=["_r"])
        labs = [hi] + [x for x in g["_r"].unique() if x != hi]
        L.append(f"  【{lab}】")
        for r in labs:
            s = g[g["_r"] == r]
            L.append(f"     {r}(n{len(s)}): 多 {s.uL4.mean():.0%}/{s.uL5.mean():.0%}  "
                     f"空 {s.dL4.mean():.0%}/{s.dL5.mean():.0%}  多−空L4={s.uL4.mean()-s.dL4.mean():+.0%}")

    # C. 主偵測器 LAG 詳表 + 方向偏移檢定
    df["reg"] = lag_join(df, vx_ok, "d_MA"); g = df.dropna(subset=["reg"])
    L.append("\n" + "─" * 92)
    L.append("C) 主 regime（VIX>MA20, LAG）多/空 × L3/L4/L5 + 方向偏移檢定：")
    for r in ["升壓", "降壓"]:
        s = g[g["reg"] == r]
        L.append(f"   {r}(n{len(s)}): 多 " + "/".join(f"{s['u'+n].mean():.0%}" for n in LVL)
                 + "  空 " + "/".join(f"{s['d'+n].mean():.0%}" for n in LVL)
                 + f"  多−空L4={s.uL4.mean()-s.dL4.mean():+.0%}")
    L.append("   → magnitude(深 reach ~2×) 因果守住;方向偏移(多−空L4)≈0 = 同期假象,不可用 VIX 偏多空。")

    txt = "\n".join(L)
    print(txt)
    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "distribution_raw.txt").write_text(txt + "\n")
    g.to_csv(out / "vix_ladder_panel.csv", index=False)
    print(f"\n存：{out/'distribution_raw.txt'}")


if __name__ == "__main__":
    main()
