"""FastAPI app factory for chart-ui."""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.chart_ui.paths import STATIC_DIR
from src.chart_ui.routes import daystats, kline, lists, risklevels


def _asset_version() -> int:
    """app.js / app.css 任一被修改就變動的 token（取 mtime 最大值），給 index.html 帶版本號用。"""
    v = 0
    for name in ("app.js", "app.css"):
        p = STATIC_DIR / name
        if p.exists():
            v = max(v, int(p.stat().st_mtime))
    return v


def create_app() -> FastAPI:
    app = FastAPI(title="台指期 Chart UI", docs_url="/api/docs")

    @app.middleware("http")
    async def no_store_api(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(kline.router)
    app.include_router(lists.router)
    app.include_router(daystats.router)
    app.include_router(risklevels.router)

    # index.html 帶上資產版本號（依 app.js/app.css mtime），改前端後瀏覽器自動抓新檔、免手動硬重整。
    # 此路由必須在 "/" StaticFiles mount 之前註冊才會優先命中。
    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        v = _asset_version()
        html = html.replace("/app.js", f"/app.js?v={v}").replace("/app.css", f"/app.css?v={v}")
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


app = create_app()
