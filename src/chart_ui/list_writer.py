"""輸出標準清單 JSON 到 data/chart_lists/，供 chart-ui dropdown 載入。

回測/探索腳本範例：
    from src.chart_ui.list_writer import write_chart_list_from_backtesting
    stats = bt.run()
    write_chart_list_from_backtesting(stats._trades, "orb-2025", name="ORB 2025")
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pandas as pd

from src.chart_ui import paths


def _summary(items: list[dict]) -> dict:
    pnls = [it["pnl_pts"] for it in items if it.get("pnl_pts") is not None]
    wins = [p for p in pnls if p > 0]
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = -sum(p for p in pnls if p < 0)
    return {
        "trades": len(items),
        "win_rate": round(len(wins) / len(pnls), 4) if pnls else None,
        "pnl_pts": round(sum(pnls), 2) if pnls else None,
        "pf": round(gross_win / gross_loss, 2) if gross_loss else None,
    }


def write_chart_list(list_id: str, items: list[dict], *, out_dir: Path | None = None,
                     name: str | None = None, summary: dict | None = None, **meta) -> Path:
    """寫一份清單。回傳檔案路徑。atomic write。"""
    out_dir = Path(out_dir) if out_dir else paths.CHART_LISTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"name": name or list_id, **meta, "items": items}
    payload["summary"] = summary if summary is not None else _summary(items)
    path = out_dir / f"{list_id}.json"
    fd, tmp = tempfile.mkstemp(dir=out_dir, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, path)
    return path


def write_chart_list_from_backtesting(trades: pd.DataFrame, list_id: str, **kwargs) -> Path:
    """吃 Backtesting.py 的 _trades DataFrame，map 成標準 items。"""
    items = []
    for r in trades.itertuples(index=False):
        d = r._asdict()
        items.append({
            "time": str(d["EntryTime"]),
            "exit_time": str(d["ExitTime"]),
            "side": "long" if d["Size"] > 0 else "short",
            "entry": float(d["EntryPrice"]),
            "exit": float(d["ExitPrice"]),
            "pnl_pts": float(d["PnL"]),
            "return_pct": float(d["ReturnPct"]),
            "result": "Win" if d["PnL"] > 0 else "Loss",
            "note": "" if d.get("Tag") in (None, "") or pd.isna(d.get("Tag")) else str(d["Tag"]),
        })
    return write_chart_list(list_id, items, **kwargs)


def write_chart_list_from_csv(csv_path: str | Path, mapping: dict, list_id: str, **kwargs) -> Path:
    """從自訂 CSV 用欄位對照轉成標準 items。

    mapping 例（選擇權）：
        {"time": "touch_time_full", "exit_time": "exit_time", "side": "side",
         "pnl_pts": "pnl", "return_pct": "cr_pct"}
    其中值為 CSV 欄名。time 欄需為完整 'YYYY-MM-DD HH:MM:SS'（呼叫端先備好）。
    """
    df = pd.read_csv(csv_path)
    items = []
    for r in df.itertuples(index=False):
        d = r._asdict()
        item = {}
        for std_key, csv_col in mapping.items():
            if csv_col in d:
                val = d[csv_col]
                item[std_key] = None if pd.isna(val) else (float(val) if std_key in ("entry", "exit", "pnl_pts", "return_pct") else str(val))
        items.append(item)
    return write_chart_list(list_id, items, **kwargs)
