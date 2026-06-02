"""掃所有交易日，計算開盤區間突破（ORB 0857）訊號，輸出 chart-ui 清單。

定義（與 static/app.js 的 ORB 指標一致）：
- 區間 = 每交易日 08:45–08:57 1分K 的最高 / 最低。
- 突破窗 = 08:58–09:15，逐根檢查收盤：close > 區間高 → 多；close < 區間低 → 空（嚴格）。
- 上、下各取窗內第一根突破；一天最多兩個訊號。

觀察性清單：無出場規則、不算 PnL（這是標記/探索工具，不是回測）。

執行：
    uv run python src/chart_ui/build_orb_list.py
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

import duckdb

from src.chart_ui import paths
from src.chart_ui.list_writer import write_chart_list

SYMBOL = "TX"
LIST_ID = "orb-0857"
LIST_NAME = "ORB 0857 突破日"

RANGE_END = dt.time(8, 57)      # 區間結束（含）
BREAK_START = dt.time(8, 58)    # 突破窗開始


def build() -> None:
    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
        rows = conn.execute(
            "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, high, low, close "
            "FROM ohlcv_1m WHERE symbol = ? "
            "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '09:15:00' "
            "ORDER BY d, t",
            [SYMBOL],
        ).fetchall()

    days: dict[dt.date, list] = defaultdict(list)
    for d, t, h, l, c in rows:
        days[d].append((t, float(h), float(l), float(c)))

    items: list[dict] = []
    n_long = n_short = 0
    for d in sorted(days):
        bars = days[d]
        range_bars = [b for b in bars if b[0] <= RANGE_END]
        if not range_bars:
            continue
        hi = max(b[1] for b in range_bars)
        lo = min(b[2] for b in range_bars)
        long_done = short_done = False
        for t, _h, _l, c in bars:
            if t < BREAK_START:
                continue
            if not long_done and c > hi:
                # entry = 突破當根收盤（確認突破的價位）；note 附區間高供對照
                items.append({"time": f"{d} {t}", "side": "long", "entry": c, "note": f"多突破 {c:.0f}（區間高 {hi:.0f}）"})
                long_done = True
                n_long += 1
            if not short_done and c < lo:
                items.append({"time": f"{d} {t}", "side": "short", "entry": c, "note": f"空突破 {c:.0f}（區間低 {lo:.0f}）"})
                short_done = True
                n_short += 1
            if long_done and short_done:
                break

    items.sort(key=lambda x: x["time"], reverse=True)   # 由近到遠（與『所有交易日』一致）
    # entry_marker=False：不畫 generic「進」箭頭（ORB 指標本身已標突破箭頭+突破價，避免重複）
    path = write_chart_list(LIST_ID, items, name=LIST_NAME, entry_marker=False)
    n_days = len({it["time"][:10] for it in items})
    print(f"✅ {path}")
    print(f"   {len(items)} 訊號（多 {n_long} / 空 {n_short}）涵蓋 {n_days} 個交易日，共掃 {len(days)} 日")


if __name__ == "__main__":
    build()
