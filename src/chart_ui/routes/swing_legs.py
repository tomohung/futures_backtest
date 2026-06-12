"""/api/swing-legs route：當日 11:30 前起點、幅度 ≥ L3 的 swing 波段。"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.chart_ui.services.swing_legs import compute_swing_legs

router = APIRouter(prefix="/api/swing-legs", tags=["swing-legs"])


@router.get("")
def get_swing_legs(d: str = Query(..., alias="date")):
    try:
        date.fromisoformat(d)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    return compute_swing_legs(date_str=d)
