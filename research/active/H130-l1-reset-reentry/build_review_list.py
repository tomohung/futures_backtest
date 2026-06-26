"""H130 覆盤清單 — 把 L1-reset 同相位再進場（reentry_idx≥2）標到 chart-ui 供肉眼複盤。

純複盤用（H130 GATE=Reject，非交易訊號）。重用 explore.py 的 causal 偵測器，逐日掃 reset 再進場，
每筆帶 錨/L4 目標 levels + 碰 L3/L4/L5 註記。點清單即跳當日進場根（搭配 l2_pullback 指標可同時看首次）。

用法：uv run python research/active/H130-l1-reset-reentry/build_review_list.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).parent))
from explore import _day_bars, detect_l1reset, forward   # noqa: E402

from src.chart_ui import paths   # noqa: E402
from src.chart_ui.list_writer import write_chart_list   # noqa: E402
from src.chart_ui.services.daystats import SYMBOL, _ema20_range   # noqa: E402
from src.chart_ui.services.l2_pullback import COEF   # noqa: E402


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def build():
    items = []
    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
        days = [r[0] for r in conn.execute(
            "SELECT DISTINCT CAST(timestamp AS DATE) d FROM ohlcv_1m WHERE symbol=? "
            "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' ORDER BY d",
            [SYMBOL]).fetchall()]
        for d in days:
            ema = _ema20_range(conn, d)
            if not ema:
                continue
            bars = _day_bars(conn, d)
            if len(bars) < 5:
                continue
            ents = detect_l1reset(bars, ema)
            L4d = COEF["L4"] * ema
            for e in ents:
                if e["reentry_idx"] < 2:        # 只收 L1-reset 再進場
                    continue
                up = e["side"] == "long"
                anchor = e["anchor"]
                _mfe, _mae, reach = forward(e["entry_i"], e["side"], anchor, ema, bars)
                rs = "".join(k[-1] for k in ("L3", "L4", "L5") if reach[k]) or "—"
                tgt = anchor + L4d if up else anchor - L4d
                items.append({
                    "time": f"{d} {hhmm(e['entry_min'])}:00",
                    "side": e["side"],
                    "entry": e["entry"],
                    "result": "Win" if reach["L4"] else "Open",
                    "return_pct": None,
                    "levels": [
                        {"price": round(anchor, 1), "label": "錨/停損"},
                        {"price": round(tgt, 1), "label": "目標L4"},
                    ],
                    "note": (f"{'多' if up else '空'}｜第{e['reentry_idx']}次同相位(L1-reset)"
                             f"｜錨{int(anchor)}｜進場{int(e['entry'])}｜碰{rs}"),
                })
    return items


def main():
    items = build()
    path = write_chart_list(
        "l1-reset-review", items, name="L1-reset 同相位再進場·複盤(H130)",
        desc="H130(GATE=Reject,非訊號)：同相位內 進場→回L1線reset→重新碰L2→拉回站回5MA 再進場。"
             "錨/L4 為視覺參考。碰=該筆進場後碰到的最深關卡。")
    wins = sum(1 for it in items if it["result"] == "Win")
    print(f"{len(items)} 筆 → {path}")
    print(f"碰 L4 比率 {round(100*wins/len(items),1)}%（{wins}）" if items else "無資料")


if __name__ == "__main__":
    main()
