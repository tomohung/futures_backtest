"""H115 衍生 — 多空力道量（bull_bear_force_volume）取代無方向 vol_ratio。

源自使用者既有指標 indicators/tradingview/bull_bear_force_volume.pine：
  bullVol = vol if close>open;  bearVol = vol if close<open;  淨力 = Σ(bull−bear)
本腳本在碰 L3 的 t_k 取「淨多空力道比例」(界 −1~1,抗 regime)：
  cum_frac  = Σ(bull−bear) / Σ(bull+bear)  自開盤累積（pine 累積版,當日歸零）
  roll_frac = 近20根(bull−bear) / 近20根(bull+bear)  滾動版（碰 L3 當下的即時方向）
比原始 vol_ratio：方向性（買/賣壓）+ 比例化（抗 regime）。

判準同 H115：分帶 P(L4|L3) IS/OOS gap + 單調、IS 內高低波分割、控時點增量。
用法：uv run python research/active/H115-volratio-vs-dci-room/h115_force.py
"""
from __future__ import annotations

from datetime import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DB = str(HERE.parents[2] / "data" / "futures.duckdb")
PANEL = HERE / "results" / "h115_panel.csv"
ROLL = 20


def force_at_cross(days_tk):
    with duckdb.connect(DB, read_only=True) as c:
        bars = c.execute(
            "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, open, close, volume FROM ohlcv_1m "
            "WHERE symbol='TX' AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
            "ORDER BY d,t").df()
    for col in ("open", "close", "volume"):
        bars[col] = bars[col].astype(float)
    out = {}
    for d, g in bars.groupby("d"):
        d = pd.Timestamp(d).date()
        if d not in days_tk:
            continue
        g = g.sort_values("t")
        bull = np.where(g["close"].values > g["open"].values, g["volume"].values, 0.0)
        bear = np.where(g["close"].values < g["open"].values, g["volume"].values, 0.0)
        net = bull - bear; tot = bull + bear
        cum_net = np.cumsum(net); cum_tot = np.cumsum(tot)
        cum_frac = np.divide(cum_net, cum_tot, out=np.zeros_like(cum_net), where=cum_tot > 0)
        s = pd.Series(net); st = pd.Series(tot)
        roll_net = s.rolling(ROLL, min_periods=3).sum().values
        roll_tot = st.rolling(ROLL, min_periods=3).sum().values
        roll_frac = np.divide(roll_net, roll_tot, out=np.zeros_like(roll_net), where=roll_tot > 0)
        ts = list(g["t"]); tk = days_tk[d]
        i = -1
        for j, tt in enumerate(ts):
            if tt <= tk:
                i = j
            else:
                break
        if i >= 0:
            out[d] = (cum_frac[i], roll_frac[i])
    return out


def banded(df, col, name, seg_col="is_seg"):
    isd = df[df[seg_col] == "IS"].dropna(subset=[col, "cont"])
    lo, hi = isd[col].quantile(1/3), isd[col].quantile(2/3)
    def band(v):
        return 2 if v >= hi else (0 if v <= lo else 1)
    lines = [f"  【{name}】IS 三分位切點=({lo:+.3f},{hi:+.3f})"]
    for seg in ("IS", "OOS"):
        g = df[df[seg_col] == seg].dropna(subset=[col, "cont"]).copy()
        g["b"] = g[col].apply(band)
        r = [g[g["b"] == k]["cont"].mean() if (g["b"] == k).sum() else np.nan for k in range(3)]
        n = [int((g["b"] == k).sum()) for k in range(3)]
        mono = "↗" if (r[0] <= r[1] <= r[2]) else "✗"
        lines.append(f"    {seg}: 賣壓={r[0]:.0%}(n{n[0]}) 中={r[1]:.0%}(n{n[1]}) 買壓={r[2]:.0%}(n{n[2]})  買−賣={r[2]-r[0]:+.0%} {mono}")
    return lines


