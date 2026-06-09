"""交易效果（B）：dci_long@09:15 能否調節 H095 出場階梯？（Phase-1，指示性）

重用 phase2_path_backtest 的 build_entries / simulate（乾淨 EstHL long-only 進場 + L1/L2/L3 階梯）。
dci 從 dci_universe_panel.csv 按日期 join（不重算盤中）。
  dci_long  = W-20_09:15（集中大型股 thrust，多方訊號，進場窗結束即可得）
  dci_short = z(−W-100_09:30) + z(−B_09:30)（空方廣度合成，對 long 單為逆風）

兩問：
  ① dci_long 能否把『實際交易的後續走多遠』排序？(corr/分組：到L3/L4率、MFE、baseline pnl)
  ② 一個簡單調節規則（高 dci_long→trail 放跑博 L4；低→fixed 收 L3）vs 不調節，窗內總損益。

硬限制：stock_min 只有 2025-06~2026-02 → 窗內僅 **44 筆**；in-sample；區間偏多頭。純指示性。
用法：uv run python research/active/H095-reach-ladder-exit/dci_exit_modulate.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from phase2_path_backtest import build_entries, simulate, C   # noqa: E402
from src.backtest.runner import load_data_for_orb_est_hl       # noqa: E402

LO, HI = date(2025, 6, 2), date(2026, 2, 26)
PANEL = HERE / "results" / "dci_universe_panel.csv"


def pb(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 5 or x.std() == 0 or y.std() == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def main():
    print("Loading...")
    df = load_data_for_orb_est_hl()
    entries = [e for e in build_entries(df) if LO <= e["date"] <= HI]

    p = pd.read_csv(PANEL)
    p["d"] = pd.to_datetime(p["trade_date"]).dt.date
    # 空方合成 z（用 181 天分佈當標準化基準，in-sample）
    s_thr = -p["W-100_09:30"]; s_B = -p["B_09:30"]
    p["dci_short"] = (s_thr - s_thr.mean()) / s_thr.std() + (s_B - s_B.mean()) / s_B.std()
    pl = p.set_index("d")

    rows = []
    for e in entries:
        d = e["date"]
        if d not in pl.index:
            continue
        r = pl.loc[d]
        H = e["day"]["High"]; ei = e["ei"]; entry = e["entry"]; base = e["base"]; ema = e["ema20"]
        after = H[ei + 1:]
        if len(after) == 0:
            continue
        mfe = float(after.max() - entry)                  # 最大有利擺幅（點）
        maxh = float(after.max())
        reachedL3 = int(maxh >= base + C["L3"] * ema)
        reachedL4 = int(maxh >= base + 0.977 * ema)
        px_fx, _, _ = simulate(e["day"], ei, base, e["emahl"], ema, "fixed", "be")
        px_tr, _, _ = simulate(e["day"], ei, base, e["emahl"], ema, "5ma", "be")
        rows.append({
            "date": d, "dci_long": float(r["W-20_09:15"]), "dci_short": float(r["dci_short"]),
            "mfe": mfe, "reL3": reachedL3, "reL4": reachedL4,
            "pnl_fixed": px_fx - entry, "pnl_trail": px_tr - entry,
        })
    t = pd.DataFrame(rows)
    n = len(t)

    L = ["=" * 76,
         f"dci_long 調節 H095 出場（指示性）  窗內 N={n}（2025-06~2026-02，in-sample）",
         "baseline 出場：fixed(收L3) 與 5ma trail(博延伸)；MFE=進場後最大有利擺幅(點)"]

    # ① 排序力
    L.append("\n" + "─" * 76)
    L.append("① dci_long@09:15 對實際交易後續的排序力：")
    L.append(f"  corr(dci_long, MFE點)      = {pb(t['dci_long'], t['mfe']):+.3f}")
    L.append(f"  corr(dci_long, 到L4)       = {pb(t['dci_long'], t['reL4']):+.3f}")
    L.append(f"  corr(dci_long, trail pnl)  = {pb(t['dci_long'], t['pnl_trail']):+.3f}")
    med = t["dci_long"].median()
    for lab, sub in [("dci_long 高(>中位)", t[t["dci_long"] > med]),
                     ("dci_long 低(≤中位)", t[t["dci_long"] <= med])]:
        L.append(f"  {lab:<16} N={len(sub):>2}  到L3={sub['reL3'].mean():.0%}  到L4={sub['reL4'].mean():.0%}  "
                 f"MFE均={sub['mfe'].mean():>5.0f}  trail均pnl={sub['pnl_trail'].mean():>6.1f}  "
                 f"fixed均pnl={sub['pnl_fixed'].mean():>6.1f}")

    # ② 調節規則 vs 不調節
    L.append("\n" + "─" * 76)
    L.append("② 調節出場（高 dci_long→trail 放跑、低→fixed 收 L3）vs 全 fixed / 全 trail：")
    t["pnl_mod"] = np.where(t["dci_long"] > med, t["pnl_trail"], t["pnl_fixed"])
    for lab, col in [("全 fixed", "pnl_fixed"), ("全 trail(5ma)", "pnl_trail"),
                     ("調節(dci_long)", "pnl_mod")]:
        v = t[col]
        L.append(f"  {lab:<16} 總={v.sum():>7.0f}  均={v.mean():>6.1f}  勝率={(v>0).mean():>4.0%}  "
                 f"最差={v.min():>7.1f}")
    # 對照：反向規則（若反向更好＝訊號方向錯）
    t["pnl_rev"] = np.where(t["dci_long"] > med, t["pnl_fixed"], t["pnl_trail"])
    L.append(f"  {'反向對照':<16} 總={t['pnl_rev'].sum():>7.0f}  均={t['pnl_rev'].mean():>6.1f}"
             f"  （若反向>調節 ⇒ 方向錯）")

    # 空方逆風：dci_short 高時 long 單表現
    L.append("\n" + "─" * 76)
    L.append("③ 空方逆風檢查：dci_short@09:30 高(>中位) 時 long 單 baseline 表現：")
    ms = t["dci_short"].median()
    for lab, sub in [("dci_short 高", t[t["dci_short"] > ms]), ("dci_short 低", t[t["dci_short"] <= ms])]:
        L.append(f"  {lab:<12} N={len(sub):>2}  到L4={sub['reL4'].mean():.0%}  "
                 f"trail均pnl={sub['pnl_trail'].mean():>6.1f}")

    L.append("\n  ⚠ N=44、in-sample、區間偏多頭 → 指示性，不可當 confirmed；需擴樣本+OOS。")
    txt = "\n".join(L)
    print(txt)
    (HERE / "results" / "dci_exit_modulate.txt").write_text(txt + "\n")
    t.to_csv(HERE / "results" / "dci_exit_modulate_trades.csv", index=False)
    print(f"\n存：{HERE/'results'/'dci_exit_modulate.txt'}")


if __name__ == "__main__":
    main()
