"""H112 Phase 1 — dci_short × 下行關卡 × 各時間點（空方關係地圖，strategy-agnostic）。

成分（皆「空方力道」，正=預測下行）：
  s_thr(t) = −thrust(W-100)   寬權值帶幅度的廣度（value-weighted tanh）
  s_B(t)   = −(up−dn)/active  全 TWSE 上市 09:xx running 家數
  dci_short(t) = z(s_thr) + z(s_B)  等權（181 日分佈標準化）
目標：TX open-anchor **下行**關卡 L1–L5（dn_full vs c×EMA20）+ 連續 dn_full/EMA20。forward-guarded。

沿用 H111 框架。限制：上市-only、181 日、輕微多頭偏（下行深關卡稀）→ 更指示性、更需 OOS。
用法：uv run python research/active/H112-dci-short-reach-map/explore.py
"""
from __future__ import annotations

import os
import sys
from datetime import date, time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
H095 = HERE.parents[0] / "H095-reach-ladder-exit"
sys.path.insert(0, str(H095))
from dci_universe_sweep import stock_features, wmean_tanh   # noqa: E402

DB = os.environ.get("STOCK_MIN_DB", str(HERE.parents[2] / "data" / "futures.duckdb"))
LO, HI = date(2025, 6, 1), date(2026, 6, 30)     # 全資料窗（含 OOS）
IS_END = date(2026, 2, 26)                        # OOS = 2026-03-01 起（空方複驗重點：OOS 下殺日）
CKPTS = ["09:01:00", "09:05:00", "09:10:00", "09:15:00", "09:20:00", "09:25:00", "09:30:00"]
KEYS = [s[:5] for s in CKPTS]
LVL = {"L1": 0.385, "L2": 0.497, "L3": 0.711, "L4": 0.977, "L5": 1.225}


def snap_prices(c):
    filt = ", ".join(
        f"arg_max(close, minute) FILTER (WHERE minute <= TIME '{s}') AS \"p_{s[:5]}\"" for s in CKPTS)
    return c.execute(
        f"SELECT trade_date, stock_id, {filt} FROM stock_min "
        f"WHERE trade_date BETWEEN ? AND ? AND minute <= TIME '{CKPTS[-1]}' "
        f"GROUP BY trade_date, stock_id", [LO, HI]).df()


