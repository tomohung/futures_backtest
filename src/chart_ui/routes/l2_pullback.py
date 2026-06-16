"""/api/l2_pullback route：當日 L2 拉回續攻進場（拉回站回 5MA 續攻 L2→L3）+ 停損/目標。"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.chart_ui.services.l2_pullback import compute_l2_pullback_entries

router = APIRouter(prefix="/api/l2_pullback", tags=["l2_pullback"])


@router.get("")
def get_l2_pullback(d: str = Query(..., alias="date")):
    try:
        date.fromisoformat(d)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    return compute_l2_pullback_entries(date_str=d)
