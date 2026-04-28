"""
抓 futures-ai.com /monitors/stock 的權值前 20 漲跌資料。

執行方式：
    uv run --python 3.12 --with playwright python scripts/fetch_futures_ai_stock.py
    # 首次需要：uv run --python 3.12 --with playwright python -m playwright install chromium

輸出 JSON 到 stdout，含：
    - api_calls: 攔截到的 JSON API 回應
    - ws_frames: 攔截到的 WebSocket 訊息（前 200 筆）
    - dom_text:  /monitors/stock 主要區塊的可見文字
"""
from __future__ import annotations

import json
import sys
from playwright.sync_api import sync_playwright

URL = "https://www.futures-ai.com/monitors/stock"


def main() -> None:
    api_calls: list[dict] = []
    ws_frames: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1600, "height": 1000},
            locale="zh-TW",
        )
        page = ctx.new_page()

        def on_response(resp):
            url = resp.url
            ct = resp.headers.get("content-type", "")
            if "application/json" in ct and "futures-ai.com" in url:
                try:
                    body = resp.json()
                except Exception:
                    return
                api_calls.append({"url": url, "status": resp.status, "body": body})

        def on_ws(ws):
            def on_frame(payload):
                if len(ws_frames) < 200:
                    ws_frames.append({"url": ws.url, "payload": payload[:2000]})
            ws.on("framereceived", on_frame)

        page.on("response", on_response)
        page.on("websocket", on_ws)

        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        # 等到網路 idle + 額外 5s 給 WS 推送資料
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(5000)

        # 抓主區塊文字 + 嘗試 grid/table-like 結構
        dom = page.evaluate(
            """
            () => {
              const main = document.querySelector('main') || document.body;
              // 嘗試找像表格的容器
              const candidates = [...main.querySelectorAll('[role="table"], [role="grid"], table, [class*="table"], [class*="Table"], [class*="grid"], [class*="Grid"]')];
              const tables = candidates.slice(0, 5).map(el => ({
                tag: el.tagName,
                cls: el.className?.toString?.().slice(0, 200),
                text: el.innerText.slice(0, 4000),
              }));
              return {
                title: document.title,
                bodyText: main.innerText.slice(0, 8000),
                tables,
              };
            }
            """
        )

        browser.close()

    print(json.dumps(
        {"api_calls": api_calls, "ws_frames": ws_frames, "dom": dom},
        ensure_ascii=False, indent=2,
    ))


if __name__ == "__main__":
    main()
