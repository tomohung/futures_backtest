"""H119 Phase 1（修正版）：突破當下強度 → ORB 多突破續走/假突破 分佈。

修正：強度讀「突破那一刻」CDF/NYF 延伸；突破前已達 L3 的事件已排除（見 h119_lib）。
兩個 OR 窗：09:30 窗（突破09:30-10:00）與 08:57 早窗（突破08:58-09:15）。
核心對照：高強度(≥θ) vs 低強度(<θ) vs 無濾網。
"""
from __future__ import annotations

import os
import sys

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from h119_lib import DB, build_events  # noqa: E402

CFGS = [("09:30 窗", "09:30:00", "10:00:00"),
        ("08:57 早窗", "08:57:00", "09:15:00")]


def grp(df):
    if len(df) == 0:
        return "N=0"
    return (f"N={len(df):>4} L3={df['reach_L3'].mean():.0%} L4={df['reach_L4'].mean():.0%} "
            f"假突破={df['revfail'].mean():.0%} 均損益%={df['pnl_pct'].mean():+.3f}")


def main():
    out = []
    def p(s=""):
        out.append(s); print(s)

    with duckdb.connect(DB, read_only=True) as conn:
        for sym in ["CDF", "NYF"]:
            for lab, oe, ec in CFGS:
                ev = build_events(conn, sym, oe, ec)
                p(f"\n############ {sym}　{lab}　多突破 N={len(ev)}（已排除突破前達L3）############")
                p(f"  無濾網（全突破）: {grp(ev)}")
                for th in [0.10, 0.16, 0.20]:
                    hi = ev[ev["strength"] >= th]; lo = ev[ev["strength"] < th]
                    p(f"   θ={th}: 高強度 {grp(hi)}")
                    p(f"          低強度 {grp(lo)}")

        # 跨 regime：CDF 09:30 窗 θ=0.16 逐年
        p(f"\n############ 跨 regime：CDF 09:30 窗 θ=0.16 逐年 ############")
        ev = build_events(conn, "CDF", "09:30:00", "10:00:00")
        for yr, g in ev.groupby("yr"):
            hi = g[g["strength"] >= 0.16]; lo = g[g["strength"] < 0.16]
            if len(hi) >= 8 and len(lo) >= 8:
                p(f"  {yr}: 高 {grp(hi)}")
                p(f"        低 {grp(lo)}")

    with open("research/active/H119-orb-strength-filter/results/distribution_raw.txt", "w") as f:
        f.write("\n".join(out))
    print("\n→ 已寫 results/distribution_raw.txt")


if __name__ == "__main__":
    main()
