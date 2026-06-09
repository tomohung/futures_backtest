"""/api/extension route — 盤中『延伸力 / EXT』逐分鐘序列（多/空）。"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.chart_ui.services.extension import get_extension

router = APIRouter(prefix="/api/extension", tags=["extension"])


@router.get("")
def get(d: str = Query(..., alias="date")):
    try:
        date.fromisoformat(d)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    return get_extension(d) or {"bars": [], "strong_long": 0.10, "strong_short": 1.2}
