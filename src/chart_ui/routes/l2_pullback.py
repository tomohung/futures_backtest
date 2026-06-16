"""/api/h120 route：當日 H120 進場（拉回站回 5MA 續攻 L2→L3）+ 停損/目標。"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.chart_ui.services.h120 import compute_h120_entries

router = APIRouter(prefix="/api/h120", tags=["h120"])


@router.get("")
def get_h120(d: str = Query(..., alias="date")):
    try:
        date.fromisoformat(d)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    return compute_h120_entries(date_str=d)
