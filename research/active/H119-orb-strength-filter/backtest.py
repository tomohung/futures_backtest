"""H119 Phase 2（修正版）：有濾網 vs 無濾網 ORB 多單回測。

修正：突破當下 CDF 強度當閘；突破前已達 L3 排除（見 h119_lib）。
bracket：SL=entry×(1−0.5%)、TP=entry+SL距離×1.5、13:30 強平（沿用 orb.py）。
主窗 09:30；附 08:57 早窗對照。績效用損益%。重點：勝率/EV/Sharpe/maxDD/最大連敗/成本。
"""
from __future__ import annotations

import os
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from h119_lib import DB, build_events  # noqa: E402


def max_consec_loss(pnl) -> int:
    c = mx = 0
    for v in pnl:
        c = c + 1 if v < 0 else 0
        mx = max(mx, c)
    return mx


def st(pnl: pd.Series, cost=0.0) -> str:
    r = pnl - cost; n = len(r)
    if n == 0:
        return "N=0"
    eq = r.cumsum(); dd = (eq.cummax() - eq).max()
    sh = r.mean() / r.std() if r.std() > 0 else np.nan
    return (f"N={n:>4} 勝率={(r>0).mean():.0%} 均%={r.mean():+.3f} 總%={r.sum():+.1f} "
            f"Sharpe={sh:+.2f} maxDD%={dd:.1f} 最大連敗={max_consec_loss(r)}")


def main():
    out = []
    def p(s=""):
        out.append(s); print(s)
    TH = 0.16

    with duckdb.connect(DB, read_only=True) as conn:
        # ---- 主窗 09:30 ----
        ev = build_events(conn, "CDF", "09:30:00", "10:00:00")
        pnl = ev["pnl_pct"]; sig = ev[ev["strength"] >= TH]["pnl_pct"]
        p("=== H119 Phase 2（修正版）：CDF 突破當下強度閘，OR_end=09:30 ===")
        p(f"突破日 N={len(ev)}（已排除突破前達 L3）")
        p(f"\n無濾網（全突破）: {st(pnl)}")
        p(f"\n=== θ 敏感度 ===")
        for th in [0.10, 0.16, 0.20]:
            p(f"  θ={th}: 有濾網 {st(ev[ev['strength']>=th]['pnl_pct'])}")
            p(f"         低強度 {st(ev[ev['strength']<th]['pnl_pct'])}")
        p(f"\n=== IS(2021–24)/OOS(2025–26)，有濾網 θ≥{TH} vs 無濾網 ===")
        for lab, sub in [("有濾網", ev[ev["strength"] >= TH]), ("無濾網", ev)]:
            p(f"  {lab} IS : {st(sub[sub['yr']<=2024]['pnl_pct'])}")
            p(f"  {lab} OOS: {st(sub[sub['yr']>=2025]['pnl_pct'])}")
        p(f"\n=== 逐年 walk-forward：有濾網 θ≥{TH} vs 無濾網 ===")
        sigf = ev[ev["strength"] >= TH]
        for yr in sorted(ev["yr"].unique()):
            p(f"  {yr}: 有濾網 {st(sigf[sigf['yr']==yr]['pnl_pct'])}")
            p(f"        無濾網 {st(ev[ev['yr']==yr]['pnl_pct'])}")
        p(f"\n=== 成本敏感度（扣每趟 round-trip 成本%）===")
        for c in [0.0, 0.01, 0.02, 0.03]:
            p(f"  成本{c}%: 有濾網 {st(sig, c)}")
            p(f"           無濾網 {st(pnl, c)}")

        # ---- 早窗 08:57 對照 ----
        ev2 = build_events(conn, "CDF", "08:57:00", "09:15:00")
        p(f"\n\n=== 對照：08:57 早窗（突破08:58-09:15）θ≥{TH} ===")
        p(f"  無濾網 {st(ev2['pnl_pct'])}")
        p(f"  有濾網 {st(ev2[ev2['strength']>=TH]['pnl_pct'])}")
        p(f"  低強度 {st(ev2[ev2['strength']<TH]['pnl_pct'])}")

    with open("research/active/H119-orb-strength-filter/results/backtest_raw.txt", "w") as f:
        f.write("\n".join(out))
    print("\n→ 已寫 results/backtest_raw.txt")


if __name__ == "__main__":
    main()
