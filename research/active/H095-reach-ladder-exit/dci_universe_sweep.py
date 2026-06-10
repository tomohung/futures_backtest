"""thrust 的 universe × 寬度 掃描（Phase-1）。回答：
  - thrust 改算在「熱門」universe 行不行？
  - 空方權值真的不重要？放寬權值到 50/100 有沒有救？
  - 若放寬有用，熱門也放寬嗎？

universe（皆 causal，依 d-1 以前資料選）：
  W-fix21 : 固定權值清單（= 既有 thrust 基準）
  W-N     : 20日均成交值前 N（結構性大型股代理；無官方比重表）
  H-N     : 昨日單日成交值前 N（反應性熱門）
寬度 N ∈ {20,50,100}。
thrust_U = Σ sel_i·tanh((p_t−open_i)/range_i) / Σ sel_i  （sel=選集所用的成交值；range=該股 causal EMA20 日振幅）
對照：B（家數）。reach=TX open-anchor 全日擺幅；方向=擺更遠那邊。時點 09:15 / 09:30。
限制：上市-only，N=181。
用法：uv run python research/active/H095-reach-ladder-exit/dci_universe_sweep.py
"""
from __future__ import annotations

import os
from datetime import date, time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

DB = os.environ.get(
    "STOCK_MIN_DB",
    str(Path(__file__).resolve().parents[3] / "data" / "futures.duckdb"),
)
START, END = date(2025, 6, 1), date(2026, 6, 30)    # 全資料窗（含 OOS；OOS 複驗 2026-06）
WARMUP = date(2025, 3, 1)          # EMA20 / rolling20 暖機
SNAPS = ["09:15:00", "09:30:00"]
LVL = {"L4": 0.977}                # 聚焦 L4（reach 決策關鍵階）
WIDTHS = [20, 50, 100]
TOP_WEIGHT_SYMBOLS = [
    "2330", "2317", "2454", "2308", "2881", "2382", "2891", "2882", "2412",
    "2303", "3711", "2886", "1216", "2884", "2885", "2357", "2892", "2880",
    "3008", "2002", "2207",
]


def stock_features(c) -> pd.DataFrame:
    """全股每日 causal 特徵：open, prev, range_i(EMA20振幅), trail_val(20日均值), prev_value。"""
    sd = c.execute(
        "SELECT trade_date, symbol AS stock_id, open, high, low, close, change, value "
        "FROM stock_day WHERE trade_date BETWEEN ? AND ? AND market IN ('TWSE') "
        "ORDER BY symbol, trade_date", [WARMUP, END]).df()
    for col in ("open", "high", "low", "close", "change"):
        sd[col] = sd[col].astype(float)
    sd["value"] = sd["value"].astype(float)
    sd["prev"] = sd["close"] - sd["change"]
    rng = sd["high"] - sd["low"]
    sd["range_i"] = rng.groupby(sd["stock_id"]).transform(
        lambda s: s.shift(1).ewm(span=20, adjust=False).mean())
    sd["trail_val"] = sd.groupby("stock_id")["value"].transform(
        lambda s: s.shift(1).rolling(20, min_periods=10).mean())
    sd["prev_value"] = sd.groupby("stock_id")["value"].transform(lambda s: s.shift(1))
    return sd[sd["trade_date"] >= pd.Timestamp(START)][
        ["trade_date", "stock_id", "open", "prev", "range_i", "trail_val", "prev_value"]]


def snap_prices(c) -> pd.DataFrame:
    filt = ", ".join(
        f"arg_max(close, minute) FILTER (WHERE minute <= TIME '{s}') AS \"p_{s[:5]}\""
        for s in SNAPS)
    return c.execute(
        f"SELECT trade_date, stock_id, {filt} FROM stock_min "
        f"WHERE trade_date BETWEEN ? AND ? AND minute <= TIME '{SNAPS[-1]}' "
        f"GROUP BY trade_date, stock_id", [START, END]).df()


