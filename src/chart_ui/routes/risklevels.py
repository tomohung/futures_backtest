"""/api/risklevels route：每個交易日的 EstRisk {risk, safe} 對照表（全歷史 EMA20）。"""

from fastapi import APIRouter

from src.chart_ui.services.risklevels import compute_risklevels

router = APIRouter(prefix="/api/risklevels", tags=["risklevels"])


@router.get("")
def get_risklevels() -> dict:
    return compute_risklevels()
