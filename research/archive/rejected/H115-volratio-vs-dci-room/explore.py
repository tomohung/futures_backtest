"""H115 Phase 1 — vol_ratio vs dci_long vs 碰觸時點,對 P(L4|L3) 的分辨力對撞。

碰 L3 當下 t_k 取三 causal 調節器,比哪個分帶對「續攻 L4」分辨力最強且 OOS 最穩：
  vol_ratio  = EstRange(t_k)/EstRange_Daily(t_k)（量加權,5分延遲,生產 compute_vol_estimated_range）
  dci_long   = 盤中 W10 ext_long @t_k（主;W10 09:15 凍結為對照）
  tod        = 碰觸時點（H114 OOS 穩基準）
結果 cont = t_k 後是否續攻 L4（forward,取自 H114 panel）。

分帶 = IS 三分位(tertile)凍結 → 套 OOS;報每帶 P(L4|L3)、強−弱 gap、單調性,IS vs OOS。
增量：控制碰觸時點(IS中位早/晚)後 vol_ratio 是否仍分辨。對齊：vol_ratio↔關卡係數(1.0↔L4)。

重用 H114 results/ladder_live_ext_panel.csv（d/tk/cont/W10_level=ext@tk/W10_frozen/ema20/is_seg/lvl）。
用法：uv run python research/active/H115-volratio-vs-dci-room/explore.py
"""
from __future__ import annotations

import sys
from datetime import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2]))
from src.backtest.estimate_hl import compute_vol_estimated_range   # noqa: E402

DB = str(HERE.parents[2] / "data" / "futures.duckdb")
H114_PANEL = HERE.parents[0] / "H114-live-ext-at-ladder" / "results" / "ladder_live_ext_panel.csv"


def vol_ratio_at_cross(days_tk: dict) -> dict:
    """每個 (date→t_k) 取 vol_ratio = EstRange/EstRange_Daily（t_k 當下,ffill）。"""
    with duckdb.connect(DB, read_only=True) as c:
        df = c.execute(
            "SELECT timestamp, open, high, low, close, volume FROM ohlcv_1m WHERE symbol='TX' "
            "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' ORDER BY timestamp").df()
    df["timestamp"] = pd.to_datetime(df["timestamp"]); df = df.set_index("timestamp")
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    df = compute_vol_estimated_range(df)
    df["d"] = df.index.date; df["t"] = df.index.time
    out = {}
    for d, g in df.groupby("d"):
        if d not in days_tk:
            continue
        g = g.sort_index()
        er = g["EstRange"].ffill().values
        erd = g["EstRange_Daily"].ffill().values
        ts = list(g["t"])
        tk = days_tk[d]
        i = -1
        for j, tt in enumerate(ts):
            if tt <= tk:
                i = j
            else:
                break
        if i >= 0 and np.isfinite(er[i]) and np.isfinite(erd[i]) and erd[i] > 0:
            out[d] = er[i] / erd[i]
    return out


def bands_is(s, q=(1/3, 2/3)):
    return s.quantile(q[0]), s.quantile(q[1])


def report_pred(df, col, name, invert=False):
    """三分位分帶 P(cont)。invert=True 表小值=強(如時點:早碰=強)。回傳文字行。"""
    isd = df[df["is_seg"] == "IS"].dropna(subset=[col, "cont"])
    lo, hi = bands_is(isd[col])
    def band(v):
        if invert:
            return 0 if v >= hi else (2 if v <= lo else 1)   # 0=弱(大),2=強(小)
        return 2 if v >= hi else (0 if v <= lo else 1)        # 2=強(大)
    lines = [f"  【{name}】IS 三分位切點=({lo:.3f},{hi:.3f}){'  (小值=強)' if invert else ''}"]
    for seg in ("IS", "OOS"):
        g = df[df["is_seg"] == seg].dropna(subset=[col, "cont"]).copy()
        g["b"] = g[col].apply(band)
        rates = [g[g["b"] == k]["cont"].mean() if (g["b"] == k).sum() else np.nan for k in range(3)]
        ns = [int((g["b"] == k).sum()) for k in range(3)]
        gap = rates[2] - rates[0]
        mono = "↗" if (rates[0] <= rates[1] <= rates[2]) else "✗"
        lines.append(f"    {seg}: 弱={rates[0]:.0%}(n{ns[0]}) 中={rates[1]:.0%}(n{ns[1]}) 強={rates[2]:.0%}(n{ns[2]})"
                     f"  強−弱={gap:+.0%} {mono}")
    return lines, gap


