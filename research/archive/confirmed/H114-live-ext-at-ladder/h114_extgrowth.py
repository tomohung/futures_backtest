"""H114 衍生探索 — 早碰 L3 子集，用「ext_long 早盤窗增幅」(非絕對值)再分一刀。

使用者想法：早碰 L3 後，若 ext_long 在 09:15→09:30 / 09:15→10:00 仍「續增」(多方力道加速)，
對後續續攻 L4 還可期待。對照「碰觸當下絕對水平/自峰回落」(早碰層無增量) 的不同切角。

設計（forward-guarded）：
  - 早碰 = L3 碰觸時點 ≤ EARLY_CUT。
  - Δext_a = ext(09:30) − ext(09:15)；Δext_b = ext(10:00) − ext(09:15)（W10，備 W5）。
  - 母體 = 早碰 且 窗結束時尚未到 L4（避免 look-ahead / 已贏）。
  - outcome = 窗結束之後才首次到 L4（cont_fwd）。
  - 依 Δext>0(力道續增) vs ≤0(轉弱) 分組，P(cont_fwd) 的 IS/OOS gap。
用法：uv run python research/active/H114-live-ext-at-ladder/h114_extgrowth.py
"""
from __future__ import annotations

import sys
from datetime import date, time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[0] / "H095-reach-ladder-exit"))
from dci_universe_sweep import stock_features   # noqa: E402

DB = str(HERE.parents[2] / "data" / "futures.duckdb")
LO, HI = date(2025, 6, 1), date(2026, 6, 30)
IS_END = date(2026, 2, 26)
L3, L4 = 0.711, 0.977
EARLY_CUT = time(10, 0)          # 早碰定義（OOS-誠實區）
UNIS = {"W5": 5, "W10": 10}
MARKS = {"0915": time(9, 15), "0930": time(9, 30), "1000": time(10, 0)}


def ext_at_marks(c, sel, fday):
    mn = c.execute("SELECT minute, stock_id, close FROM stock_min WHERE trade_date=? ORDER BY minute", [sel]).df()
    if mn.empty or fday.empty:
        return None
    mn["minute"] = mn["minute"].astype(str)
    panel = mn.pivot_table(index="minute", columns="stock_id", values="close", aggfunc="last").sort_index().ffill()
    f = fday[fday["stock_id"].isin(panel.columns)].set_index("stock_id")
    syms = [s for s in panel.columns if s in f.index]
    if not syms:
        return None
    panel = panel[syms]
    opn = f["open"].reindex(syms).to_numpy(float); rngi = f["range_i"].reindex(syms).to_numpy(float)
    tval = f["trail_val"].reindex(syms).to_numpy(float)
    P = panel.to_numpy(float); P = np.where(np.isnan(P), opn[None, :], P)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.tanh((P - opn[None, :]) / rngi[None, :])
    order = np.argsort(-np.nan_to_num(tval, nan=-1.0))
    mins = [time.fromisoformat(x) for x in panel.index]
    def val_at(vals, tm):
        i = -1
        for j, mm in enumerate(mins):
            if mm <= tm:
                i = j
            else:
                break
        return float(vals[i]) if i >= 0 else np.nan
    out = {}
    for tag, N in UNIS.items():
        idx = order[:N]; mi = m[:, idx]; wi = tval[idx]
        ok = np.isfinite(mi) & (np.isfinite(wi) & (wi > 0))[None, :]
        num = np.where(ok, mi * wi[None, :], 0.0).sum(1); den = np.where(ok, wi[None, :], 0.0).sum(1)
        ser = np.divide(num, den, out=np.zeros_like(num), where=den > 0)
        out[tag] = {k: val_at(ser, tm) for k, tm in MARKS.items()}
    return out


