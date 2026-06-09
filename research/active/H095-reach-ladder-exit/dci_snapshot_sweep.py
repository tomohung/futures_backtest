"""DCI 盤中多時點掃描 — 回答三問（Phase-1 探索）。

承 dci_intraday_calibrate.py。把單一 09:30 快照擴成 09:01/09:05/09:10/09:15/09:30，
回答：
  Q1 早盤各時點 thrust 對「該時點之後才達 L3/L4」的鑑別力（forward-guarded，防套套邏輯）。
  Q2 各時點 sign(thrust) 能否決定當日（與 10:00 前）該站的方向 = 擺得更遠的那一邊。
  Q3 上市-only breadth 下，多/空是否需要不同公式（用多空鑑別力差異判讀）。

公式同 spec §2：thrust=Σw_i·tanh((p_t−open_i)/range_i)/Σw_i（權值前21，前一日成交值權重）；
breadth=(up_t−dn_t)/active（全 TWSE 上市，vs 昨收）；confirm=breadth·sign(thrust)。
reach=TX open-anchor 擺幅 vs c×EMA20（L3=0.711,L4=0.977）。

限制：stock_min 為 TWSE 上市-only；N=181（2025-06~2026-02）。
用法：uv run python research/active/H095-reach-ladder-exit/dci_snapshot_sweep.py
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
SNAPS = ["09:01:00", "09:05:00", "09:10:00", "09:15:00", "09:30:00"]
DIR_HORIZON = "10:00:00"   # Q2「10:00 前方向」的視窗
LVL = {"L3": 0.711, "L4": 0.977}
TOP_WEIGHT_SYMBOLS = [
    "2330", "2317", "2454", "2308", "2881", "2382", "2891", "2882", "2412",
    "2303", "3711", "2886", "1216", "2884", "2885", "2357", "2892", "2880",
    "3008", "2002", "2207",
]


def weight_ranges(c) -> pd.Series:
    sd = c.execute(
        "SELECT symbol, trade_date, high, low FROM stock_day "
        "WHERE symbol IN ({}) AND high IS NOT NULL ORDER BY symbol, trade_date".format(
            ",".join("?" * len(TOP_WEIGHT_SYMBOLS))), TOP_WEIGHT_SYMBOLS,
    ).df()
    sd["rng"] = sd["high"].astype(float) - sd["low"].astype(float)
    sd["range_i"] = sd.groupby("symbol")["rng"].transform(
        lambda s: s.shift(1).ewm(span=20, adjust=False).mean())
    return sd.set_index(["symbol", "trade_date"])["range_i"]


def snapshot_prices(c) -> pd.DataFrame:
    """每日每檔在各時點的價（≤t 最後一根 close）。寬表：p_<snap>。"""
    filt = ", ".join(
        f"arg_max(close, minute) FILTER (WHERE minute <= TIME '{s}') AS \"p_{s[:5]}\""
        for s in SNAPS)
    px = c.execute(
        f"SELECT trade_date, stock_id, {filt} FROM stock_min "
        f"WHERE trade_date BETWEEN ? AND ? AND minute <= TIME '{SNAPS[-1]}' "
        f"GROUP BY trade_date, stock_id", [START, END]
    ).df()
    sd = c.execute(
        "SELECT trade_date, symbol AS stock_id, open, close, change, value "
        "FROM stock_day WHERE trade_date BETWEEN ? AND ?", [START, END]
    ).df()
    sd["open"] = sd["open"].astype(float)
    sd["prev"] = sd["close"].astype(float) - sd["change"].astype(float)
    sd = sd.sort_values(["stock_id", "trade_date"])
    sd["prev_value"] = sd.groupby("stock_id")["value"].shift(1)
    return px.merge(sd[["trade_date", "stock_id", "open", "prev", "prev_value"]],
                    on=["trade_date", "stock_id"], how="inner")


def tx_swings(c) -> pd.DataFrame:
    """每日 TX：EMA20 + 各時點/10:00/全日的累計 up/dn 擺幅。"""
    rng = c.execute(
        "SELECT CAST(timestamp AS DATE) d, MAX(high)-MIN(low) r FROM ohlcv_1m "
        "WHERE symbol='TX' AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "GROUP BY 1 ORDER BY 1"
    ).df()
    rng["ema20"] = rng["r"].astype(float).shift(1).ewm(span=20, adjust=False).mean()
    ema = rng.set_index("d")["ema20"]
    bars = c.execute(
        "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, high, low FROM ohlcv_1m "
        "WHERE symbol='TX' AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "AND CAST(timestamp AS DATE) BETWEEN ? AND ? ORDER BY d, t", [START, END]
    ).df()
    bars["high"] = bars["high"].astype(float); bars["low"] = bars["low"].astype(float)
    marks = [s[:5] for s in SNAPS] + ["10:00", "full"]
    cut = {s[:5]: time.fromisoformat(s) for s in SNAPS}
    cut["10:00"] = time.fromisoformat(DIR_HORIZON)
    rows = []
    for d, g in bars.groupby("d"):
        g = g.sort_values("t")
        hi, lo, t = g["high"].values, g["low"].values, list(g["t"].values)
        up_sw = np.maximum.accumulate(hi - np.minimum.accumulate(lo))
        dn_sw = np.maximum.accumulate(np.maximum.accumulate(hi) - lo)
        rec = {"trade_date": d, "ema20": ema.get(d, np.nan)}
        for m in marks:
            if m == "full":
                i = len(t) - 1
            else:
                i = max(np.searchsorted(t, cut[m], side="right") - 1, 0)
            rec[f"up_{m}"] = up_sw[i]; rec[f"dn_{m}"] = dn_sw[i]
        rows.append(rec)
    return pd.DataFrame(rows)


def build(c) -> pd.DataFrame:
    ranges = weight_ranges(c)
    px = snapshot_prices(c)
    tx = tx_swings(c).set_index("trade_date")
    wset = set(TOP_WEIGHT_SYMBOLS)
    snap_keys = [s[:5] for s in SNAPS]

    rows = []
    for d, g in px.groupby("trade_date"):
        if d not in tx.index:
            continue
        txr = tx.loc[d]
        if not (txr["ema20"] and txr["ema20"] > 0):
            continue
        ema = float(txr["ema20"])
        active = len(g)
        rec = {"trade_date": d, "ema20": ema, "active": active}
        w = g[g["stock_id"].isin(wset)]
        for sk in snap_keys:
            p = g[f"p_{sk}"]
            up = int((p > g["prev"]).sum()); dn = int((p < g["prev"]).sum())
            rec[f"breadth_{sk}"] = (up - dn) / active if active else 0.0
            # thrust（權值）
            num = den = 0.0
            wp = w[f"p_{sk}"].values
            for pi, sym, opn, wt in zip(wp, w["stock_id"].values,
                                        w["open"].values, w["prev_value"].values):
                ri = ranges.get((sym, d), np.nan)
                if not (ri and ri > 0) or not (wt and wt > 0) or pd.isna(pi):
                    continue
                num += np.tanh((pi - opn) / ri) * wt; den += wt
            rec[f"thrust_{sk}"] = num / den if den else 0.0
        # reach 標記：各時點之後才達（forward）
        for name, co in LVL.items():
            lvl = co * ema
            rec[f"up_{name}_full"] = int(txr["up_full"] >= lvl)
            rec[f"dn_{name}_full"] = int(txr["dn_full"] >= lvl)
            for sk in snap_keys:
                rec[f"up_{name}_pre_{sk}"] = int(txr[f"up_{sk}"] >= lvl)
                rec[f"dn_{name}_pre_{sk}"] = int(txr[f"dn_{sk}"] >= lvl)
                rec[f"up_{name}_fwd_{sk}"] = int(txr[f"up_{sk}"] < lvl <= txr["up_full"])
                rec[f"dn_{name}_fwd_{sk}"] = int(txr[f"dn_{sk}"] < lvl <= txr["dn_full"])
        # 方向標的：哪一邊擺得更遠
        rec["dir_full"] = 1 if txr["up_full"] >= txr["dn_full"] else -1
        rec["dir_10"] = 1 if txr["up_10:00"] >= txr["dn_10:00"] else -1
        rows.append(rec)
    return pd.DataFrame(rows)


def pb(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 5 or x.std() == 0 or y.std() == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def decile_hit(df, xcol, ycol, q=5):
    d = df[[xcol, ycol]].dropna()
    if len(d) < q * 3:
        return ""
    try:
        d = d.assign(b=pd.qcut(d[xcol], q, duplicates="drop"))
    except ValueError:
        return ""
    g = d.groupby("b", observed=True)[ycol].agg(["mean", "count"])
    return "  ".join(f"[{m:.0%},n{int(n)}]" for m, n in zip(g["mean"], g["count"]))


def main():
    with duckdb.connect(DB, read_only=True) as c:
        p = build(c)
    snap_keys = [s[:5] for s in SNAPS]
    L = []
    L.append("=" * 78)
    L.append("DCI 盤中多時點掃描（Phase-1）  breadth=上市-only  reach=TX open-anchor")
    L.append(f"範圍 {p['trade_date'].min().date()} ~ {p['trade_date'].max().date()}  N={len(p)} 日")

    # ── Q1：各時點 thrust → forward reach 鑑別力（多空、L3/L4）──
    L.append("\n" + "─" * 78)
    L.append("Q1) 各時點 thrust 對『該時點之後才達標』的鑑別力  r(力道,forward reach)")
    L.append(f"{'時點':>7} | {'多L3':>7} {'多L4':>7} | {'空L3':>7} {'空L4':>7}   (空方力道=−thrust)")
    for sk in snap_keys:
        cells = []
        for side in ("up", "dn"):
            force = p[f"thrust_{sk}"] if side == "up" else -p[f"thrust_{sk}"]
            for lvl in ("L3", "L4"):
                sub = p[p[f"{side}_{lvl}_pre_{sk}"] == 0]   # 該時點尚未達
                r = pb(force.loc[sub.index], sub[f"{side}_{lvl}_fwd_{sk}"])
                cells.append(f"{r:+.3f}")
        L.append(f"{sk:>7} | {cells[0]:>7} {cells[1]:>7} | {cells[2]:>7} {cells[3]:>7}")
    # 最具代表的多L4 forward 分位
    L.append("\n  多方 L4 forward 力道五分位達標率（看單調性/τ）：")
    for sk in snap_keys:
        sub = p[p[f"up_L4_pre_{sk}"] == 0].assign(f=p[f"thrust_{sk}"])
        L.append(f"    {sk}: " + decile_hit(sub, "f", f"up_L4_fwd_{sk}"))

    # ── Q2：各時點 sign(thrust) 決定方向（擺更遠那邊）──
    L.append("\n" + "─" * 78)
    L.append("Q2) sign(thrust_t) 預測『擺得更遠的一邊』命中率（基準=多數類）")
    for tgt, lab in (("dir_full", "全日方向"), ("dir_10", "10:00前方向")):
        base = max((p[tgt] == 1).mean(), (p[tgt] == -1).mean())
        L.append(f"  [{lab}]  多數類基準={base:.1%}")
        L.append(f"    {'時點':>7} | {'全體命中':>8} {'|thrust|前1/3命中':>16} {'前1/3覆蓋':>10}")
        for sk in snap_keys:
            pred = np.sign(p[f"thrust_{sk}"])
            hit = (pred == p[tgt])
            acc = hit[pred != 0].mean()
            thr = p[f"thrust_{sk}"].abs()
            strong = thr >= thr.quantile(2/3)
            acc_s = hit[strong & (pred != 0)].mean()
            cov = strong.mean()
            L.append(f"    {sk:>7} | {acc:8.1%} {acc_s:16.1%} {cov:10.1%}")

    # ── Q3：多空對稱性 ──
    L.append("\n" + "─" * 78)
    L.append("Q3) 多空對稱性（09:15 為例）：同一 thrust 對多/空 reach 的鑑別力是否需拆公式")
    sk = "09:15"
    for side in ("up", "dn"):
        force = p[f"thrust_{sk}"] if side == "up" else -p[f"thrust_{sk}"]
        r3 = pb(force, p[f"{side}_L3_full"]); r4 = pb(force, p[f"{side}_L4_full"])
        rate3 = p[f"{side}_L3_full"].mean(); rate4 = p[f"{side}_L4_full"].mean()
        L.append(f"  {'多' if side=='up' else '空'}方 full: r(L3)={r3:+.3f} r(L4)={r4:+.3f}  "
                 f"達標率 L3={rate3:.1%} L4={rate4:.1%}")
    # breadth 單獨對方向/reach 的貢獻（上市-only 下還有沒有用）
    L.append("  breadth(上市) 單獨鑑別力 09:15：")
    for side in ("up", "dn"):
        bf = p[f"breadth_{sk}"] if side == "up" else -p[f"breadth_{sk}"]
        L.append(f"    {'多' if side=='up' else '空'}方 r(breadth,L4_full)="
                 f"{pb(bf, p[f'{side}_L4_full']):+.3f}")

    txt = "\n".join(L)
    print(txt)
    out = Path(__file__).parent / "results"
    out.mkdir(exist_ok=True)
    (out / "dci_snapshot_sweep.txt").write_text(txt + "\n")
    p.to_csv(out / "dci_snapshot_panel.csv", index=False)
    print(f"\n存：{out/'dci_snapshot_sweep.txt'}")


if __name__ == "__main__":
    main()