def main():
    pan = pd.read_csv(H114_PANEL)
    pan["d"] = pd.to_datetime(pan["d"]).dt.date
    df = pan[pan["lvl"] == "L3"].copy()
    df["tk_t"] = pd.to_datetime(df["tk"], format="%H:%M:%S").dt.time
    df["tod"] = pd.to_datetime(df["tk"], format="%H:%M:%S").dt.hour * 60 + pd.to_datetime(df["tk"], format="%H:%M:%S").dt.minute
    days_tk = dict(zip(df["d"], df["tk_t"]))
    vr = vol_ratio_at_cross(days_tk)
    df["vol_ratio"] = df["d"].map(vr)
    df = df.dropna(subset=["cont"])

    L = ["=" * 92,
         f"H115 Phase 1 — vol_ratio vs dci_long vs 時點,對 P(L4|L3) 分辨力  L3 事件 N={len(df)}",
         f"  IS={int((df['is_seg']=='IS').sum())} / OOS={int((df['is_seg']=='OOS').sum())}；vol_ratio 取得={df['vol_ratio'].notna().sum()}"]
    L.append(f"  base P(L4|L3): IS={df[df['is_seg']=='IS']['cont'].mean():.0%} / OOS={df[df['is_seg']=='OOS']['cont'].mean():.0%}")

    L.append("\n" + "═" * 92)
    L.append("① 三調節器分帶 P(L4|L3)（IS 三分位凍結→套 OOS;強−弱 gap）")
    gaps = {}
    for col, nm, inv in [("vol_ratio", "vol_ratio 量比(放量=強)", False),
                         ("W10_level", "dci_long 盤中W10@t_k(主)", False),
                         ("W10_frozen", "dci_long W10@09:15(對照)", False),
                         ("tod", "碰觸時點(早碰=強)", True)]:
        lines, _ = report_pred(df, col, nm, invert=inv)
        L += ["\n"] + lines

    # ② 增量：控制時點後 vol_ratio
    L.append("\n" + "═" * 92)
    L.append("② 增量檢定：控制碰觸時點(IS中位 早/晚)後,vol_ratio 是否仍分辨")
    tmed = df[df["is_seg"] == "IS"]["tod"].median()
    L.append(f"   時點中位={int(tmed)}分({int(tmed//60)}:{int(tmed%60):02d})")
    for strat, slab in [(df["tod"] <= tmed, "早碰層"), (df["tod"] > tmed, "晚碰層")]:
        vmed = df[strat & (df["is_seg"] == "IS")]["vol_ratio"].median()
        for seg in ("IS", "OOS"):
            g = df[strat & (df["is_seg"] == seg)].dropna(subset=["vol_ratio"])
            if len(g) < 4:
                L.append(f"   {slab} {seg}: n={len(g)} 太少"); continue
            hi = g[g["vol_ratio"] >= vmed]["cont"]; lo = g[g["vol_ratio"] < vmed]["cont"]
            L.append(f"   {slab} {seg}: 放量={hi.mean():.0%}(n{len(hi)}) vs 縮量={lo.mean():.0%}(n{len(lo)})  gap={hi.mean()-lo.mean():+.0%}")

    # ③ vol_ratio ↔ 關卡係數對齊
    L.append("\n" + "═" * 92)
    L.append("③ vol_ratio↔滿足關卡對齊（理論 1.0↔L4=0.977;放量續攻↑?）")
    L.append(f"   全體 vol_ratio: 中位={df['vol_ratio'].median():.2f} 平均={df['vol_ratio'].mean():.2f} "
             f"[{df['vol_ratio'].quantile(.1):.2f},{df['vol_ratio'].quantile(.9):.2f}]")
    for lab, m in [("續攻 L4 (cont=1)", df["cont"] == 1), ("止於 L3 (cont=0)", df["cont"] == 0)]:
        L.append(f"   {lab}: vol_ratio 中位={df[m]['vol_ratio'].median():.2f} 平均={df[m]['vol_ratio'].mean():.2f}")
    for a, b, lab in [(0, 0.85, "縮量<0.85"), (0.85, 1.15, "中 0.85-1.15"), (1.15, 9, "放量>1.15")]:
        for seg in ("IS", "OOS"):
            g = df[(df["is_seg"] == seg) & (df["vol_ratio"] >= a) & (df["vol_ratio"] < b)]
            if len(g):
                L.append(f"   [{seg}] {lab}: P(L4|L3)={g['cont'].mean():.0%}(n{len(g)})")

    L.append("\n  ⚠ 上市-only(dci)、單一窗;切點 IS 定 OOS 驗;L4→L5 未列(薄)。GATE 看 vol_ratio OOS gap 是否 > DCI 且增量存活。")
    txt = "\n".join(L)
    print(txt)
    out = HERE / "results"; out.mkdir(exist_ok=True)
    (out / "distribution_raw.txt").write_text(txt + "\n")
    df.to_csv(out / "h115_panel.csv", index=False)
    print(f"\n存：{out/'distribution_raw.txt'}")


if __name__ == "__main__":
    main()
