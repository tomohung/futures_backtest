"""把 H103 主訊號（跳空下方+成本遠上方≥1.0 做多）日子輸出成 chart-ui 清單，供覆盤。

進場=08:45 開盤多、目標0.7×ema20、停損0.5×ema20、13:30 收盤平倉、成本3點。
清單寫到 data/chart_lists/h103-gapdown-far.json。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "research" / "active" / "H103-gapdown-cost-revert"))

import backtest as bt
from src.chart_ui.list_writer import write_chart_list

T, S, COST = 0.7, 0.5, 3.0


def run_detail(g, ema20):
    entry = float(g["open"].iloc[0])
    post = g[g["t"] <= bt.EXIT_T]
    tp, sl = entry + T * ema20, entry - S * ema20
    exit_px, why = None, "收盤"
    for _, b in post.iterrows():
        if b["low"] <= sl:
            exit_px, why = sl, "停損"; break
        if b["high"] >= tp:
            exit_px, why = tp, "停利"; break
    if exit_px is None:
        exit_px = float(post["close"].iloc[-1])
    pnl = (exit_px - entry) - COST
    return entry, tp, exit_px, why, pnl


def main():
    daily = bt.pd.read_csv(bt.DAILY_CSV, parse_dates=[0], index_col=0)
    q = daily[(daily["n_above"] == 2) & (daily["up_clear_norm"] >= 1.0)].sort_index(ascending=False)
    intr = bt.load_intraday([d.date() for d in q.index])

    items = []
    for d, r in q.iterrows():
        g = intr[d.date()]
        entry, tp, exit_px, why, pnl = run_detail(g, r["ema20"])
        cost = min(r["vwap_last"], r["vwap_prev"])
        items.append({
            "time": f"{d.date()} 08:45:00",
            "side": "long",
            "entry": round(entry, 1),
            "pnl_pts": round(float(pnl), 1),
            "result": "Win" if pnl > 0 else "Loss",
            "note": (f"開低{entry:.0f}｜最近成本{cost:.0f}(+{r['up_clear_norm']:.2f}ema)｜"
                     f"目標{tp:.0f}｜{why}{pnl:+.0f}點"),
        })

    path = write_chart_list(
        "h103-gapdown-far", items,
        name="H103 跳空下方遠(做多覆盤)",
        entry_marker=True,
        desc="open跌破昨/前日VWAP兩者、最近成本≥1×ema20上方→開盤做多。覆盤用。",
    )
    print(f"[saved] {path}  ({len(items)} 天)")


if __name__ == "__main__":
    main()
