"""H117 Phase 2 — regime-conditioned 出場回測（事件型 bracket,全 TX 史）。

碰 L3 進場做多(p_L3),bracket：target 依規則、stop 共用 −0.266×EMA20、皆未到→收盤平。
損益% = 點數/p_L3×100。regime = 昨日 VIX vs MA20（因果 lag）。

規則（target offset，×EMA20;d_L4=0.266 d_L5=0.514）：
  regime: 升壓→d_L5(抱尾) / 降壓→d_L4(早收)
  fixed_L4: 一律 d_L4（保守固定）
  fixed_L5: 一律 d_L5（積極固定）
  satzone: target=SatZoneUpper（est_range 滿足價;若已 ≤p_L3=已滿足→exit p_L3,pnl 0）
對撞：regime vs fixed_L4/L5（VIX 調節有無增益）、regime vs satzone（VIX 是否冗餘於 vol_ratio）。

IS=2021-02~2024-12、OOS=2025-01~2026-06（皆含升/降壓）。附連敗/maxDD。
用法：uv run python research/active/H117-vix-regime-ladder/backtest.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from src.backtest.estimate_hl import compute_vol_estimated_range

DB = str(Path(__file__).resolve().parents[3] / "data" / "futures.duckdb")
L3, L4, L5 = 0.711, 0.977, 1.225
D_L4, D_L5 = L4 - L3, L5 - L3      # target offsets ×EMA20
STOP = D_L4                         # 共用停損 0.266×EMA20
IS_END = date(2024, 12, 31)


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
    # SatZone（est_range）：用完整 OHLCV
    sdf = con.execute(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv_1m WHERE symbol='TX' "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' ORDER BY timestamp").df()
    con.close()
    sdf["timestamp"] = pd.to_datetime(sdf["timestamp"]); sdf = sdf.set_index("timestamp")
    sdf.columns = ["Open", "High", "Low", "Close", "Volume"]
    sdf = compute_vol_estimated_range(sdf)
    sdf["d"] = sdf.index.date; sdf["t"] = sdf.index.time
    sat_by = {d: (list(g["t"]), g["EstRange_SatUpper"].ffill().values, g["Close"].values, g["High"].values, g["Low"].values)
              for d, g in sdf.groupby("d")}

    rows = []
    for d in sorted(sat_by.keys()):
        e = float(ema.get(pd.Timestamp(d), np.nan))
        if d < date(2021, 2, 1) or not (e > 0):
            continue
        ts, sat, cl, hi, lo = sat_by[d]
        up = np.maximum.accumulate(np.array(hi) - np.minimum.accumulate(np.array(lo)))
        i3 = np.argmax(up >= L3 * e) if (up >= L3 * e).any() else -1
        if i3 < 0:
            continue
        p3 = cl[i3]; sat3 = sat[i3] if i3 < len(sat) and np.isfinite(sat[i3]) else np.nan
        rec = {"d": pd.Timestamp(d), "e": e, "p3": p3, "i3": i3,
               "hi": hi, "lo": lo, "cl": cl, "sat3": sat3}
        rows.append(rec)
    df = pd.DataFrame(rows); df["d"] = df["d"].astype("datetime64[ns]")
    df["reg"] = pd.merge_asof(df.sort_values("d"), vx.sort_values("date")[["date", "reg"]],
                              left_on="d", right_on="date", direction="backward",
                              allow_exact_matches=False)["reg"].values
    return df.dropna(subset=["reg"]).reset_index(drop=True)


def walk(r, target_px):
    """從 i3+1 走,先到 stop/target,否則收盤。回傳點數（相對 p3）。"""
    p3, e, i3 = r["p3"], r["e"], r["i3"]
    stop_px = p3 - STOP * e
    if target_px <= p3:           # SatZone 已滿足 → 不持有
        return 0.0
    hi, lo, cl = r["hi"], r["lo"], r["cl"]
    for j in range(i3 + 1, len(cl)):
        if lo[j] <= stop_px:
            return stop_px - p3
        if hi[j] >= target_px:
            return target_px - p3
    return cl[-1] - p3


def pnl_rules(df):
    out = {}
    for nm in ["regime", "fixed_L4", "fixed_L5", "satzone"]:
        ps = []
        for _, r in df.iterrows():
            if nm == "regime":
                tgt = r["p3"] + (D_L5 if r["reg"] == "升壓" else D_L4) * r["e"]
            elif nm == "fixed_L4":
                tgt = r["p3"] + D_L4 * r["e"]
            elif nm == "fixed_L5":
                tgt = r["p3"] + D_L5 * r["e"]
            else:
                tgt = r["sat3"] if np.isfinite(r["sat3"]) else r["p3"] + D_L4 * r["e"]
            ps.append(walk(r, tgt) / r["p3"] * 100)
        out[nm] = np.array(ps)
    return out


def stats(p):
    n = len(p)
    if n == 0:
        return dict(N=0, sum=0, mean=0, win=np.nan, sharpe=np.nan, maxDD=0, streak=0)
    eq = np.cumsum(p); dd = (eq - np.maximum.accumulate(eq)).min()
    s = mx = 0
    for x in p:
        s = s + 1 if x < 0 else 0; mx = max(mx, s)
    return dict(N=n, sum=p.sum(), mean=p.mean(), win=(p > 0).mean(),
                sharpe=(p.mean() / p.std() if p.std() > 0 else np.nan), maxDD=dd, streak=mx)


def ln(lab, s):
    return (f"  {lab:<14} N={s['N']:>3} Σ%={s['sum']:>7.2f} 平均%={s['mean']:>6.3f} "
            f"勝率={s['win']:.0%} Sharpe={s['sharpe']:>5.2f} maxDD={s['maxDD']:>6.2f} 連敗={s['streak']}")


def main():
    df = build()
    df["seg"] = np.where(df["d"].dt.date <= IS_END, "IS", "OOS")
    L = ["=" * 96,
         f"H117 Phase 2 — regime-conditioned 出場 bracket（target 升壓=L5/降壓=L4,stop −{STOP:.3f}×EMA20）",
         f"L3 事件 N={len(df)}（IS {int((df.seg=='IS').sum())} / OOS {int((df.seg=='OOS').sum())}）;損益%=點數/p3×100"]
    for seg in ["IS", "OOS"]:
        g = df[df.seg == seg]
        r = pnl_rules(g)
        L.append("\n" + "─" * 96)
        L.append(f"【{seg}】L3 事件={len(g)}（升壓 {int((g.reg=='升壓').sum())} / 降壓 {int((g.reg=='降壓').sum())}）")
        for nm, lab in [("regime", "regime條件"), ("fixed_L4", "固定L4"), ("fixed_L5", "固定L5"), ("satzone", "SatZone")]:
            L.append(ln(lab, stats(r[nm])))
    # 增量控制：高波水位內 regime 是否仍有增益（Invalidation #3）
    L.append("\n" + "═" * 96)
    L.append("增量控制：僅高波水位日(ema20≥全史2/3分位)內,regime vs fixed_L5（VIX 是否只是 vol level 代理）")
    thr = df["e"].quantile(2 / 3); hv = df[df["e"] >= thr]
    r = pnl_rules(hv)
    L.append(f"  高波日 N={len(hv)}")
    L.append(ln("regime條件", stats(r["regime"])))
    L.append(ln("固定L5", stats(r["fixed_L5"])))

    L.append("\n  ⚠ 全 TX 史;無手續費滑價(純訊號);stop/target 未細掃。VIX regime 因果 lag。")
    txt = "\n".join(L)
    print(txt)
    out = Path(__file__).parent / "results"
    (out / "backtest_raw.txt").write_text(txt + "\n")
    print(f"\n存：{out/'backtest_raw.txt'}")


if __name__ == "__main__":
    main()
