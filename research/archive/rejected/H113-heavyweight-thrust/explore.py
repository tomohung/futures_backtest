"""H113 Phase 1 — 重權值推力 HT vs 廣度 ext_long，含套套邏輯防護。

HT = 前 N 大權值的 (p@t−open)/range_i，近似 TAIEX 權重加權、linear（不 tanh）。
對打 ext_long(W50 tanh，取自 H111 panel)；目標 forward 上行 L4。
★防護：控制「TX 自身 09:30 上行擺幅」(upsw_09:30/ema，取自 H111 panel)，看 HT 的 forward 預測力是否還在。

限制：上市-only、181 日、偏多頭、無 OOS。近似權重 hardcode（無真實市值欄）。
用法：uv run python research/active/H113-heavyweight-thrust/explore.py
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
H095 = HERE.parents[0] / "H095-reach-ladder-exit"
sys.path.insert(0, str(H095))
from dci_universe_sweep import stock_features, wmean_tanh   # noqa: E402

DB = os.environ.get("STOCK_MIN_DB", str(HERE.parents[2] / "data" / "futures.duckdb"))
LO, HI = date(2025, 6, 1), date(2026, 2, 28)
CKPTS = ["09:15:00", "09:30:00"]
KEYS = [s[:5] for s in CKPTS]
LVL_L4 = 0.977
# 近似 TAIEX 權重（%，2025 概估；無真實市值欄）
WEIGHTS = {"2330": 31, "2317": 5, "2454": 4, "2308": 3, "2382": 3, "3008": 1,
           "2891": 1.5, "2881": 1.5, "2882": 1.5, "2412": 1.3, "2303": 1.3,
           "3711": 1, "2886": 1, "1216": 1, "2884": 1, "2885": 0.8, "2357": 0.8,
           "2892": 0.8, "2880": 0.7, "2002": 0.6, "2207": 0.7}
WSYMS = sorted(WEIGHTS, key=lambda s: -WEIGHTS[s])


def snap(c):
    filt = ", ".join(f"arg_max(close, minute) FILTER (WHERE minute <= TIME '{s}') AS \"p_{s[:5]}\"" for s in CKPTS)
    return c.execute(f"SELECT trade_date, stock_id, {filt} FROM stock_min "
                     f"WHERE trade_date BETWEEN ? AND ? AND minute <= TIME '{CKPTS[-1]}' "
                     f"GROUP BY trade_date, stock_id", [LO, HI]).df()


def ht(sub, pcol, syms, weights, *, tanh=False):
    """HT = Σ w·m / Σ w over syms；m linear 或 tanh。"""
    num = den = 0.0
    for s in syms:
        if s not in sub.index:
            continue
        r = sub.loc[s]
        if not (r["range_i"] > 0) or pd.isna(r[pcol]):
            continue
        x = (r[pcol] - r["open"]) / r["range_i"]
        m = np.tanh(x) if tanh else x
        w = weights[s]
        num += m * w; den += w
    return num / den if den else 0.0


def build(c):
    feat = stock_features(c); px = snap(c)
    g = px.merge(feat, on=["trade_date", "stock_id"], how="inner").set_index("stock_id")
    rows = []
    for d, gd in g.groupby("trade_date"):
        rec = {"d": pd.Timestamp(d).date()}
        for k in KEYS:
            for N in (5, 10, 15):
                syms = WSYMS[:N]
                rec[f"HT{N}lin_{k}"] = ht(gd, f"p_{k}", syms, WEIGHTS, tanh=False)
            rec[f"HT10tanh_{k}"] = ht(gd, f"p_{k}", WSYMS[:10], WEIGHTS, tanh=True)
            rec[f"HT10eq_{k}"] = ht(gd, f"p_{k}", WSYMS[:10], {s: 1 for s in WSYMS}, tanh=False)
        rows.append(rec)
    return pd.DataFrame(rows).set_index("d")


def pb(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    return np.nan if x.std() == 0 or y.std() == 0 else float(np.corrcoef(x, y)[0, 1])


def resid(y, z):
    X = np.column_stack([np.ones(len(y)), np.asarray(z, float)])
    b, *_ = np.linalg.lstsq(X, np.asarray(y, float), rcond=None)
    return np.asarray(y, float) - X @ b


def pcorr(a, b, z):
    return float(np.corrcoef(resid(a, z), resid(b, z))[0, 1])


def quint_lift(x, y):
    d = pd.DataFrame({"x": x, "y": y})
    d["q"] = pd.qcut(d["x"], 5, labels=False, duplicates="drop")
    base = d["y"].mean()
    q5 = d[d["q"] == 4]["y"].mean()
    return q5, q5 - base


def main():
    with duckdb.connect(DB, read_only=True) as c:
        df = build(c)
    pl = pd.read_csv(HERE.parents[0] / "H111-dci-long-reach-map" / "results" / "reach_map_panel.csv")
    pl["d"] = pd.to_datetime(pl.iloc[:, 0]).dt.date
    pl = pl.set_index("d")
    df = df.join(pl[["ema20", "up_full", "upsw_09:30", "W50_09:30"]], how="inner")
    ema = df["ema20"]
    fwdL4 = ((df["upsw_09:30"] < LVL_L4 * ema) & (df["up_full"] >= LVL_L4 * ema)).astype(int)
    tx_own = df["upsw_09:30"] / ema       # TX 自身 09:30 上行擺幅（控制變數）
    extlong = df["W50_09:30"]
    N = len(df); base = fwdL4.mean()

    L = ["=" * 86,
         f"H113 Phase 1 — 重權值推力 HT vs ext_long  N={N}  目標 forward L4(base={base:.0%})",
         "近似 TAIEX 權重、linear；上市-only、181 日、偏多頭"]

    # ① 對打：corr / 五分位 lift
    L.append("\n" + "─" * 86)
    L.append("① 對 forward-L4 鑑別力（@09:30）：r(point-biserial) + 五分位 Q5 lift")
    cands = [("ext_long(W50 tanh)", extlong), ("HT5 lin", df["HT5lin_09:30"]),
             ("HT10 lin", df["HT10lin_09:30"]), ("HT15 lin", df["HT15lin_09:30"]),
             ("HT10 tanh", df["HT10tanh_09:30"]), ("HT10 等權", df["HT10eq_09:30"]),
             ("TX自身09:30擺幅", tx_own)]
    for nm, col in cands:
        q5, lift = quint_lift(col, fwdL4)
        L.append(f"  {nm:<18} r={pb(col, fwdL4):+.3f}  Q5達標={q5:.0%}  lift={lift:+.0%}")

    # ② subsume：HT10lin vs ext_long 互相控制
    L.append("\n" + "─" * 86)
    L.append("② subsume 檢定（HT10 lin vs ext_long，partial corr 控制對方）：")
    ht10 = df["HT10lin_09:30"]
    L.append(f"  r(HT10, fwdL4)={pb(ht10, fwdL4):+.3f}  → 控制 ext_long 後 partial={pcorr(ht10, fwdL4, extlong):+.3f}")
    L.append(f"  r(ext_long, fwdL4)={pb(extlong, fwdL4):+.3f}  → 控制 HT10 後 partial={pcorr(extlong, fwdL4, ht10):+.3f}")
    L.append(f"  corr(HT10, ext_long)={pb(ht10, extlong):+.3f}")

    # ③ ★套套邏輯防護：控制 TX 自身 09:30 擺幅
    L.append("\n" + "─" * 86)
    L.append("③ ★套套邏輯防護：控制『TX 自身 09:30 上行擺幅』後，forward-L4 預測力是否還在")
    L.append(f"  corr(HT10, TX自身擺幅)={pb(ht10, tx_own):+.3f}（高=HT 幾乎就是指數動能）")
    L.append(f"  r(HT10, fwdL4)={pb(ht10, fwdL4):+.3f} → 控制 TX自身 後 partial={pcorr(ht10, fwdL4, tx_own):+.3f}")
    L.append(f"  r(ext_long, fwdL4)={pb(extlong, fwdL4):+.3f} → 控制 TX自身 後 partial={pcorr(extlong, fwdL4, tx_own):+.3f}")

    # ④ 2/25 窄基案例
    L.append("\n" + "─" * 86)
    if date(2026, 2, 25) in df.index:
        r = df.loc[date(2026, 2, 25)]
        L.append(f"④ 2026-02-25（窄基重權值日）：ext_long={r['W50_09:30']:+.3f}  "
                 f"HT5={r['HT5lin_09:30']:+.3f}  HT10={r['HT10lin_09:30']:+.3f}  "
                 f"達L5={r['up_full']/r['ema20']:.2f}×  → HT 是否翻強？")

    L.append("\n  ⚠ 上市-only、181 日、偏多頭、近似權重 → 描述性，附 N。")
    txt = "\n".join(L)
    print(txt)
    out = HERE / "results"; out.mkdir(exist_ok=True)
    (out / "distribution_raw.txt").write_text(txt + "\n")
    df.assign(fwdL4=fwdL4, tx_own=tx_own).to_csv(out / "ht_panel.csv")
    print(f"\n存：{out/'distribution_raw.txt'}")


if __name__ == "__main__":
    main()
