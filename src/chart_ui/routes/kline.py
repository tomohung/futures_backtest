"""/api/kline route。"""

from fastapi import APIRouter, HTTPException, Query

from src.chart_ui.services.kline_loader import (
    ALLOWED_ADJUST, ALLOWED_SESSION, ALLOWED_TF, load_kline,
)

router = APIRouter(prefix="/api/kline", tags=["kline"])


@router.get("")
def get_kline(
    center: str | None = Query(None),
    frm: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    tf: str = Query("1m"),
    session: str = Query("day"),
    adjust: str = Query("raw"),
):
    center = center or None  # 空字串視同未帶（避免 date.fromisoformat('') → 500）
    frm = frm or None
    to = to or None
    if tf not in ALLOWED_TF:
        raise HTTPException(400, f"tf must be one of {sorted(ALLOWED_TF)}")
    if session not in ALLOWED_SESSION:
        raise HTTPException(400, f"session must be one of {sorted(ALLOWED_SESSION)}")
    if adjust not in ALLOWED_ADJUST:
        raise HTTPException(400, f"adjust must be one of {sorted(ALLOWED_ADJUST)}")
    if tf != "1d" and center is None and (frm is None or to is None):
        raise HTTPException(400, "intraday 需要 center 或 from+to")
    return load_kline(center=center, frm=frm, to=to, tf=tf, session=session, adjust=adjust)
