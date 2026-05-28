"""FastAPI app factory for chart-ui."""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from src.chart_ui.paths import STATIC_DIR
from src.chart_ui.routes import kline, lists


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

    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


app = create_app()
