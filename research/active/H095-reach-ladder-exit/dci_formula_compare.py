"""新舊 DCI 公式對打（同一批 181 天盤中資料；Phase-1）。

原版（收盤三因子盤中化，對齊 dci_spec / dci_intraday_20260529.py）：
  W = 權值前21 sign(p_t−open) 平均（只看方向）
  H = 前一日成交值前20 sign(p_t−open) 平均（causal 選集）
  B = (up−dn)/active   vs 昨收（全 TWSE 上市）
  dci_long = .40W+.35H+.25B ; dci_short = .30W+.30H+.40B
新版：
  thrust = Σ prev_value_i·tanh((p_t−open_i)/range_i)/Σ prev_value_i  （權值前21，保留幅度+自我標準化）
  breadth = B（同一個）；新版主張 B 改當 NARROW 旗標，不進多方加總

對打維度：①各因子/合成對 reach(L4) 的鑑別力 r　②對方向(擺更遠那邊)的命中率。
時點：09:15、09:30。限制：上市-only，N=181。
用法：uv run python research/active/H095-reach-ladder-exit/dci_formula_compare.py
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
START, END = date(2025, 6, 1), date(2026, 2, 28)
SNAPS = ["09:15:00", "09:30:00"]
LVL = {"L3": 0.711, "L4": 0.977}
TOP_WEIGHT_SYMBOLS = [
    "2330", "2317", "2454", "2308", "2881", "2382", "2891", "2882", "2412",
    "2303", "3711", "2886", "1216", "2884", "2885", "2357", "2892", "2880",
    "3008", "2002", "2207",
]
_WL = (0.40, 0.35, 0.25)
_WS = (0.30, 0.30, 0.40)


def weight_ranges(c) -> pd.Series:
    sd = c.execute(
        "SELECT symbol, trade_date, high, low FROM stock_day WHERE symbol IN ({}) "
        "AND high IS NOT NULL ORDER BY symbol, trade_date".format(
            ",".join("?" * len(TOP_WEIGHT_SYMBOLS))), TOP_WEIGHT_SYMBOLS).df()
    sd["rng"] = sd["high"].astype(float) - sd["low"].astype(float)
    sd["range_i"] = sd.groupby("symbol")["rng"].transform(
        lambda s: s.shift(1).ewm(span=20, adjust=False).mean())
    return sd.set_index(["symbol", "trade_date"])["range_i"]


def load(c):
    filt = ", ".join(
        f"arg_max(close, minute) FILTER (WHERE minute <= TIME '{s}') AS \"p_{s[:5]}\""
        for s in SNAPS)
    px = c.execute(
        f"SELECT trade_date, stock_id, {filt} FROM stock_min "
        f"WHERE trade_date BETWEEN ? AND ? AND minute <= TIME '{SNAPS[-1]}' "
        f"GROUP BY trade_date, stock_id", [START, END]).df()
    sd = c.execute(
        "SELECT trade_date, symbol AS stock_id, open, close, change, value "
        "FROM stock_day WHERE trade_date BETWEEN ? AND ?", [START, END]).df()
    sd["open"] = sd["open"].astype(float)
    sd["prev"] = sd["close"].astype(float) - sd["change"].astype(float)
    sd = sd.sort_values(["stock_id", "trade_date"])
    sd["prev_value"] = sd.groupby("stock_id")["value"].shift(1)
    m = px.merge(sd[["trade_date", "stock_id", "open", "prev", "prev_value"]],
                 on=["trade_date", "stock_id"], how="inner")
    return m


def tx_dir_reach(c):
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
    ten = time.fromisoformat("10:00:00")
    rows = []
    for d, g in bars.groupby("d"):
        g = g.sort_values("t"); hi, lo, t = g["high"].values, g["low"].values, list(g["t"].values)
        up = np.maximum.accumulate(hi - np.minimum.accumulate(lo))
        dn = np.maximum.accumulate(np.maximum.accumulate(hi) - lo)
        i10 = max(np.searchsorted(t, ten, side="right") - 1, 0)
        rows.append({"trade_date": d, "ema20": ema.get(d, np.nan),
                     "up_full": up[-1], "dn_full": dn[-1],
                     "dir_full": 1 if up[-1] >= dn[-1] else -1,
                     "dir_10": 1 if up[i10] >= dn[i10] else -1})
    return pd.DataFrame(rows).set_index("trade_date")


def build(c):
    ranges = weight_ranges(c); m = load(c); tx = tx_dir_reach(c)
    wset = set(TOP_WEIGHT_SYMBOLS); rows = []
    for d, g in m.groupby("trade_date"):
        if d not in tx.index:
            continue
        txr = tx.loc[d]
        if not (txr["ema20"] and txr["ema20"] > 0):
            continue
        ema = float(txr["ema20"]); active = len(g)
        # H 集合：前一日成交值前 20（causal）
        hset = set(g.dropna(subset=["prev_value"]).nlargest(20, "prev_value")["stock_id"])
        rec = {"trade_date": d, "ema20": ema}
        for sk in [s[:5] for s in SNAPS]:
            p = g[f"p_{sk}"]
            so = np.sign(p - g["open"])      # vs 開盤（W/H 投票）
            up = int((p > g["prev"]).sum()); dn = int((p < g["prev"]).sum())
            B = (up - dn) / active if active else 0.0
            wmask = g["stock_id"].isin(wset)
            hmask = g["stock_id"].isin(hset)
            W = so[wmask].mean() if wmask.any() else 0.0
            H = so[hmask].mean() if hmask.any() else 0.0
            # 新版 thrust
            num = den = 0.0
            for pi, sym, opn, wt in zip(g[f"p_{sk}"].values[wmask.values],
                                        g["stock_id"].values[wmask.values],
                                        g["open"].values[wmask.values],
                                        g["prev_value"].values[wmask.values]):
                ri = ranges.get((sym, d), np.nan)
                if not (ri and ri > 0) or not (wt and wt > 0) or pd.isna(pi):
                    continue
                num += np.tanh((pi - opn) / ri) * wt; den += wt
            thrust = num / den if den else 0.0
            rec.update({
                f"W_{sk}": W, f"H_{sk}": H, f"B_{sk}": B, f"thrust_{sk}": thrust,
                f"dciL_{sk}": _WL[0]*W + _WL[1]*H + _WL[2]*B,
                f"dciS_{sk}": _WS[0]*W + _WS[1]*H + _WS[2]*B,
            })
        for name, co in LVL.items():
            lvl = co * ema
            rec[f"up_{name}"] = int(txr["up_full"] >= lvl)
            rec[f"dn_{name}"] = int(txr["dn_full"] >= lvl)
        rec["dir_full"] = int(txr["dir_full"]); rec["dir_10"] = int(txr["dir_10"])
        rows.append(rec)
    return pd.DataFrame(rows)


def pb(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 5 or x.std() == 0 or y.std() == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def dir_acc(sig, tgt):
    pred = np.sign(sig); ok = pred != 0
    return float((pred[ok] == np.asarray(tgt)[ok]).mean())


def main():
    with duckdb.connect(DB, read_only=True) as c:
        p = build(c)
    L = ["=" * 80,
         "新舊 DCI 公式對打  N=%d  上市-only  reach=TX open-anchor(full-day)" % len(p),
         f"範圍 {p['trade_date'].min().date()} ~ {p['trade_date'].max().date()}"]

    for sk in [s[:5] for s in SNAPS]:
        L.append("\n" + "─" * 80)
        L.append(f"【時點 {sk}】")
        # ① reach 鑑別力（多 L4 / 空 L4）
        L.append("① 對 reach 的鑑別力 r：")
        L.append(f"{'因子/合成':<14}{'多L3':>8}{'多L4':>8}{'空L3':>8}{'空L4':>8}")
        items = [
            ("W(權值sign)", p[f"W_{sk}"], p[f"W_{sk}"]),
            ("H(熱門sign)", p[f"H_{sk}"], p[f"H_{sk}"]),
            ("B(家數)", p[f"B_{sk}"], -p[f"B_{sk}"]),
            ("thrust(新)", p[f"thrust_{sk}"], -p[f"thrust_{sk}"]),
            ("dci_long(舊)", p[f"dciL_{sk}"], None),
            ("dci_short(舊)", None, p[f"dciS_{sk}"]),
        ]
        for nm, longsig, shortsig in items:
            cL3 = f"{pb(longsig, p['up_L3']):+.3f}" if longsig is not None else "   -  "
            cL4 = f"{pb(longsig, p['up_L4']):+.3f}" if longsig is not None else "   -  "
            sL3 = f"{pb(shortsig, p['dn_L3']):+.3f}" if shortsig is not None else "   -  "
            sL4 = f"{pb(shortsig, p['dn_L4']):+.3f}" if shortsig is not None else "   -  "
            L.append(f"{nm:<14}{cL3:>8}{cL4:>8}{sL3:>8}{sL4:>8}")

        # ② 方向命中率
        L.append("② 方向命中率（擺更遠那邊；基準=多數類）：")
        for tgt, lab in (("dir_full", "全日"), ("dir_10", "10:00前")):
            base = max((p[tgt] == 1).mean(), (p[tgt] == -1).mean())
            sigs = [("舊 dci_long", p[f"dciL_{sk}"]), ("新 thrust", p[f"thrust_{sk}"]),
                    ("W only", p[f"W_{sk}"]), ("H only", p[f"H_{sk}"]), ("B only", p[f"B_{sk}"])]
            cells = "  ".join(f"{nm}={dir_acc(s, p[tgt]):.1%}" for nm, s in sigs)
            L.append(f"   {lab}(基準{base:.0%}): {cells}")

    txt = "\n".join(L)
    print(txt)
    out = Path(__file__).parent / "results"; out.mkdir(exist_ok=True)
    (out / "dci_formula_compare.txt").write_text(txt + "\n")
    print(f"\n存：{out/'dci_formula_compare.txt'}")


if __name__ == "__main__":
    main()
