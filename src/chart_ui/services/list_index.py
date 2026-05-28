"""列舉 data/chart_lists/*.json，並注入內建『所有交易日』虛擬清單。"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

ALL_DAYS_ID = "__all_days__"
ALL_DAYS_NAME = "所有交易日"


def _trading_days_desc(db_path: Path) -> list[str]:
    with duckdb.connect(str(db_path), read_only=True) as conn:
        rows = conn.execute(
            "SELECT DISTINCT CAST(timestamp AS DATE) d FROM ohlcv_1m "
            "WHERE CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
            "ORDER BY d DESC"
        ).fetchall()
    return [r[0].isoformat() for r in rows]


def _all_days_payload(db_path: Path) -> dict:
    days = _trading_days_desc(db_path)
    return {
        "id": ALL_DAYS_ID,
        "name": ALL_DAYS_NAME,
        "items": [{"time": f"{d} 08:45:00"} for d in days],
    }


def list_lists(chart_lists_dir: Path, db_path: Path) -> list[dict]:
    """回傳 dropdown 用清單：內建『所有交易日』排第一，其後為檔案清單。"""
    out: list[dict] = []
    days = _trading_days_desc(db_path)
    out.append({"id": ALL_DAYS_ID, "name": ALL_DAYS_NAME, "count": len(days), "summary": None})

    if chart_lists_dir.is_dir():
        for path in sorted(chart_lists_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
            except (ValueError, OSError):
                continue
            out.append({
                "id": path.stem,
                "name": data.get("name", path.stem),
                "count": len(data.get("items", [])),
                "summary": data.get("summary"),
            })
    return out


def load_list(chart_lists_dir: Path, db_path: Path, list_id: str) -> dict:
    if list_id == ALL_DAYS_ID:
        return _all_days_payload(db_path)
    path = chart_lists_dir / f"{list_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No such list: {list_id}")
    data = json.loads(path.read_text())
    data.setdefault("id", list_id)
    data.setdefault("name", list_id)
    data.setdefault("items", [])
    return data