def main():
    df = pd.read_csv(PANEL).dropna(subset=["cont"])
    df["tk_t"] = pd.to_datetime(df["tk"], format="%H:%M:%S").dt.time
    days_tk = dict(zip(pd.to_datetime(df["d"]).dt.date, df["tk_t"]))
    fr = force_at_cross(days_tk)
    dd = pd.to_datetime(df["d"]).dt.date
    df["cum_frac"] = [fr.get(x, (np.nan, np.nan))[0] for x in dd]
    df["roll_frac"] = [fr.get(x, (np.nan, np.nan))[1] for x in dd]

    L = ["=" * 92,
         f"H115 多空力道量 vs vol_ratio  L3 事件 N={len(df)}（IS {int((df['is_seg']=='IS').sum())} / OOS {int((df['is_seg']=='OOS').sum())}）",
         f"  base P(L4|L3): IS={df[df['is_seg']=='IS']['cont'].mean():.0%} / OOS={df[df['is_seg']=='OOS']['cont'].mean():.0%}"]

    L.append("\n① 分帶 P(L4|L3)（買壓強=淨多空力道高）")
    for col, nm in [("cum_frac", "累積淨力比例(當日)"), ("roll_frac", "滾動淨力比例(近20根@t_k)"),
                    ("vol_ratio", "原始 vol_ratio(對照)")]:
        L += ["\n"] + banded(df, col, nm)

    # ② IS 內高低波分割（看方向是否 regime-stable,vs vol_ratio 的翻轉）
    emed = df["ema20"].median()
    L.append("\n" + "═" * 92)
    L.append(f"② IS 內高低波分割（ema20 中位={emed:.0f}）：淨力比例方向是否 regime-stable")
    for col, nm in [("cum_frac", "累積淨力"), ("roll_frac", "滾動淨力")]:
        L.append(f"  {nm}：")
        for rlab, rm in [("低波", df["ema20"] < emed), ("高波", df["ema20"] >= emed)]:
            for seg in ("IS", "OOS"):
                g = df[rm & (df["is_seg"] == seg)].dropna(subset=[col])
                if len(g) < 6:
                    L.append(f"    {rlab} {seg}: n={len(g)} 太少"); continue
                m = g[col].median()
                hi = g[g[col] >= m]["cont"]; lo = g[g[col] < m]["cont"]
                L.append(f"    {rlab} {seg}: 買壓={hi.mean():.0%}(n{len(hi)}) vs 賣壓={lo.mean():.0%}(n{len(lo)})  gap={hi.mean()-lo.mean():+.0%}")

    # ③ 控時點增量
    tmed = df[df["is_seg"] == "IS"]["tod"].median()
    L.append("\n" + "═" * 92)
    L.append(f"③ 控時點增量（IS中位時點={int(tmed)}分）：滾動淨力在早/晚碰層內的 gap")
    for strat, slab in [(df["tod"] <= tmed, "早碰層"), (df["tod"] > tmed, "晚碰層")]:
        m = df[strat & (df["is_seg"] == "IS")]["roll_frac"].median()
        for seg in ("IS", "OOS"):
            g = df[strat & (df["is_seg"] == seg)].dropna(subset=["roll_frac"])
            if len(g) < 4:
                L.append(f"   {slab} {seg}: n={len(g)} 太少"); continue
            hi = g[g["roll_frac"] >= m]["cont"]; lo = g[g["roll_frac"] < m]["cont"]
            L.append(f"   {slab} {seg}: 買壓={hi.mean():.0%}(n{len(hi)}) vs 賣壓={lo.mean():.0%}(n{len(lo)})  gap={hi.mean()-lo.mean():+.0%}")

    L.append("\n  ⚠ 同 H115 限制;淨力比例界 −1~1 抗 regime。GATE 看是否 IS 高低波同向 + 控時點有增量 + OOS 不翻。")
    txt = "\n".join(L)
    print(txt)
    (HERE / "results" / "force_raw.txt").write_text(txt + "\n")
    print(f"\n存：{HERE/'results'/'force_raw.txt'}")


if __name__ == "__main__":
    main()