def tx_labels(c) -> pd.DataFrame:
    rng = c.execute(
        "SELECT CAST(timestamp AS DATE) d, MAX(high)-MIN(low) r FROM ohlcv_1m WHERE symbol='TX' "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' GROUP BY 1 ORDER BY 1").df()
    rng["ema20"] = rng["r"].astype(float).shift(1).ewm(span=20, adjust=False).mean()
    ema = rng.set_index("d")["ema20"]
    bars = c.execute(
        "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, high, low FROM ohlcv_1m "
        "WHERE symbol='TX' AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "AND CAST(timestamp AS DATE) BETWEEN ? AND ? ORDER BY d,t", [START, END]).df()
    bars["high"] = bars["high"].astype(float); bars["low"] = bars["low"].astype(float)
    ten = time.fromisoformat("10:00:00"); rows = []
    for d, gg in bars.groupby("d"):
        gg = gg.sort_values("t"); hi, lo, t = gg["high"].values, gg["low"].values, list(gg["t"].values)
        up = np.maximum.accumulate(hi - np.minimum.accumulate(lo))
        dn = np.maximum.accumulate(np.maximum.accumulate(hi) - lo)
        i10 = max(np.searchsorted(t, ten, side="right") - 1, 0)
        rows.append({"trade_date": d, "ema20": ema.get(d, np.nan),
                     "up_full": up[-1], "dn_full": dn[-1],
                     "dir_full": 1 if up[-1] >= dn[-1] else -1,
                     "dir_10": 1 if up[i10] >= dn[i10] else -1})
    return pd.DataFrame(rows).set_index("trade_date")


def wmean_tanh(sub: pd.DataFrame, pcol: str, selcol: str) -> float:
    """選集 sub 的 thrust：以 selcol 加權的 tanh((p−open)/range)。"""
    m = np.tanh((sub[pcol].values - sub["open"].values) / sub["range_i"].values)
    w = sub[selcol].values
    ok = np.isfinite(m) & np.isfinite(w) & (w > 0)
    if ok.sum() == 0:
        return 0.0
    return float(np.sum(m[ok] * w[ok]) / np.sum(w[ok]))


def build(c) -> pd.DataFrame:
    feat = stock_features(c)
    px = snap_prices(c)
    tx = tx_labels(c)
    df = px.merge(feat, on=["trade_date", "stock_id"], how="inner")
    df = df[df["range_i"] > 0]
    wfix = set(TOP_WEIGHT_SYMBOLS)
    snap_keys = [s[:5] for s in SNAPS]

    rows = []
    for d, g in df.groupby("trade_date"):
        if d not in tx.index:
            continue
        txr = tx.loc[d]
        if not (txr["ema20"] and txr["ema20"] > 0):
            continue
        ema = float(txr["ema20"]); active = len(g)
        # 各 universe 的 index
        gv = g.dropna(subset=["trail_val"])
        gh = g.dropna(subset=["prev_value"])
        unis = {"W-fix21": g[g["stock_id"].isin(wfix)]}
        for N in WIDTHS:
            unis[f"W-{N}"] = gv.nlargest(N, "trail_val")
            unis[f"H-{N}"] = gh.nlargest(N, "prev_value")
        rec = {"trade_date": d, "ema20": ema}
        for sk in snap_keys:
            # universe thrust（W-fix21 用 prev_value 加權；W-* 用 trail_val；H-* 用 prev_value）
            selmap = {"W-fix21": "prev_value"}
            for N in WIDTHS:
                selmap[f"W-{N}"] = "trail_val"; selmap[f"H-{N}"] = "prev_value"
            for uname, usub in unis.items():
                rec[f"{uname}_{sk}"] = wmean_tanh(usub, f"p_{sk}", selmap[uname])
            up = int((g[f"p_{sk}"] > g["prev"]).sum()); dn = int((g[f"p_{sk}"] < g["prev"]).sum())
            rec[f"B_{sk}"] = (up - dn) / active if active else 0.0
        for name, co in LVL.items():
            rec[f"up_{name}"] = int(txr["up_full"] >= co * ema)
            rec[f"dn_{name}"] = int(txr["dn_full"] >= co * ema)
        rec["dir_full"] = int(txr["dir_full"]); rec["dir_10"] = int(txr["dir_10"])
        rows.append(rec)
    return pd.DataFrame(rows)


def pb(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 5 or np.nanstd(x) == 0 or np.nanstd(y) == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def dir_acc(sig, tgt):
    pred = np.sign(np.asarray(sig)); ok = pred != 0
    return float((pred[ok] == np.asarray(tgt)[ok]).mean())


def main():
    with duckdb.connect(DB, read_only=True) as c:
        p = build(c)
    snap_keys = [s[:5] for s in SNAPS]
    unames = ["W-fix21"] + [f"W-{N}" for N in WIDTHS] + [f"H-{N}" for N in WIDTHS]
    L = ["=" * 84,
         f"thrust universe × 寬度 掃描  N={len(p)}  上市-only  reach=TX open-anchor(L4,全日)",
         f"範圍 {p['trade_date'].min().date()} ~ {p['trade_date'].max().date()}  "
         "W=20日均值大型股代理  H=昨日成交值熱門"]
    for sk in snap_keys:
        L.append("\n" + "─" * 84)
        L.append(f"【{sk}】  欄：多 r(up_L4)｜空 r(dn_L4,力道=−thrust)｜方向全日｜方向10:00前")
        base_f = max((p["dir_full"] == 1).mean(), (p["dir_full"] == -1).mean())
        base_t = max((p["dir_10"] == 1).mean(), (p["dir_10"] == -1).mean())
        L.append(f"{'universe':<10}{'多L4':>9}{'空L4':>9}{'方向全日':>10}{'方向10前':>10}")
        for u in unames:
            col = p[f"{u}_{sk}"]
            rL = pb(col, p["up_L4"]); rS = pb(-col, p["dn_L4"])
            aF = dir_acc(col, p["dir_full"]); aT = dir_acc(col, p["dir_10"])
            L.append(f"{u:<10}{rL:>+9.3f}{rS:>+9.3f}{aF:>9.1%}{aT:>9.1%}")
        bcol = p[f"B_{sk}"]
        L.append(f"{'B(家數)':<10}{pb(bcol, p['up_L4']):>+9.3f}{pb(-bcol, p['dn_L4']):>+9.3f}"
                 f"{dir_acc(bcol, p['dir_full']):>9.1%}{dir_acc(bcol, p['dir_10']):>9.1%}")
        L.append(f"  方向基準（多數類）：全日 {base_f:.0%}｜10:00前 {base_t:.0%}")
    txt = "\n".join(L)
    print(txt)
    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "dci_universe_sweep.txt").write_text(txt + "\n")
    p.to_csv(out / "dci_universe_panel.csv", index=False)
    print(f"\n存：{out/'dci_universe_sweep.txt'}")


if __name__ == "__main__":
    main()
