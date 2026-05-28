"""/api/lists routes。"""

from fastapi import APIRouter, HTTPException

import src.chart_ui.paths as paths
from src.chart_ui.services.list_index import list_lists, load_list

router = APIRouter(prefix="/api/lists", tags=["lists"])


@router.get("")
def get_lists():
    return list_lists(paths.CHART_LISTS_DIR, paths.DUCKDB_PATH)


@router.get("/{list_id}")
def get_list(list_id: str):
    try:
        return load_list(paths.CHART_LISTS_DIR, paths.DUCKDB_PATH, list_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
