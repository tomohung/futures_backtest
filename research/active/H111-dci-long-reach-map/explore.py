"""H111 Phase 1 — dci_long × 盤中關卡觸及 × 各時間點（多方關係地圖，strategy-agnostic）。

時間點 T={09:01,09:05,09:10,09:15,09:20,09:25,09:30}；universe={W-20,W-50,H-20}；
關卡 L1–L5（c=0.385/0.497/0.711/0.977/1.225 × EMA20，open-anchor 上行擺幅）+ 連續擺幅 up_full/EMA20。
dci_long(t,U) = U 內 value-weighted tanh((p@t−open)/range_i)。

分析（只多方）：
  A 核心地圖：各 t × L_k，P(forward 達 L_k | dci_long 五分位) + base rate（W-20）
  B 成熟曲線：固定 L4，強分位 forward 達成率 − base 隨 t
  C 套套邏輯：L4 全日 vs forward base rate 差（t 前既成擺幅成分）
  D 關卡深度：09:15 W-20，L1→L5 鑑別力(強分位−base)
  E universe 對照：09:15 W-20/W-50/H-20 的 corr(dci, 擺幅)、L4 強分位 lift；W-20 vs H-20 重疊
  F 連續擺幅：corr(dci_long, up_full/EMA20) by universe × t

限制：上市-only、181 日、偏多頭、無 OOS。全部附 N。
用法：uv run python research/active/H111-dci-long-reach-map/explore.py
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
IS_END = date(2026, 2, 26)                        # IS 末日；OOS = 2026-03-01 起（OOS 複驗用）
CKPTS = ["09:01:00", "09:05:00", "09:10:00", "09:15:00", "09:20:00", "09:25:00", "09:30:00"]
KEYS = [s[:5] for s in CKPTS]
LVL = {"L1": 0.385, "L2": 0.497, "L3": 0.711, "L4": 0.977, "L5": 1.225}
UNIS = ["W10", "W20", "W50", "H20"]   # W10 為 OOS 複驗後採用的 ext_long universe


def snap_prices(c):
    filt = ", ".join(
        f"arg_max(close, minute) FILTER (WHERE minute <= TIME '{s}') AS \"p_{s[:5]}\"" for s in CKPTS)
    return c.execute(
        f"SELECT trade_date, stock_id, {filt} FROM stock_min "
        f"WHERE trade_date BETWEEN ? AND ? AND minute <= TIME '{CKPTS[-1]}' "
        f"GROUP BY trade_date, stock_id", [LO, HI]).df()


def tx_swings(c):
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
        up = np.maximum.accumulate(hi - np.minimum.accumulate(lo))
        rec = {"d": pd.Timestamp(d).date(), "ema20": ema.get(d, np.nan), "up_full": up[-1]}
        for k in KEYS:
            i = max(np.searchsorted(t, cut[k], side="right") - 1, 0)
            rec[f"up_{k}"] = up[i]
        rows.append(rec)
    return pd.DataFrame(rows).set_index("d")


def build(c):
    feat = stock_features(c); px = snap_prices(c); tx = tx_swings(c)
    g = px.merge(feat, on=["trade_date", "stock_id"], how="inner")
    g = g[g["range_i"] > 0]
    rows = []
    for d, gd in g.groupby("trade_date"):
        dd = pd.Timestamp(d).date()
        if dd not in tx.index or not (tx.loc[dd, "ema20"] > 0):
            continue
        w = gd.dropna(subset=["trail_val"])
        w10 = w.nlargest(10, "trail_val"); w20 = w.nlargest(20, "trail_val"); w50 = w.nlargest(50, "trail_val")
        h20 = gd.dropna(subset=["prev_value"]).nlargest(20, "prev_value")
        rec = {"d": dd, "ema20": float(tx.loc[dd, "ema20"]), "up_full": float(tx.loc[dd, "up_full"])}
        for k in KEYS:
            rec[f"W10_{k}"] = wmean_tanh(w10, f"p_{k}", "trail_val")
            rec[f"W20_{k}"] = wmean_tanh(w20, f"p_{k}", "trail_val")
            rec[f"W50_{k}"] = wmean_tanh(w50, f"p_{k}", "trail_val")
            rec[f"H20_{k}"] = wmean_tanh(h20, f"p_{k}", "prev_value")
            rec[f"upsw_{k}"] = float(tx.loc[dd, f"up_{k}"])
        rows.append(rec)
    df = pd.DataFrame(rows).set_index("d")
    df["exc"] = df["up_full"] / df["ema20"]      # 連續擺幅比
    return df


def quintile(s):
    try:
        return pd.qcut(s, 5, labels=False, duplicates="drop")
    except ValueError:
        return pd.Series(np.full(len(s), -1), index=s.index)


def reach_fwd(df, k, name):
    """forward 達 L_name：up@k < c·ema <= up_full。回傳 0/1 Series。"""
    c_ = LVL[name]; lvl = c_ * df["ema20"]
    return ((df[f"upsw_{k}"] < lvl) & (df["up_full"] >= lvl)).astype(int)


def reach_full(df, name):
    return (df["up_full"] >= LVL[name] * df["ema20"]).astype(int)


def main():
    with duckdb.connect(DB, read_only=True) as c:
        df = build(c)
    N = len(df)
    L = ["=" * 92,
         f"H111 Phase 1 — dci_long × 關卡 × 時間點（多方地圖）  N={N}（{df.index.min()}~{df.index.max()}）",
         "上市-only、forward-guarded、附 N；universe: W20/W50(權值) H20(熱門)"]

    # base rates
    L.append("\n基準達成率（無條件）：")
    L.append("  " + "  ".join(f"{n}: full={reach_full(df, n).mean():.0%}/fwd={reach_fwd(df, KEYS[-1], n).mean():.0%}"
                              for n in LVL))

    # A 核心地圖（W-20）：各 t × L3/L4/L5 強分位 forward 達成率 − base
    L.append("\n" + "─" * 92)
    L.append("A) W-20 核心地圖：強分位(Q5) forward 達成率 − base rate（[強分位率→差]，Q5≈36/5 日）")
    for name in ("L3", "L4", "L5"):
        cells = []
        for k in KEYS:
            q = quintile(df[f"W20_{k}"])
            y = reach_fwd(df, k, name)
            base = y.mean()
            q5 = y[q == 4].mean() if (q == 4).sum() else np.nan
            cells.append(f"{q5:.0%}({q5 - base:+.0%})")
        L.append(f"  {name} | " + "  ".join(f"{k}:{c}" for k, c in zip(KEYS, cells)))
    L.append("  （格式 達成率(vs base)；base 見上行）")

    # B 成熟曲線 L4
    L.append("\n" + "─" * 92)
    L.append("B) 成熟曲線（W-20, L4）：Q5 forward 達成率 − base 隨 t；+ 五分位單調")
    for k in KEYS:
        q = quintile(df[f"W20_{k}"]); y = reach_fwd(df, k, "L4"); base = y.mean()
        rates = [y[q == i].mean() if (q == i).sum() else np.nan for i in range(5)]
        mono = "↗" if rates[4] >= rates[0] else "✗"
        L.append(f"  {k}: Q1-5=[" + " ".join(f"{r:.0%}" for r in rates) +
                 f"]  base={base:.0%}  Q5−base={rates[4]-base:+.0%} {mono}")

    # C 套套邏輯
    L.append("\n" + "─" * 92)
    L.append("C) 套套邏輯檢查（L4）：全日 vs forward 達成率（差=09:30 前既成擺幅成分）")
    for name in ("L3", "L4", "L5"):
        L.append(f"  {name}: 全日={reach_full(df, name).mean():.0%}  forward(09:30)={reach_fwd(df, KEYS[-1], name).mean():.0%}")

    # D 關卡深度 @09:15
    L.append("\n" + "─" * 92)
    L.append("D) 關卡深度（W-20 @09:15）：L1→L5 鑑別力(Q5 forward − base)")
    k = "09:15"
    for name in LVL:
        q = quintile(df[f"W20_{k}"]); y = reach_fwd(df, k, name); base = y.mean()
        q5 = y[q == 4].mean() if (q == 4).sum() else np.nan
        L.append(f"  {name}: base={base:.0%}  Q5={q5:.0%}  lift={q5-base:+.0%}")

    # E universe 對照 @09:15
    L.append("\n" + "─" * 92)
    L.append("E) universe 對照 @09:15：corr(dci, 擺幅比 exc)、L4 強分位 lift；W20 vs H20 重疊")
    for u in UNIS:
        col = df[f"{u}_09:15"]
        r = np.corrcoef(col, df["exc"])[0, 1]
        q = quintile(col); y = reach_fwd(df, "09:15", "L4"); base = y.mean()
        lift = (y[q == 4].mean() if (q == 4).sum() else np.nan) - base
        L.append(f"  {u:>4}: corr(dci,exc)={r:+.3f}  L4 Q5−base={lift:+.0%}")
    L.append(f"  重疊 corr(W20, H20)@09:15 = {np.corrcoef(df['W20_09:15'], df['H20_09:15'])[0,1]:+.3f}"
             "（高=H 對多方與 W 重複）")

    # F 連續擺幅 corr by t
    L.append("\n" + "─" * 92)
    L.append("F) 連續擺幅 corr(dci_long, up_full/EMA20) by universe × t：")
    L.append(f"{'t':>6} | " + "".join(f"{u:>9}" for u in UNIS))
    for k in KEYS:
        L.append(f"{k:>6} | " + "".join(f"{np.corrcoef(df[f'{u}_{k}'], df['exc'])[0,1]:>+9.3f}" for u in UNIS))

    nis = sum(1 for d in df.index if d <= IS_END); noos = N - nis
    L.append(f"\n  ⚠ 上市-only、全窗 N={N}（IS≤{IS_END}:{nis}日 / OOS≥2026-03:{noos}日）→ 描述性，附 N。OOS 複驗見 backtest.py。")
    txt = "\n".join(L)
    print(txt)
    out = HERE / "results"; out.mkdir(exist_ok=True)
    (out / "distribution_raw.txt").write_text(txt + "\n")
    df.to_csv(out / "reach_map_panel.csv")
    print(f"\n存：{out/'distribution_raw.txt'}")


if __name__ == "__main__":
    main()
