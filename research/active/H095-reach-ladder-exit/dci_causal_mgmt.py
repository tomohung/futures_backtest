"""因果修正：dci 不能當 EstHL 進場濾網（進場中位 09:01），但能當『進場後管理』訊號。

問題：dci_exit_modulate 用 09:15 dci 做進場分組 = look-ahead（進場中位 09:01）。
修正：
  ① 排序力隨『因果檢查點』t∈{09:05,09:10,09:15} 怎麼變（t 都在多數進場之後 → 當管理訊號合法）。
  ② 合法管理動作：09:15 在倉時，若 dci_long<0（龍頭未站上開盤）→ 砍倉(exit TX@09:15)，
     否則 hold 到 fixed-L3。比 baseline(全 hold) 好不好。
  ③ 09:05 能否佐證（對進場≥09:05 的 14 筆是因果的）。

dci_long = W-20 thrust（動態 20日均值大型股，value-weighted tanh）。
窗內 N=44，in-sample，偏多頭 → 指示性。
用法：uv run python research/active/H095-reach-ladder-exit/dci_causal_mgmt.py
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
sys.path.insert(0, str(HERE))
from dci_universe_sweep import stock_features, wmean_tanh   # noqa: E402
from phase2_path_backtest import build_entries, simulate, C  # noqa: E402
from src.backtest.runner import load_data_for_orb_est_hl     # noqa: E402

DB = os.environ.get("STOCK_MIN_DB", str(HERE.parents[2] / "data" / "futures.duckdb"))
LO, HI = date(2025, 6, 2), date(2026, 2, 26)
CKPTS = ["09:05:00", "09:10:00", "09:15:00"]


def snap_at(c, times):
    filt = ", ".join(
        f"arg_max(close, minute) FILTER (WHERE minute <= TIME '{s}') AS \"p_{s[:5]}\"" for s in times)
    return c.execute(
        f"SELECT trade_date, stock_id, {filt} FROM stock_min "
        f"WHERE trade_date BETWEEN ? AND ? AND minute <= TIME '{times[-1]}' "
        f"GROUP BY trade_date, stock_id", [LO, HI]).df()


def tx_close_at(c, times):
    """TX 在各檢查點的 close（≤t 最後一根）。"""
    cols = ", ".join(
        f"arg_max(close, CAST(timestamp AS TIME)) FILTER (WHERE CAST(timestamp AS TIME) <= TIME '{s}') AS \"tx_{s[:5]}\""
        for s in times)
    return c.execute(
        f"SELECT CAST(timestamp AS DATE) d, {cols} FROM ohlcv_1m WHERE symbol='TX' "
        f"AND CAST(timestamp AS DATE) BETWEEN ? AND ? AND CAST(timestamp AS TIME) <= TIME '{times[-1]}' "
        f"GROUP BY 1", [LO, HI]).df()


def main():
    print("Loading...")
    df = load_data_for_orb_est_hl()
    entries = [e for e in build_entries(df) if LO <= e["date"] <= HI]

    with duckdb.connect(DB, read_only=True) as c:
        feat = stock_features(c)
        px = snap_at(c, CKPTS)
        txc = tx_close_at(c, CKPTS)
    g = px.merge(feat, on=["trade_date", "stock_id"], how="inner")
    g = g[g["range_i"] > 0]
    txc["d"] = pd.to_datetime(txc["d"]).dt.date

    # 每日 W-20 thrust @ 各檢查點
    keys = [s[:5] for s in CKPTS]
    dlong = {}
    for d, gd in g.groupby("trade_date"):
        gv = gd.dropna(subset=["trail_val"]).nlargest(20, "trail_val")
        dd = pd.Timestamp(d).date()
        dlong[dd] = {k: wmean_tanh(gv, f"p_{k}", "trail_val") for k in keys}

    txmap = txc.set_index("d")
    rows = []
    for e in entries:
        d = e["date"]
        if d not in dlong or d not in txmap.index:
            continue
        emin = int(e["day"]["min"][e["ei"]]); entry = e["entry"]
        H = e["day"]["High"]; after = H[e["ei"] + 1:]
        if len(after) == 0:
            continue
        maxh = float(after.max())
        reL4 = int(maxh >= e["base"] + 0.977 * e["ema20"])
        px_fx, _, _ = simulate(e["day"], e["ei"], e["base"], e["emahl"], e["ema20"], "fixed", "be")
        rec = {"date": d, "emin": emin, "mfe": maxh - entry, "reL4": reL4,
               "pnl_fixed": px_fx - entry, "entry": entry}
        for k in keys:
            rec[f"dl_{k}"] = dlong[d][k]
            rec[f"cut_{k}"] = float(txmap.loc[d][f"tx_{k}"]) - entry   # 在 t 砍倉的 pnl
        rows.append(rec)
    t = pd.DataFrame(rows)

    def pb(x, y):
        x, y = np.asarray(x, float), np.asarray(y, float)
        return np.nan if x.std() == 0 or y.std() == 0 else float(np.corrcoef(x, y)[0, 1])

    L = ["=" * 76,
         f"因果修正：dci 當『進場後管理』訊號  N={len(t)}（窗內，in-sample，偏多頭）",
         f"進場分鐘 中位={int(t['emin'].median())//60:02d}:{int(t['emin'].median())%60:02d}  "
         "→ dci 不能當進場濾網；以下檢查點皆在多數進場之後（管理用合法）"]

    # ① 各因果檢查點的排序力
    L.append("\n" + "─" * 76)
    L.append("① W-20 thrust 在各檢查點對交易後續的排序力（檢查點越晚越成熟）：")
    L.append(f"{'檢查點':>7} | {'corr(MFE)':>10} {'corr(到L4)':>11} | {'進場已≤此點筆數':>14}")
    for k in keys:
        ncausal = int((t["emin"] <= int(k[:2]) * 60 + int(k[3:5])).sum())
        L.append(f"{k:>7} | {pb(t[f'dl_{k}'], t['mfe']):>+10.3f} {pb(t[f'dl_{k}'], t['reL4']):>+11.3f}"
                 f" | {ncausal:>14}")

    # ② 09:15 管理：dci_long<0 砍倉 vs 全 hold
    L.append("\n" + "─" * 76)
    L.append("② 合法管理動作：09:15 在倉時 dci_long(09:15)<0 → 砍倉(exit@09:15)，否則 hold→fixed-L3")
    weak = t["dl_09:15"] < 0
    t["pnl_mgmt"] = np.where(weak, t["cut_09:15"], t["pnl_fixed"])
    for lab, col in [("全 hold→fixed", "pnl_fixed"), ("弱單09:15砍倉", "pnl_mgmt")]:
        v = t[col]
        L.append(f"  {lab:<16} 總={v.sum():>7.0f}  均={v.mean():>6.1f}  勝率={(v>0).mean():>4.0%}  最差={v.min():>7.1f}")
    L.append(f"  其中被砍 {int(weak.sum())} 筆：fixed 原本總={t.loc[weak,'pnl_fixed'].sum():>6.0f} → 砍倉後={t.loc[weak,'cut_09:15'].sum():>6.0f}"
             f"（差 {t.loc[weak,'cut_09:15'].sum()-t.loc[weak,'pnl_fixed'].sum():+.0f}）")

    # ③ 09:05 佐證（對進場≥09:05 的子集才因果）
    L.append("\n" + "─" * 76)
    causal05 = t[t["emin"] >= 545]
    L.append(f"③ 09:05 佐證：對進場≥09:05 的 {len(causal05)} 筆（09:05 因果），"
             f"corr(dl_09:05, MFE)={pb(causal05['dl_09:05'], causal05['mfe']):+.3f}  "
             f"corr(到L4)={pb(causal05['dl_09:05'], causal05['reL4']):+.3f}")
    L.append("  （樣本極小，僅參考；09:05 訊號本就比 09:15 弱、見 snapshot_sweep）")

    L.append("\n  ⚠ N=44/14、in-sample、偏多頭 → 指示性。結論方向：dci 是進場後管理訊號，非進場濾網。")
    txt = "\n".join(L)
    print(txt)
    (HERE / "results" / "dci_causal_mgmt.txt").write_text(txt + "\n")
    t.to_csv(HERE / "results" / "dci_causal_mgmt_trades.csv", index=False)
    print(f"\n存：{HERE/'results'/'dci_causal_mgmt.txt'}")


if __name__ == "__main__":
    main()
