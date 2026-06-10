"""H114 Phase 1 — 碰到關卡當下的「即時 ext_long」分辨續攻 vs 滿足點。

抽取每日 TX 上行擺幅首觸 L3/L4/L5 的分鐘 t_k，在 t_k 當下讀「即時 ext_long」
（universe W10 / W5）三種衰竭定義：
  - level   ：ext_long(t_k) 絕對水平
  - slope   ：ext_long(t_k) − ext_long(t_k−5m)（近 5 分鐘斜率，>0=還在推）
  - ddpeak  ：max(ext_long, [09:15,t_k]) − ext_long(t_k)（自當日峰回落，大=滾頭）
標記後續是否續攻 L_{k+1}（forward：只看 t_k 之後的擺幅），算 P(L_{k+1}|L_k) 依即時讀數
強弱分組的 **IS vs OOS 強−弱 gap**（headline：對照早盤凍結 09:15 讀數的 L3→L4 +30%→+7% 崩）。

對照/增量控制（皆 t_k 當下可得，因果乾淨）：
  - frozen0915：早盤 09:15 凍結 ext_long（要被取代的對象）
  - tod       ：t_k 時點（早碰 vs 晚碰）
  - satcons   ：est_range 消耗比例 = 當下上行擺幅 / (EMA20 日振幅) 的輕量滿足度代理（SatZone 完整版留 Phase 2）

限制：上市-only、stock_min 2025-06~2026-06。IS=≤2026-02-26、OOS=≥2026-03-01。L5 樣本預期薄→探索性。
用法：uv run python research/active/H114-live-ext-at-ladder/explore.py
"""
from __future__ import annotations

import sys
from datetime import date, time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
H095 = HERE.parents[0] / "H095-reach-ladder-exit"
sys.path.insert(0, str(H095))
from dci_universe_sweep import stock_features   # noqa: E402

DB = str(HERE.parents[2] / "data" / "futures.duckdb")
LO, HI = date(2025, 6, 1), date(2026, 6, 30)
IS_END = date(2026, 2, 26)
LVL = {"L3": 0.711, "L4": 0.977, "L5": 1.225}
NEXT = {"L3": "L4", "L4": "L5"}
UNIS = {"W5": 5, "W10": 10}
EXT_START = time(9, 1)        # ext_long 09:01 後才有意義（09:00 噪音）
SLOPE_LAG = 5                 # 分鐘


def tx_intraday(c):
    """每日：EMA20 日振幅 + 每分鐘 open-anchor 上行累計擺幅（dict minute->upswing）+ 全日。"""
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
    out = {}
    for d, g in bars.groupby("d"):
        g = g.sort_values("t"); hi, lo = g["high"].values, g["low"].values
        up = np.maximum.accumulate(hi - np.minimum.accumulate(lo))
        ts = [t if isinstance(t, time) else (pd.Timestamp(t).time()) for t in g["t"].values]
        out[pd.Timestamp(d).date()] = {"ema20": float(ema.get(d, np.nan)), "ts": ts, "up": up}
    return out


def ext_series_for_day(c, sel, feat_day):
    """回傳 {N: (minutes[list[time]], ext_long[np.array])}；逐分鐘 value-weighted tanh，top-N。"""
    mn = c.execute(
        "SELECT minute, stock_id, close FROM stock_min WHERE trade_date=? ORDER BY minute", [sel]).df()
    if mn.empty or feat_day.empty:
        return None
    mn["minute"] = mn["minute"].astype(str)
    panel = mn.pivot_table(index="minute", columns="stock_id", values="close", aggfunc="last").sort_index().ffill()
    f = feat_day[feat_day["stock_id"].isin(panel.columns)].set_index("stock_id")
    syms = [s for s in panel.columns if s in f.index]
    if not syms:
        return None
    panel = panel[syms]
    opn = f["open"].reindex(syms).to_numpy(float)
    rngi = f["range_i"].reindex(syms).to_numpy(float)
    tval = f["trail_val"].reindex(syms).to_numpy(float)
    P = panel.to_numpy(float)
    P = np.where(np.isnan(P), opn[None, :], P)                       # 未成交→開盤(中性)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.tanh((P - opn[None, :]) / rngi[None, :])
    order = np.argsort(-np.nan_to_num(tval, nan=-1.0))
    mins = [time.fromisoformat(x) for x in panel.index]
    res = {}
    for tag, N in UNIS.items():
        idx = order[:N]; mi = m[:, idx]; wi = tval[idx]
        ok = np.isfinite(mi) & (np.isfinite(wi) & (wi > 0))[None, :]
        num = np.where(ok, mi * wi[None, :], 0.0).sum(1)
        den = np.where(ok, wi[None, :], 0.0).sum(1)
        res[tag] = (mins, np.divide(num, den, out=np.zeros_like(num), where=den > 0))
    return res


