"""產生 L2 拉回續攻進場清單（拉回站回 5MA 續攻 L2→L3）給 chart-ui dropdown。

重用 services/l2_pullback 的 detect_day + simulate（causal，與主圖指標同源），逐交易日掃進場，
每筆帶 stop/target 兩條 levels（點選清單項時主圖即畫停損/目標水平線 + 進出場 marker）。

用法：
    uv run python src/chart_ui/build_l2_pullback_list.py            # 全部
    uv run python src/chart_ui/build_l2_pullback_list.py --side short  # 只空單
    uv run python src/chart_ui/build_l2_pullback_list.py --cutoff 690  # 只 ≤11:30 進場
"""
from __future__ import annotations

import argparse
from datetime import date

import duckdb

from src.chart_ui import paths
from src.chart_ui.list_writer import write_chart_list
from src.chart_ui.services.daystats import SYMBOL, _ema20_range
from src.chart_ui.services.l2_pullback import (
    MIN_DEPTH_FRAC,
    _day_bars,
    _min_to_hhmm,
    detect_day,
    simulate,
)


def build(side: str | None, cutoff: int | None, result: str | None = None):
    items = []
    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
        days = [r[0] for r in conn.execute(
            "SELECT DISTINCT CAST(timestamp AS DATE) d FROM ohlcv_1m "
            "WHERE symbol = ? ORDER BY d", [SYMBOL]).fetchall()]
        for d in days:
            ema20 = _ema20_range(conn, d)
            if not ema20:
                continue
            bars = _day_bars(conn, d)
            if len(bars) < 5:
                continue
            entries, _dist = detect_day(bars, ema20)
            for e in entries:
                if side and e["side"] != side:
                    continue
                if cutoff and e["entry_min"] >= cutoff:
                    continue
                if e["depth_frac"] < MIN_DEPTH_FRAC:   # 濾掉淺拉回（與策略一致）
                    continue
                exit_min, exit_px, pnl, res = simulate(e, bars)
                if result and res != result:
                    continue
                items.append({
                    "time": f"{d} {_min_to_hhmm(e['entry_min'])}:00",
                    "exit_time": f"{d} {_min_to_hhmm(exit_min)}:00",
                    "side": e["side"],
                    "entry": e["entry"],
                    "exit": exit_px,
                    "pnl_pts": pnl,
                    "return_pct": round(pnl / e["entry"] * 100, 3),
                    "result": res,
                    "levels": [
                        {"price": e["stop"], "label": "停損"},
                        {"price": e["target"], "label": "目標L3"},
                    ],
                    "note": (f"{'多' if e['side']=='long' else '空'}"
                             f"｜深度{round(e['depth_frac'],2):g}L2｜錨{int(e['anchor'])}｜拉回{int(e['pb_ext'])}"
                             f"｜風險{e['risk']}點｜目標L3 {int(e['target'])}"),
                })
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--side", choices=["long", "short"], default=None)
    ap.add_argument("--result", choices=["Win", "Loss", "Open"], default=None,
                    help="只收特定結果（Loss=敗單覆盤）")
    ap.add_argument("--cutoff", type=int, default=720,
                    help="只收此分鐘前進場（預設720=12:00；825=全時段）")
    ap.add_argument("--id", default=None)
    args = ap.parse_args()

    items = build(args.side, args.cutoff, args.result)
    # 預設 cutoff=720(12:00) 視為標準，不加後綴；非預設才標 -le{cutoff}
    cut_suffix = f"-le{args.cutoff}" if (args.cutoff and args.cutoff != 720) else ""
    res_suffix = f"-{args.result.lower()}" if args.result else ""
    suffix = (f"-{args.side}" if args.side else "") + res_suffix + cut_suffix
    list_id = args.id or f"l2-pullback{suffix}"
    cut_name = f"（≤{_min_to_hhmm(args.cutoff)}）" if (args.cutoff and args.cutoff != 720) else ""
    res_name = {"Win": "（勝）", "Loss": "（敗）", "Open": "（收盤）"}.get(args.result, "")
    name = "L2拉回續攻" + (f"（{args.side}）" if args.side else "") + res_name + cut_name
    path = write_chart_list(list_id, items, name=name,
                            desc="L2確立→拉回→收盤站回5MA進場；停損=拉回極值往錨靠0.75，目標L3。causal 行情參考指標（前身 H120）。")
    wins = sum(1 for it in items if it["result"] == "Win")
    print(f"{len(items)} 筆 → {path}")
    print(f"勝率 {round(100*wins/len(items),1)}%（Win={wins}）" if items else "無資料")


if __name__ == "__main__":
    main()