def tx_down(c):
    bars = c.execute(
        "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, high, low FROM ohlcv_1m "
        "WHERE symbol='TX' AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "AND CAST(timestamp AS DATE) BETWEEN ? AND ? ORDER BY d,t", [LO, HI]).df()
    rng = c.execute(
        "SELECT CAST(timestamp AS DATE) d, MAX(high)-MIN(low) r FROM ohlcv_1m WHERE symbol='TX' "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' GROUP BY 1 ORDER BY 1").df()
    rng["ema20"] = rng["r"].astype(float).shift(1).ewm(span=20, adjust=False).mean()
    ema = rng.set_index("d")["ema20"]
    bars["high"] = bars["high"].astype(float); bars["low"] = bars["low"].astype(float)
    cut = {s[:5]: time.fromisoformat(s) for s in CKPTS}
    rows = []
    for d, g in bars.groupby("d"):
        g = g.sort_values("t"); hi, lo, t = g["high"].values, g["low"].values, list(g["t"].values)
        dn = np.maximum.accumulate(np.maximum.accumulate(hi) - lo)   # 下行擺幅
        rec = {"d": pd.Timestamp(d).date(), "ema20": ema.get(d, np.nan), "dn_full": dn[-1]}
        for k in KEYS:
            i = max(np.searchsorted(t, cut[k], side="right") - 1, 0)
            rec[f"dn_{k}"] = dn[i]
        rows.append(rec)
    return pd.DataFrame(rows).set_index("d")


def build(c):
    feat = stock_features(c); px = snap_prices(c); tx = tx_down(c)
    g = px.merge(feat, on=["trade_date", "stock_id"], how="inner")
    rows = []
    for d, gd in g.groupby("trade_date"):
        dd = pd.Timestamp(d).date()
        if dd not in tx.index or not (tx.loc[dd, "ema20"] > 0):
            continue
        w100 = gd[gd["range_i"] > 0].dropna(subset=["trail_val"]).nlargest(100, "trail_val")
        rec = {"d": dd, "ema20": float(tx.loc[dd, "ema20"]), "dn_full": float(tx.loc[dd, "dn_full"])}
        for k in KEYS:
            rec[f"s_thr_{k}"] = -wmean_tanh(w100, f"p_{k}", "trail_val")     # 空方力道
            p = gd[f"p_{k}"]; valid = p.notna() & gd["prev"].notna()
            up = int((p[valid] > gd["prev"][valid]).sum()); dn = int((p[valid] < gd["prev"][valid]).sum())
            active = int(valid.sum())
            rec[f"s_B_{k}"] = -((up - dn) / active) if active else 0.0       # 空方力道
            rec[f"dn_{k}"] = float(tx.loc[dd, f"dn_{k}"])
        rows.append(rec)
    df = pd.DataFrame(rows).set_index("d")
    # 合成 = z(s_thr)+z(s_B) 逐檢查點
    for k in KEYS:
        zt = (df[f"s_thr_{k}"] - df[f"s_thr_{k}"].mean()) / df[f"s_thr_{k}"].std()
        zb = (df[f"s_B_{k}"] - df[f"s_B_{k}"].mean()) / df[f"s_B_{k}"].std()
        df[f"comp_{k}"] = zt + zb
    df["dn_exc"] = df["dn_full"] / df["ema20"]
    return df


def quintile(s):
    try:
        return pd.qcut(s, 5, labels=False, duplicates="drop")
    except ValueError:
        return pd.Series(np.full(len(s), -1), index=s.index)


def reach_fwd(df, k, name):
    lvl = LVL[name] * df["ema20"]
    return ((df[f"dn_{k}"] < lvl) & (df["dn_full"] >= lvl)).astype(int)


def reach_full(df, name):
    return (df["dn_full"] >= LVL[name] * df["ema20"]).astype(int)


def main():
    with duckdb.connect(DB, read_only=True) as c:
        df = build(c)
    N = len(df)
    L = ["=" * 92,
         f"H112 Phase 1 — dci_short × 下行關卡 × 時間點  N={N}（{df.index.min()}~{df.index.max()}）",
         "空方力道：s_thr=−thrust(W100)、s_B=−家數、comp=z+z；上市-only、forward-guarded"]
    L.append("\n下行基準達成率：" + "  ".join(
        f"{n}: full={reach_full(df, n).mean():.0%}/fwd={reach_fwd(df, KEYS[-1], n).mean():.0%}(N達={int(reach_full(df, n).sum())})"
        for n in LVL))

    # A 核心地圖（合成）：t × L3/L4/L5 強分位 forward − base
    L.append("\n" + "─" * 92)
    L.append("A) 合成 dci_short 核心地圖：強分位(Q5) forward 達成率(差 base)")
    for name in ("L3", "L4", "L5"):
        cells = []
        for k in KEYS:
            q = quintile(df[f"comp_{k}"]); y = reach_fwd(df, k, name); base = y.mean()
            q5 = y[q == 4].mean() if (q == 4).sum() else np.nan
            cells.append(f"{q5:.0%}({q5-base:+.0%})")
        L.append(f"  {name} | " + "  ".join(f"{k}:{c}" for k, c in zip(KEYS, cells)))

    # B 成分對照 @09:30（誰主導、互補）
    L.append("\n" + "─" * 92)
    L.append("B) 成分對照 @09:30：corr(力道, dn_exc)、L4 強分位 forward lift")
    for comp, lab in (("s_thr_09:30", "寬權值幅度"), ("s_B_09:30", "家數"), ("comp_09:30", "合成")):
        col = df[comp]; r = np.corrcoef(col, df["dn_exc"])[0, 1]
        q = quintile(col); y = reach_fwd(df, "09:30", "L4"); base = y.mean()
        lift = (y[q == 4].mean() if (q == 4).sum() else np.nan) - base
        L.append(f"  {lab:<8}({comp[:-6]}): corr={r:+.3f}  L4 Q5−base={lift:+.0%}")
    L.append(f"  互補性 corr(s_thr, s_B)@09:30 = {np.corrcoef(df['s_thr_09:30'], df['s_B_09:30'])[0,1]:+.3f}")

    # C 成熟曲線 L4（合成）
    L.append("\n" + "─" * 92)
    L.append("C) 成熟曲線（合成, L4）：Q5 forward−base 隨 t（驗 t*≈09:30 較多方晚）")
    for k in KEYS:
        q = quintile(df[f"comp_{k}"]); y = reach_fwd(df, k, "L4"); base = y.mean()
        rates = [y[q == i].mean() if (q == i).sum() else np.nan for i in range(5)]
        L.append(f"  {k}: Q1-5=[" + " ".join(f"{r:.0%}" for r in rates) +
                 f"]  base={base:.0%}  Q5−base={rates[4]-base:+.0%}")

    # D 套套邏輯 + 關卡深度 @09:30
    L.append("\n" + "─" * 92)
    L.append("D) 套套邏輯 + 關卡深度（合成 @09:30）：")
    k = "09:30"
    for name in LVL:
        full = reach_full(df, name).mean(); fwd = reach_fwd(df, k, name)
        q = quintile(df[f"comp_{k}"]); base = fwd.mean()
        q5 = fwd[q == 4].mean() if (q == 4).sum() else np.nan
        L.append(f"  {name}: 全日={full:.0%} fwd={base:.0%}(N達fwd={int(fwd.sum())})  Q5={q5:.0%} lift={q5-base:+.0%}")

    # E) OOS 複驗：IS vs OOS 的下殺日量 + 段內離散下行關卡地圖是否乾淨
    L.append("\n" + "═" * 92)
    L.append("E) OOS 複驗（IS≤2026-02-26 vs OOS≥2026-03）：下殺日量 + 段內 comp Q5 forward lift")
    is_mask = np.array([d <= IS_END for d in df.index])
    for seg_lab, seg in (("IS", is_mask), ("OOS", ~is_mask), ("全窗", np.ones(len(df), bool))):
        g = df[seg]
        n = len(g)
        # 下行 forward L4 達成日量（核心稀缺資源）
        cnt = {nm: int(reach_fwd(g, "09:30", nm).sum()) for nm in ("L3", "L4", "L5")}
        L.append(f"\n  [{seg_lab}] N={n}　forward 達成日量 @09:30: "
                 + " ".join(f"{nm}={cnt[nm]}" for nm in ("L3", "L4", "L5")))
        # 段內 quintile（rank-based，不受 z 尺度影響）→ L4 Q5 lift + 單調
        col = g["comp_09:30"]; q = quintile(col); y = reach_fwd(g, "09:30", "L4"); base = y.mean()
        rates = [y[q == i].mean() if (q == i).sum() else np.nan for i in range(5)]
        q5 = rates[4]
        mono = "↗單調" if all(rates[i] <= rates[i+1] for i in range(4) if not (np.isnan(rates[i]) or np.isnan(rates[i+1]))) else "✗非單調"
        L.append(f"     L4: base={base:.0%}  Q1-5=[" + " ".join(f"{r:.0%}" for r in rates)
                 + f"]  Q5−base={q5-base:+.0%}  {mono}")
        # 連續 corr（段內）
        r = np.corrcoef(g["comp_09:30"], g["dn_exc"])[0, 1]
        L.append(f"     連續 corr(comp, dn_exc)@09:30 = {r:+.3f}")

    L.append("\n  ⚠ 上市-only、全窗 250 日、偏多頭。空方複驗重點：OOS 是否多下殺日 → 離散地圖能否轉乾淨。附 N。")
    txt = "\n".join(L)
    print(txt)
    out = HERE / "results"; out.mkdir(exist_ok=True)
    (out / "distribution_raw.txt").write_text(txt + "\n")
    df.to_csv(out / "short_reach_panel.csv")
    print(f"\n存：{out/'distribution_raw.txt'}")


if __name__ == "__main__":
    main()
