"""/api/daystats route。"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.chart_ui.services.daystats import compute_daystats

router = APIRouter(prefix="/api/daystats", tags=["daystats"])


@router.get("")
def get_daystats(d: str = Query(..., alias="date")):
    try:
        date.fromisoformat(d)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    return compute_daystats(date_str=d)