def at_minute(mins, vals, tk, default=np.nan):
    """取 <= tk 的最後一個值（forward-fill 到 tk）；tk 早於序列起點→default。"""
    i = -1
    for j, mm in enumerate(mins):
        if mm <= tk:
            i = j
        else:
            break
    return float(vals[i]) if i >= 0 else default


def build():
    with duckdb.connect(DB, read_only=True) as c:
        feat = stock_features(c)
        tx = tx_intraday(c)
        feat_by = {d: g for d, g in feat.groupby("trade_date")}
        rows = []
        for d in sorted(tx.keys()):
            tdat = tx[d]
            ema = tdat["ema20"]
            if not (ema > 0):
                continue
            fday = feat_by.get(pd.Timestamp(d))
            if fday is None:
                continue
            es = ext_series_for_day(c, d, fday)
            if es is None:
                continue
            ts, up = tdat["ts"], tdat["up"]
            # frozen 09:15 ext_long（各 universe）
            frozen = {tag: at_minute(es[tag][0], es[tag][1], time(9, 15)) for tag in UNIS}
            for lvl, c_ in LVL.items():
                thr = c_ * ema
                cross_idx = np.argmax(up >= thr) if (up >= thr).any() else -1
                if cross_idx < 0:
                    continue
                tk = ts[cross_idx]
                rec = {"d": d, "lvl": lvl, "tk": tk, "ema20": ema,
                       "swing_at_tk": float(up[cross_idx]), "up_full": float(up[-1]),
                       "satcons": float(up[cross_idx] / ema)}     # 滿足度代理：當下擺幅/EMA20
                # 續攻：t_k 之後是否再到 L_{k+1}（forward）
                if lvl in NEXT:
                    nthr = LVL[NEXT[lvl]] * ema
                    after = up[cross_idx:]
                    rec["cont"] = int((after >= nthr).any())
                else:
                    rec["cont"] = np.nan
                for tag in UNIS:
                    mins, vals = es[tag]
                    lvl_v = at_minute(mins, vals, tk)
                    lag_v = at_minute(mins, vals, _minus(tk, SLOPE_LAG))
                    peak = max((v for mm, v in zip(mins, vals) if time(9, 15) <= mm <= tk), default=np.nan)
                    rec[f"{tag}_level"] = lvl_v
                    rec[f"{tag}_slope"] = lvl_v - lag_v if np.isfinite(lag_v) else np.nan
                    rec[f"{tag}_ddpeak"] = (peak - lvl_v) if np.isfinite(peak) else np.nan
                    rec[f"{tag}_frozen"] = frozen[tag]
                rows.append(rec)
    return pd.DataFrame(rows)


