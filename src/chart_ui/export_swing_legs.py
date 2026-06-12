"""匯出全歷史 L3 波段（swing legs）到 CSV。

重用 services/swing_legs 的純函式（zigzag_legs / L2、L3 係數）與 daystats 的 EMA20，
單一唯讀連線跑完所有日盤交易日，每段一列。

用法：
    uv run python src/chart_ui/export_swing_legs.py [--out output/l3_swing_legs.csv]
"""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

import duckdb

from src.chart_ui import paths
from src.chart_ui.services.daystats import SYMBOL, _ema20_range
from src.chart_ui.services.swing_legs import (
    L2_COEF,
    L3_COEF,
    NOON_MIN,
    _day_bars,
    _min_to_hhmm,
    zigzag_legs,
)

COLUMNS = [
    "日期", "方向", "起點時間", "起點價", "終點時間", "終點價",
    "點數", "倍數", "持續分鐘", "當日L3距離", "當日EMA20振幅",
]


def _rows_for_day(conn, sel: date) -> list[dict]:
    ema20 = _ema20_range(conn, sel)
    if not ema20:
        return []
    l2_dist = L2_COEF * ema20
    l3_dist = L3_COEF * ema20
    bars = _day_bars(conn, sel)
    raw = zigzag_legs(bars, threshold=l2_dist)
    rows = []
    for lg in raw:
        if lg["start_min"] >= NOON_MIN:
            continue
        amp_abs = abs(lg["end_price"] - lg["start_price"])
        if amp_abs < l3_dist:
            continue
        rows.append({
            "日期": sel.isoformat(),
            "方向": "多" if lg["dir"] == "up" else "空",
            "起點時間": _min_to_hhmm(lg["start_min"]),
            "起點價": round(lg["start_price"]),
            "終點時間": _min_to_hhmm(lg["end_min"]),
            "終點價": round(lg["end_price"]),
            "點數": round(lg["end_price"] - lg["start_price"]),
            "倍數": round(amp_abs / l3_dist, 1),
            "持續分鐘": lg["end_min"] - lg["start_min"],
            "當日L3距離": round(l3_dist, 1),
            "當日EMA20振幅": round(ema20, 1),
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output/l3_swing_legs.csv")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
        days = [r[0] for r in conn.execute(
            "SELECT DISTINCT CAST(timestamp AS DATE) d FROM ohlcv_1m "
            "WHERE symbol = ? ORDER BY d", [SYMBOL]).fetchall()]
        all_rows = []
        for d in days:
            all_rows.extend(_rows_for_day(conn, d))

    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(all_rows)

    print(f"{len(all_rows)} legs across {len(days)} days → {out}")


if __name__ == "__main__":
    main()
