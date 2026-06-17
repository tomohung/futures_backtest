"""/api/estrange route — 盤中『EstRange 預估振幅』逐分鐘高/低水平線（主圖疊線）。"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.chart_ui.services.estrange import get_estrange

router = APIRouter(prefix="/api/estrange", tags=["estrange"])


@router.get("")
def get(d: str = Query(..., alias="date")):
    try:
        date.fromisoformat(d)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    return get_estrange(d) or {"bars": []}
