"""CLI entry point: `uv run chart-ui`."""

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "src.chart_ui.app:app",
        host=os.environ.get("CHART_UI_HOST", "127.0.0.1"),
        port=int(os.environ.get("CHART_UI_PORT", "8888")),
        reload=False,
    )


if __name__ == "__main__":
    main()
