"""掃所有交易日，計算開盤區間突破（ORB 0857）訊號，依方向 × 成本帶位拆成 6 份 chart-ui 清單。

ORB 訊號定義（與 static/app.js 的 ORB 指標一致）：
- 區間 = 每交易日 08:45–08:57 1分K 的最高 / 最低。
- 突破窗 = 08:58–09:15，逐根檢查收盤：close > 區間高 → 多；close < 區間低 → 空（嚴格）。
- 上、下各取窗內第一根突破；一天最多兩個訊號。

成本帶（VWAP band）：對交易日 D
- vwap_d1 = 前一交易日日盤 VWAP，vwap_d2 = 前二交易日日盤 VWAP
- 帶上緣 = max(vwap_d1, vwap_d2)，帶下緣 = min(vwap_d1, vwap_d2)
- VWAP = 日盤（08:45–13:45）Σ(adj_close×volume)/Σ(volume)

分類在 Panama 調整價空間（換倉不污染）：
- entry_adj = 突破當根 adj_close
- 上：entry_adj > 帶上緣；中：帶下緣 ≤ entry_adj ≤ 帶上緣；下：entry_adj < 帶下緣
note 把帶換回當日原始價顯示，圖上維持原始價可讀。
最早兩個交易日沒有前二日 VWAP → 該訊號丟棄。

觀察性清單：無出場規則、不算 PnL（這是標記/探索工具，不是回測）。

執行：
    uv run python src/chart_ui/build_orb_list.py
"""

from __future__ import annotations

import bisect
import datetime as dt
from collections import defaultdict

import duckdb

from src.chart_ui import paths
from src.chart_ui.list_writer import write_chart_list

SYMBOL = "TX"

RANGE_END = dt.time(8, 57)      # 區間結束（含）
BREAK_START = dt.time(8, 58)    # 突破窗開始

SIDE_LABEL = {"long": "多", "short": "空"}
POS_LABEL = {"up": "上", "mid": "中", "dn": "下"}
# (side, pos) -> (list_id, list_name)
LISTS = {
    (side, pos): (f"orb-{side}-{pos}", f"ORB {SIDE_LABEL[side]}·成本帶{POS_LABEL[pos]}")
    for side in ("long", "short")
    for pos in ("up", "mid", "dn")
}


def _daily_vwap(conn) -> dict[dt.date, float]:
    """各交易日日盤（08:45–13:45）VWAP（adj_close 加權），用於成本帶。"""
    rows = conn.execute(
        "SELECT CAST(timestamp AS DATE) d, "
        "       SUM(adj_close * volume) / SUM(volume) AS vwap "
        "FROM ohlcv_1m WHERE symbol = ? "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "GROUP BY 1 HAVING SUM(volume) > 0 ORDER BY 1",
        [SYMBOL],
    ).fetchall()
    return {d: float(v) for d, v in rows}


def build() -> None:
    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
        vwap = _daily_vwap(conn)
        rows = conn.execute(
            "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, "
            "       high, low, close, adj_close "
            "FROM ohlcv_1m WHERE symbol = ? "
            "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '09:15:00' "
            "ORDER BY d, t",
            [SYMBOL],
        ).fetchall()

    vwap_dates = sorted(vwap)  # 有 VWAP 的交易日（升冪），供二分查前二日

    days: dict[dt.date, list] = defaultdict(list)
    for d, t, h, l, c, ac in rows:
        days[d].append((t, float(h), float(l), float(c), float(ac)))

    # (side, pos) -> items
    buckets: dict[tuple, list[dict]] = {k: [] for k in LISTS}
    n_signal = n_dropped = 0

    for d in sorted(days):
        bars = days[d]
        range_bars = [b for b in bars if b[0] <= RANGE_END]
        if not range_bars:
            continue
        hi = max(b[1] for b in range_bars)
        lo = min(b[2] for b in range_bars)

        # 前二交易日 VWAP（嚴格早於 d）
        i = bisect.bisect_left(vwap_dates, d)
        if i < 2:
            band = None  # 最早兩天無前二日 VWAP
        else:
            v1, v2 = vwap[vwap_dates[i - 1]], vwap[vwap_dates[i - 2]]
            band = (min(v1, v2), max(v1, v2))  # (帶下緣, 帶上緣) in adj space

        long_done = short_done = False
        for t, _h, _l, c, ac in bars:
            if t < BREAK_START:
                continue
            for side, ok in (("long", c > hi), ("short", c < lo)):
                done = long_done if side == "long" else short_done
                if done or not ok:
                    continue
                if side == "long":
                    long_done = True
                else:
                    short_done = True
                n_signal += 1
                if band is None:
                    n_dropped += 1
                    continue
                lo_adj, hi_adj = band
                if ac > hi_adj:
                    pos = "up"
                elif ac < lo_adj:
                    pos = "dn"
                else:
                    pos = "mid"
                # 帶換回當日原始價顯示（adjustment = adj_close - close）
                adj = ac - c
                band_lo_raw, band_hi_raw = lo_adj - adj, hi_adj - adj
                ref = f"區間高 {hi:.0f}" if side == "long" else f"區間低 {lo:.0f}"
                note = (f"{SIDE_LABEL[side]}突破 {c:.0f}（{ref}）"
                        f"｜成本帶 {band_lo_raw:.0f}–{band_hi_raw:.0f}｜帶位:{POS_LABEL[pos]}")
                buckets[(side, pos)].append(
                    {"time": f"{d} {t}", "side": side, "entry": c, "note": note}
                )
            if long_done and short_done:
                break

    total = 0
    for (side, pos), items in buckets.items():
        items.sort(key=lambda x: x["time"], reverse=True)  # 由近到遠
        list_id, list_name = LISTS[(side, pos)]
        # entry_marker=False：ORB 指標本身已標突破箭頭+突破價，避免重複
        path = write_chart_list(list_id, items, name=list_name, entry_marker=False)
        n_days = len({it["time"][:10] for it in items})
        total += len(items)
        print(f"✅ {list_id:14s} {len(items):4d} 訊號 / {n_days} 日  → {path.name}")

    print(f"\n共 {n_signal} 個 ORB 訊號，分到 6 桶 {total} 筆"
          f"（丟棄 {n_dropped} 筆：最早兩日無前二日 VWAP），掃 {len(days)} 個交易日")


if __name__ == "__main__":
    build()