def main():
    with duckdb.connect(DB, read_only=True) as c:
        feat = stock_features(c); feat_by = {d: g for d, g in feat.groupby("trade_date")}
        rng = c.execute("SELECT CAST(timestamp AS DATE) d, MAX(high)-MIN(low) r FROM ohlcv_1m WHERE symbol='TX' "
                        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' GROUP BY 1 ORDER BY 1").df()
        rng["ema20"] = rng["r"].astype(float).shift(1).ewm(span=20, adjust=False).mean(); ema = rng.set_index("d")["ema20"]
        bars = c.execute("SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, high, low FROM ohlcv_1m WHERE symbol='TX' "
                         "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
                         "AND CAST(timestamp AS DATE) BETWEEN ? AND ? ORDER BY d,t", [LO, HI]).df()
        bars["high"] = bars["high"].astype(float); bars["low"] = bars["low"].astype(float)
        rows = []
        for d, g in bars.groupby("d"):
            e = float(ema.get(d, np.nan))
            if not (e > 0):
                continue
            fday = feat_by.get(pd.Timestamp(d))
            if fday is None:
                continue
            ex = ext_at_marks(c, pd.Timestamp(d).date(), fday)
            if ex is None:
                continue
            g = g.sort_values("t"); hi, lo = g["high"].values, g["low"].values
            ts = [t if isinstance(t, time) else pd.Timestamp(t).time() for t in g["t"].values]
            up = np.maximum.accumulate(hi - np.minimum.accumulate(lo))
            ci3 = np.argmax(up >= L3 * e) if (up >= L3 * e).any() else -1
            if ci3 < 0:
                continue
            tk3 = ts[ci3]
            ci4 = np.argmax(up >= L4 * e) if (up >= L4 * e).any() else -1
            tk4 = ts[ci4] if ci4 >= 0 else None
            rec = {"d": pd.Timestamp(d).date(), "tk3": tk3, "tk4": tk4}
            for tag in UNIS:
                rec[f"{tag}_d_a"] = ex[tag]["0930"] - ex[tag]["0915"]    # 09:15→09:30 增幅
                rec[f"{tag}_d_b"] = ex[tag]["1000"] - ex[tag]["0915"]    # 09:15→10:00 增幅
            rows.append(rec)
    df = pd.DataFrame(rows)
    df["seg"] = df["d"].apply(lambda x: "IS" if x <= IS_END else "OOS")
    df["early"] = df["tk3"] <= EARLY_CUT

    def reached_after(row, wend):
        return int(row["tk4"] is not None and row["tk4"] > wend)
    def notyet(row, wend):
        return (row["tk4"] is None) or (row["tk4"] > wend)

    print(f"早碰 L3 (≤{EARLY_CUT}) 子集；ext_long 早盤增幅 → 後續(窗後)到 L4。forward-guarded。\n")
    for win, wend, dcol in [("09:15→09:30", time(9, 30), "d_a"), ("09:15→10:00", time(10, 0), "d_b")]:
        print(f"=== 窗 {win} ===")
        for tag in UNIS:
            col = f"{tag}_{dcol}"
            for seg in ("IS", "OOS"):
                g = df[(df["seg"] == seg) & df["early"]].copy()
                g = g[g.apply(lambda r: notyet(r, wend), axis=1)]    # 窗結束時尚未到 L4
                g["cont"] = g.apply(lambda r: reached_after(r, wend), axis=1)
                g = g.dropna(subset=[col])
                if len(g) < 4:
                    print(f"  {tag} {seg}: n={len(g)} 太少"); continue
                up = g[g[col] > 0]["cont"]; dn = g[g[col] <= 0]["cont"]
                base = g["cont"].mean()
                print(f"  {tag} {seg}: 母體n={len(g)} base續攻={base:.0%} | 力道續增(Δ>0) {up.mean():.0%}(n{len(up)}) "
                      f"vs 轉弱(Δ≤0) {dn.mean():.0%}(n{len(dn)})  gap={up.mean()-dn.mean():+.0%}")
        print()


if __name__ == "__main__":
    main()