def _minus(tk, mins):
    total = tk.hour * 60 + tk.minute - mins
    return time(max(total, 0) // 60, max(total, 0) % 60)


def main():
    df = build()
    df["is_seg"] = df["d"].apply(lambda x: "IS" if x <= IS_END else "OOS")
    L = ["=" * 96,
         f"H114 Phase 1 — 即時 ext_long @關卡 分辨續攻 vs 滿足點  事件總 N={len(df)}",
         f"窗 {df['d'].min()}~{df['d'].max()}；IS={int((df['is_seg']=='IS').sum())} / OOS={int((df['is_seg']=='OOS').sum())} 事件（含所有關卡）",
         "強=即時讀數方向有利續攻（level↑/slope↑/ddpeak↓）；門檻=IS 該關卡母體 q0.50（中位數，分強弱兩半）"]

    # 各關卡事件量 + base 續攻率
    L.append("\n" + "─" * 96)
    L.append("① 關卡碰觸事件量 + base 續攻率 P(L_{k+1}|L_k)：")
    for lvl in ("L3", "L4"):
        for seg in ("IS", "OOS"):
            g = df[(df["lvl"] == lvl) & (df["is_seg"] == seg)]
            n = len(g); base = g["cont"].mean()
            L.append(f"   {lvl}→{NEXT[lvl]} {seg}: 碰觸={n}天  base 續攻={base:.0%}")

    # ② headline：三種衰竭定義 × universe，IS/OOS 強−弱 gap
    L.append("\n" + "═" * 96)
    L.append("② 即時讀數分辨力（強−弱 gap）：強弱用 IS 母體中位數切；對照 frozen0915")
    metrics = [("level", "水平", False), ("slope", "斜率", False), ("ddpeak", "自峰回落", True),
               ("frozen", "早盤0915凍結", False)]
    for lvl in ("L3", "L4"):
        L.append("\n" + "─" * 96)
        L.append(f"【{lvl}→{NEXT[lvl]}】")
        L.append(f"   {'metric':<14}{'universe':<8}{'IS強':>6}{'IS弱':>6}{'IS gap':>8}{'OOS強':>7}{'OOS弱':>7}{'OOS gap':>9}{'OOS強n':>7}")
        for tag in UNIS:
            for key, lab, invert in metrics:
                col = f"{tag}_{key}"
                gIS = df[(df["lvl"] == lvl) & (df["is_seg"] == "IS")].dropna(subset=[col, "cont"])
                if len(gIS) < 4:
                    continue
                thr = gIS[col].median()
                def split(g):
                    if invert:           # ddpeak 小=強（延伸力還在推、沒滾頭）
                        strong = g[col] <= thr; weak = g[col] > thr
                    else:
                        strong = g[col] >= thr; weak = g[col] < thr
                    return (g["cont"][strong].mean(), int(strong.sum()),
                            g["cont"][weak].mean(), int(weak.sum()))
                sIS, nsIS, wIS, _ = split(gIS)
                gOOS = df[(df["lvl"] == lvl) & (df["is_seg"] == "OOS")].dropna(subset=[col, "cont"])
                if len(gOOS):
                    sO, nsO, wO, _ = split(gOOS)
                else:
                    sO = wO = nsO = np.nan
                L.append(f"   {lab:<12}{tag:<8}{sIS:>6.0%}{wIS:>6.0%}{sIS-wIS:>+8.0%}"
                         f"{sO:>7.0%}{wO:>7.0%}{sO-wO:>+9.0%}{nsO:>7}")

    # ③ 增量控制：碰關卡時點 + 滿足度代理（看是否 ext_long 只是它們的代理）
    L.append("\n" + "═" * 96)
    L.append("③ 對照控制（同切法，IS/OOS gap）：時點(早碰=強)、滿足度代理 satcons(消耗少=強，續攻機會大?)")
    for lvl in ("L3", "L4"):
        for key, lab, invert in [("tk_min", "碰觸時點", True), ("satcons", "擺幅/EMA20", True)]:
            if key == "tk_min":
                df["tk_min"] = df["tk"].apply(lambda t: t.hour * 60 + t.minute)
            col = key
            gIS = df[(df["lvl"] == lvl) & (df["is_seg"] == "IS")].dropna(subset=[col, "cont"])
            thr = gIS[col].median()
            def split(g):
                strong = (g[col] <= thr) if invert else (g[col] >= thr)
                weak = ~strong
                return g["cont"][strong].mean(), g["cont"][weak].mean()
            sIS, wIS = split(gIS)
            gO = df[(df["lvl"] == lvl) & (df["is_seg"] == "OOS")].dropna(subset=[col, "cont"])
            sO, wO = split(gO) if len(gO) else (np.nan, np.nan)
            L.append(f"   {lvl} {lab:<10}: IS gap={sIS-wIS:+.0%}  OOS gap={sO-wO:+.0%}")

    L.append("\n  ⚠ 上市-only、全窗、L5 事件薄未列判定；強弱用 IS 中位數切（GATE 看 OOS gap 是否守住 & 贏 frozen/控制）。")
    txt = "\n".join(L)
    print(txt)
    out = HERE / "results"; out.mkdir(exist_ok=True)
    (out / "distribution_raw.txt").write_text(txt + "\n")
    df.to_csv(out / "ladder_live_ext_panel.csv", index=False)
    print(f"\n存：{out/'distribution_raw.txt'}")


if __name__ == "__main__":
    main()
