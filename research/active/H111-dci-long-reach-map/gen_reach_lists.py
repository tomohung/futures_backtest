"""產生 chart-ui 覆盤清單：多/空 × 關卡(L4/L5) × 首次到達時段(09:30前/10:30前/11:30前)。

互斥分桶——每個交易日（每側、每關卡）只進「首次達該關卡的那個時段」（09:30前⊂10:30前⊂11:30前 不重複）；
11:30 後才到 / 沒到的日子不列入。多=上行(side long)、空=下行(side short)。
註記帶首達時間、達到幅度、ext_long/ext_short@09:30（對照訊號）。共 2 側 × 2 關卡 × 3 時段 = 12 清單。

用法：uv run python research/active/H111-dci-long-reach-map/gen_reach_lists.py
"""
from __future__ import annotations

from datetime import date, time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from src.chart_ui.list_writer import write_chart_list

HERE = Path(__file__).parent
DB = str(HERE.parents[2] / "data" / "futures.duckdb")
LO, HI = date(2025, 6, 2), date(2026, 6, 30)     # 全資料窗（含 OOS）
LEVELS = {"L4": 0.977, "L5": 1.225}
T0930, T1030, T1130 = time(9, 30), time(10, 30), time(11, 30)
LABELS = {"0930": "09:30前", "1030": "10:30前", "1130": "11:30前"}


def reach_times():
    """每日 up/dn 對各關卡的首達時間 + ema20 + 全日幅度。"""
    with duckdb.connect(DB, read_only=True) as c:
        rng = c.execute(
            "SELECT CAST(timestamp AS DATE) d, MAX(high)-MIN(low) r FROM ohlcv_1m WHERE symbol='TX' "
            "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' GROUP BY 1 ORDER BY 1").df()
        rng["ema20"] = rng["r"].astype(float).shift(1).ewm(span=20, adjust=False).mean()
        ema = rng.set_index("d")["ema20"]
        bars = c.execute(
            "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, high, low FROM ohlcv_1m WHERE symbol='TX' "
            "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
            "AND CAST(timestamp AS DATE) BETWEEN ? AND ? ORDER BY d,t", [LO, HI]).df()
    bars["high"] = bars["high"].astype(float); bars["low"] = bars["low"].astype(float)
    rows = []
    for d, g in bars.groupby("d"):
        dd = pd.Timestamp(d).date(); e = ema.get(d, np.nan)
        if not (e > 0):
            continue
        g = g.sort_values("t"); hi, lo, t = g["high"].values, g["low"].values, list(g["t"].values)
        up = np.maximum.accumulate(hi - np.minimum.accumulate(lo))
        dn = np.maximum.accumulate(np.maximum.accumulate(hi) - lo)
        rec = {"d": dd, "ema20": e, "up_full": up[-1], "dn_full": dn[-1]}
        for lname, c_ in LEVELS.items():
            lvl = c_ * e
            iu = np.argmax(up >= lvl) if (up >= lvl).any() else -1
            idn = np.argmax(dn >= lvl) if (dn >= lvl).any() else -1
            rec[f"up_{lname}"] = t[iu] if iu >= 0 else None
            rec[f"dn_{lname}"] = t[idn] if idn >= 0 else None
        rows.append(rec)
    return pd.DataFrame(rows).set_index("d")


def bucket(tm):
    if tm is None:
        return None
    return "0930" if tm <= T0930 else "1030" if tm <= T1030 else "1130" if tm <= T1130 else None


def main():
    fr = reach_times()
    pl = pd.read_csv(HERE / "results" / "reach_map_panel.csv"); pl["d"] = pd.to_datetime(pl.iloc[:, 0]).dt.date
    extlong = pl.set_index("d")["W10_09:30"]   # 對齊 chart-ui 副圖（ext_long 已改 W10）
    ps = pd.read_csv(HERE.parents[0] / "H112-dci-short-reach-map" / "results" / "short_reach_panel.csv")
    ps["d"] = pd.to_datetime(ps.iloc[:, 0]).dt.date
    extshort = ps.set_index("d")["comp_09:30"]

    written = []
    for lname in LEVELS:
        for side, full_col, sig, signame in (("up", "up_full", extlong, "ext_long"),
                                             ("dn", "dn_full", extshort, "ext_short")):
            buckets = {b: [] for b in LABELS}
            for d, r in fr.iterrows():
                b = bucket(r[f"{side}_{lname}"])
                if b is None:
                    continue
                sv = sig.get(d, np.nan)
                note = (f"{side} {lname} 首達 {str(r[f'{side}_{lname}'])[:5]}｜幅度 {r[full_col]/r['ema20']:.2f}×EMA20"
                        + (f"｜{signame}@09:30={sv:+.3f}" if pd.notna(sv) else ""))
                buckets[b].append({"time": f"{d} 08:45:00",
                                   "side": "long" if side == "up" else "short", "note": note})
            for b, items in buckets.items():
                items.sort(key=lambda x: x["time"], reverse=True)
                sd = "多" if side == "up" else "空"
                lid = f"{lname.lower()}-{'up' if side=='up' else 'dn'}-{b}"
                write_chart_list(lid, items,
                                 name=f"{sd}·{lname}·{LABELS[b]} (n={len(items)})",
                                 desc=f"TX {('上行' if side=='up' else '下行')}首次達 {lname} 落在 {LABELS[b]}（互斥分桶）。")
                written.append((lid, len(items)))

    print("已產生 12 清單（data/chart_lists/）：")
    for lid, n in written:
        print(f"  {lid}: {n} 天")
    # 互斥驗證（每側每關卡：同一天只會落在一個時段桶）
    for lname in LEVELS:
        for side in ("up", "dn"):
            tcol_days = [d for d, r in fr.iterrows() if bucket(r[f"{side}_{lname}"]) is not None]
            print(f"  {lname} {side}: {len(tcol_days)} 天、不重複 {len(set(tcol_days))} → "
                  f"{'OK' if len(tcol_days)==len(set(tcol_days)) else '重複!'}")


if __name__ == "__main__":
    main()
