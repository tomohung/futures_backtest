"""/api/extension route — 盤中『延伸力 / EXT』逐分鐘序列（多/空）。"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.chart_ui.services.extension import get_extension
from src.chart_ui.services.futures_extension import get_futures_extension

router = APIRouter(prefix="/api/extension", tags=["extension"])


@router.get("")
def get(d: str = Query(..., alias="date")):
    try:
        date.fromisoformat(d)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    res = get_extension(d) or {"bars": [], "strong_long": 0.10, "strong_short": 1.33}
    # 盤前『延伸力·多(0050期)』NYF 版（自身時間軸，08:45 起）；無資料則空陣列
    fut = get_futures_extension(d)
    res["fut_bars"] = fut["bars"] if fut else []
    return res
