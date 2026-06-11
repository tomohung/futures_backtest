"""H119：產 chart-ui 清單供視覺 review（修正版：突破當下強度 + L3-before 排除）。

兩個 OR 窗 × 強/弱對照，共 4 份（皆倒序，由 list_writer 預設處理）：
  09:30 窗（OR 08:45–09:30、突破 09:30–10:00）：強(CDF延伸@突破≥0.16) / 弱
  08:57 早窗（OR 08:45–08:57、突破 08:58–09:15）：強 / 弱
每筆帶進出場 + L3/L4/OR 關卡線 + 突破當下 CDF 強度 note。
"""
from __future__ import annotations

import os
import sys

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from h119_lib import DB, build_events  # noqa: E402
from src.chart_ui.list_writer import write_chart_list  # noqa: E402

TH = 0.16


def items_from(ev):
    out = []
    for d, r in ev.iterrows():
        ds = str(d)[:10]
        win = r["exit"] > r["entry"]
        out.append({
            "time": f"{ds} {r['bo_time']}", "exit_time": f"{ds} {r['exit_time']}",
            "side": "long", "entry": round(float(r["entry"]), 1),
            "exit": round(float(r["exit"]), 1),
            "pnl_pts": round(float(r["exit"]) - float(r["entry"]), 1),
            "return_pct": round(float(r["pnl_pct"]), 3),
            "result": "Win" if win else "Loss",
            "strength": round(float(r["strength"]), 3),
            "levels": [
                {"price": float(r["l3"]), "label": "L3"},
                {"price": float(r["l4"]), "label": "L4"},
                {"price": round(float(r["or_low"]), 1), "label": "OR低"},
            ],
            "note": f"CDF延伸@突破 {r['strength']:+.2f}｜OR低 {r['or_low']:.0f}｜"
                    f"{'Win' if win else 'Loss'}",
        })
    return out


def main():
    cfgs = [("0930", "09:30 窗(突破09:30-10:00)", "09:30:00", "10:00:00"),
            ("0857", "08:57 早窗(突破08:58-09:15)", "08:57:00", "09:15:00")]
    with duckdb.connect(DB, read_only=True) as conn:
        for tag, label, oe, ec in cfgs:
            ev = build_events(conn, "CDF", oe, ec)
            strong = ev[ev["strength"] >= TH]
            weak = ev[ev["strength"] < TH]
            ps = write_chart_list(f"h119-orb-{tag}-strong", items_from(strong),
                                  name=f"H119 {label} CDF≥{TH} 放行")
            pw = write_chart_list(f"h119-orb-{tag}-weak", items_from(weak),
                                  name=f"H119 {label} CDF<{TH} 對照")
            print(f"{label}: 放行 {len(strong)} / 對照 {len(weak)}")
            print(f"   {ps.name} / {pw.name}")


if __name__ == "__main__":
    main()
