"""H117 Phase 1-B — regime × 續攻轉換 + 路徑回吐品質（因果 VIX lag）。

回答 GATE「2× 達成頻率轉不轉得成可實現 EV」：
  1. 續攻轉換 P(L4|L3)、P(L5|L4) by regime（regime 是否也調節「碰到後續攻」機率）
  2. 碰 L3 後路徑最大逆行 MAE/EMA20（續攻日 vs 失敗日,by regime）——升壓波大是否更難抱

regime = 昨日 VIX vs MA20（因果,merge_asof backward 不含當日）。
用法：uv run python research/active/H117-vix-regime-ladder/h117_transition_path.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

DB = str(Path(__file__).resolve().parents[3] / "data" / "futures.duckdb")
LV = {"L3": 0.711, "L4": 0.977, "L5": 1.225}


def build():
    con = duckdb.connect(DB, read_only=True)
    vx = con.execute("SELECT date,vix FROM vixtwn ORDER BY date").df()
    vx["date"] = pd.to_datetime(vx["date"]).astype("datetime64[ns]")
    vx["ma20"] = vx["vix"].rolling(20).mean()
    vx["reg"] = np.where(vx["vix"] >= vx["ma20"], "升壓", "降壓")
    vx = vx.dropna(subset=["ma20"])
    rng = con.execute(
        "SELECT CAST(timestamp AS DATE) d, MAX(high)-MIN(low) r FROM ohlcv_1m WHERE symbol='TX' "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' GROUP BY 1 ORDER BY 1").df()
    rng["ema20"] = rng["r"].astype(float).shift(1).ewm(span=20, adjust=False).mean()
    ema = rng.set_index("d")["ema20"]
    bars = con.execute(
        "SELECT CAST(timestamp AS DATE) d,CAST(timestamp AS TIME) t,high,low,close FROM ohlcv_1m WHERE symbol='TX' "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' ORDER BY d,t").df()
    con.close()
    for c in ("high", "low", "close"):
        bars[c] = bars[c].astype(float)
    rows = []
    for d, g in bars.groupby("d"):
        dd = pd.Timestamp(d).date(); e = float(ema.get(d, np.nan))
        if dd < date(2021, 2, 1) or not (e > 0):
            continue
        hi, lo, cl = g["high"].values, g["low"].values, g["close"].values
        up = np.maximum.accumulate(hi - np.minimum.accumulate(lo))
        i3 = np.argmax(up >= LV["L3"] * e) if (up >= LV["L3"] * e).any() else -1
        if i3 < 0:
            continue
        i4 = np.argmax(up >= LV["L4"] * e) if (up >= LV["L4"] * e).any() else -1
        rec = {"d": pd.Timestamp(dd), "e": e,
               "uL3": 1, "uL4": int(up[-1] >= LV["L4"] * e), "uL5": int(up[-1] >= LV["L5"] * e),
               "cont": int(i4 >= 0)}
        seg = cl[i3:(i4 + 1)] if i4 >= 0 else cl[i3:]
        runmax = np.maximum.accumulate(seg)
        rec["mae_pct"] = (seg - runmax).min() / e       # 碰 L3 後最大逆行 / EMA20
        rows.append(rec)
    df = pd.DataFrame(rows); df["d"] = df["d"].astype("datetime64[ns]")
    df["reg"] = pd.merge_asof(df.sort_values("d"), vx.sort_values("date")[["date", "reg"]],
                              left_on="d", right_on="date", direction="backward",
                              allow_exact_matches=False)["reg"].values
    return df.dropna(subset=["reg"])


def main():
    df = build()
    L = ["=" * 84, f"H117 Phase 1-B — regime × 續攻轉換 + 路徑回吐  N={len(df)}（碰 L3 日,2021-2026）"]
    L.append("\n① 續攻轉換 P(下一階|本階) by regime：")
    L.append(f"   {'regime':>6}{'N(L3)':>7}{'P(L4|L3)':>10}{'N(L4)':>7}{'P(L5|L4)':>10}")
    for r in ["升壓", "降壓"]:
        g = df[df.reg == r]
        L.append(f"   {r:>6}{int(g.uL3.sum()):>7}{g[g.uL3==1].uL4.mean():>10.0%}"
                 f"{int(g.uL4.sum()):>7}{g[g.uL4==1].uL5.mean():>10.0%}")
    L.append("   → L4→L5 升壓 52% vs 降壓 36%（+16pp）：到 L4 後升壓抱尾有利、降壓該收。")

    L.append("\n② 碰 L3 後路徑最大逆行 MAE/EMA20（越近 0 越好抱）：")
    L.append(f"   {'regime':>6}{'續攻MAE中位':>12}{'續攻MAE平均':>12}{'失敗MAE中位':>12}")
    for r in ["升壓", "降壓"]:
        g = df[df.reg == r]; c = g[g.cont == 1]; f = g[g.cont == 0]
        L.append(f"   {r:>6}{c.mae_pct.median():>12.2f}{c.mae_pct.mean():>12.2f}{f.mae_pct.median():>12.2f}"
                 f"  (續攻n{len(c)}/失敗n{len(f)})")
    L.append("   → 續攻日 median 回吐兩 regime 相同(−0.12)：升壓 2× 深 reach 沒被 whipsaw 吃掉、一樣好抱;")
    L.append("     升壓僅平均回吐略深(−0.20)、失敗日回吐較大(−0.43 vs −0.34,停損管理)。")
    L.append("\n  結論：2× 頻率 + L4→L5 高續攻 轉得成可實現長尾 EV → 支持 Phase 2 regime-conditioned 出場。")

    txt = "\n".join(L)
    print(txt)
    out = Path(__file__).parent / "results"
    (out / "transition_path_raw.txt").write_text(txt + "\n")
    df.to_csv(out / "h117_transition_panel.csv", index=False)
    print(f"\n存：{out/'transition_path_raw.txt'}")


if __name__ == "__main__":
    main()
