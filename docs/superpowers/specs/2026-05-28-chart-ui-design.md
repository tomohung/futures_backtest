# 台指期 Chart UI — 設計文件

- 日期：2026-05-28
- 狀態：已通過 brainstorming，待寫實作計畫
- 作者：Tomo Hung + Claude

## 目標

一個本機 web app，用來快速瀏覽台指期（TX）行情並回顧回測/探索結果。核心使用情境：

1. 每次回測/探索後，把結果輸出成一份「清單」（標準格式），app 側欄 dropdown 可選不同清單。
2. 點清單裡的一筆項目 → 主視圖跳到該時間點的 K 棒並置中。
3. 主視圖可切換時間軸：1 / 5 / 15 / 30 / 60 分 / 1 日。
4. 主視圖可切換盤別：純日盤（08:45–13:45）/ 全日盤（前一交易日 15:00 → 當日 13:45）。
5. 一份內建「所有交易日」清單（最常用）：點一天 → 跳到當天 08:45 日盤開盤。

資料源：`data/futures.duckdb` 的 `ohlcv_1m` 表（僅 TX；已含夜盤 bars，2020-12-30 起）。

## 技術選型

Mirror `trading_spirit` 的 `screener-ui`：

- 後端：FastAPI + uvicorn
- 前端：vanilla JS SPA（無框架）+ TradingView **Lightweight Charts v5**（vendored standalone JS）
- 樣式：vanilla CSS 深色主題，台灣配色（**漲紅跌綠**）
- 資料：DuckDB **唯讀**連線（`read_only=True`，避免與 ETL 寫入衝突）
- 快取：`cachetools` 輕量記憶體快取（資料在本地 duckdb，不需 diskcache）

不採用的方案：
- 塞進 trading_spirit 的 screener-ui（會耦合兩專案資料/部署，台指期資料在本 repo）。
- Streamlit/notebook（圖表拉動/marker/多時間軸 UX 較差）。

## 目錄結構

```
futures_backtest/
├── src/chart_ui/
│   ├── __main__.py          # uvicorn runner；env CHART_UI_HOST / CHART_UI_PORT（預設 127.0.0.1:8888）
│   ├── app.py               # FastAPI factory：掛載 static、註冊 routers、/api/* 加 no-store header
│   ├── paths.py             # PROJECT_ROOT / DUCKDB_PATH / CHART_LISTS_DIR
│   ├── list_writer.py       # 共用 helper：回測腳本 import 這支，輸出標準清單 JSON
│   ├── routes/
│   │   ├── lists.py         # GET /api/lists、GET /api/lists/{id}
│   │   └── kline.py         # GET /api/kline?...
│   ├── services/
│   │   ├── kline_loader.py  # DuckDB 唯讀查詢 + session 過濾 + resample
│   │   ├── list_index.py    # 列舉 data/chart_lists/ + 內建「所有交易日」虛擬清單
│   │   └── resample.py      # OHLCV resample（1m → 5/15/30/60/1d）
│   └── static/
│       ├── index.html
│       ├── app.js
│       ├── app.css
│       └── vendor/lightweight-charts.standalone.production.js   # 從 trading_spirit 複製
├── data/chart_lists/        # 標準清單 JSON 存放處（在 data/ 下，已 gitignore）
└── run-chart-ui.sh          # 綁 tailscale IP，uv run chart-ui
```

## 打包與啟動

- `pyproject.toml` 新增相依：`fastapi>=0.110`、`uvicorn[standard]>=0.27`、`cachetools>=5.3`。
- 新增 `[project.scripts]`：`chart-ui = "chart_ui.__main__:main"`，並把 `src/chart_ui` 納入 hatch wheel packages（mirror screener-ui）。
- 啟動：`uv run chart-ui` 或 `./run-chart-ui.sh`。
- Python 3.14.3t（free-threaded）；fastapi/uvicorn 相容。

## 標準清單 JSON schema

每份清單一個檔 `data/chart_lists/<id>.json`，`<id>` 取檔名 stem，用於 dropdown 與 API。
逐筆項目唯一必填欄位是 `time`（跳轉目標），其餘全選填——讓「所有交易日」「策略交易」「選擇權價差」共用同一 schema。

```json
{
  "name": "EstHL 2025 交易",
  "strategy": "S001-esthl",
  "params": "frac=0.5, dte=2",
  "date_range": ["2025-01-01", "2025-12-31"],
  "summary": { "trades": 142, "win_rate": 0.58, "pnl_pts": 1234.0, "pf": 1.6 },
  "items": [
    {
      "time": "2025-09-23 09:04:00",
      "exit_time": "2025-09-23 09:21:00",
      "side": "long",
      "entry": 26106.0,
      "exit": 26048.0,
      "pnl_pts": -58.0,
      "return_pct": -0.222,
      "result": "Loss",
      "note": "",
      "levels": [
        { "price": 23200, "label": "sell_strike" }
      ]
    }
  ]
}
```

欄位說明：
- `time`（必填）：點該項目時跳轉並置中的時間點。
- `side`：含 long/buy → 紅色向上箭頭；含 short/sell → 綠色向下箭頭；其餘自由文字（如 `"Sell Call Spread"`）僅於側欄顯示，markers 用 entry/exit。
- `entry`/`exit`：有 `entry` 時畫進場價虛線；有 `exit_time` 時畫出場箭頭與持倉底色。
- `levels`（選填）：額外水平線陣列，通用化「進場價虛線」，給選擇權畫履約價 / est_high / est_low。
- 日期顯示：側欄與主圖標題一律帶星期幾（如 `2025-09-23 (二)`），由前端從 `time` 推導（一/二/三/四/五）。

## 輸出 helper（`chart_ui/list_writer.py`）

回測/探索腳本 import 使用，atomic write 到 `data/chart_lists/<id>.json`：

- `write_chart_list(name, items, **meta)` — 通用寫入。
- `write_chart_list_from_backtesting(df, name, **meta)` — 吃 Backtesting.py 的 `_trades` DataFrame，自動 map：`EntryTime→time`、`ExitTime→exit_time`、`EntryPrice→entry`、`ExitPrice→exit`、`Size` 正負 → `side`(long/short)、`PnL→pnl_pts`、`ReturnPct→return_pct`、`Tag→note`。現有 orb/reversal/exhaustion 腳本兩行接上。
- `write_chart_list_from_csv(path, mapping, name)` — 給選擇權那種自訂 CSV，用欄位對照表轉換（如 `touch_time→time`、`sell_strike/buy_strike→levels`）。

策略邏輯更新時，對應的 list 重新輸出即可。

## 內建「所有交易日」虛擬清單

`list_index.py` 永遠在 dropdown 最上方注入一筆 `所有交易日`：

- 不需檔案，即時查 DuckDB distinct 日盤交易日。
- 每筆 `time = "<日期> 08:45:00"`、無 entry/exit/levels。
- 新資料進來自動更新。
- App 啟動時**預設選中**這份清單（最常用）。

## API 端點

- `GET /api/lists` → dropdown 用：`[{id, name, count, summary?}, …]`（內建所有交易日 + `data/chart_lists/` 下所有檔）。
- `GET /api/lists/{id}` → 該清單完整 items（`__all_days__` 動態產生）。
- `GET /api/kline?center=YYYY-MM-DD&tf=&session=&adjust=` → 該交易日 ± 緩衝交易日的 K 棒（跳轉用）。
- `GET /api/kline?from=ISO&to=ISO&tf=&session=&adjust=` → 指定區間 K 棒（往邊緣拉動 lazy load 用）。

參數：
- `tf` ∈ {`1m`,`5m`,`15m`,`30m`,`60m`,`1d`}
- `session` ∈ {`day`, `full`}
- `adjust` ∈ {`raw`, `adj`}

回傳：`{ bars: [{time, open, high, low, close, volume}], meta: {...} }`
- intraday：`time` 為 epoch 秒，台灣本地時間「當作 UTC」編碼，使 HH:MM 正確顯示。
- 1日：`time` 為 `YYYY-MM-DD` 字串（Lightweight Charts business-day）。
- 成交量漲紅跌綠由前端依 close vs open 上色。

## Session 與 resample 邏輯

D = 選中交易日，P = D 之前一個**交易日**（非日曆日；故週一的 P = 週五）。

Session 過濾：
- 純日盤（`day`）：timestamp ∈ [D 08:45:00, D 13:45:00]
- 全日盤（`full`）：timestamp ∈ [P 15:00:00, D 13:45:00]（含 P 傍晚→D 清晨夜盤 + 收盤空檔 + D 日盤）

Resample（以 1m 為底）：
- OHLC：open=first、high=max、low=min、close=last、volume=sum。
- intraday bucket 對齊 session 開盤（日盤錨 08:45、夜盤錨 15:00）。
- `adjust=adj`：先把每根 1m 的 `adjustment` 加到 OHLC 再聚合（跨換倉不跳空）。

1日：
- 每交易日一根，OHLC 取該盤別區間（`day`=08:45–13:45 / `full`=[P 15:00, D 13:45]）。
- 回傳整段日線（約 1300 根，便宜），前端捲到選中日。
- `adjust` toggle 適用（日線跨換倉用 adj 避免跳空）。

非交易時段（13:45–15:00、05:00–08:45）無 bars；Lightweight Charts 連續描點，缺口自然收合，不留大片空白。

## 前端版面與互動

```
┌──────────────────────────────────────────────────────────────────┐
│ 台指期 Chart UI                                                     │
├────────────────┬───────────────────────────────────────────────────┤
│ ▼[所有交易日 ▾]│ tf:[1m][5m][15m][30m][60m][1d]  盤別:[日盤][全日]   │
│  (清單dropdown)│ 價格:[原始][調整]                                   │
│ ┌────────────┐ │ ┌───────────────────────────────────────────────┐ │
│ │摘要 142筆   │ │ │            K 棒主圖（標題顯示中心日+星期）       │ │
│ │勝率58 PF1.6 │ │ │     ▲entry        ▽exit                        │ │
│ ├────────────┤ │ │  ╴╴╴│╴╴╴╴╴╴╴╴╴╴╴╴│╴╴ 進場價虛線               │ │
│ │time side pnl│ │ │   ░│░░░░░░░░░░░░|░ 持倉底色                    │ │
│ │09:04 L  -58│◄│ │    │ ││ │││ ││ ││ │                            │ │
│ │09:01 L +151│ │ └───────────────────────────────────────────────┘ │
│ │ … 點列跳轉  │ │ ┌───────────────────────────────────────────────┐ │
│ └────────────┘ │ │ 成交量 ▂▃▅▍▎ (漲紅跌綠)                         │ │
└────────────────┴───────────────────────────────────────────────────┘
```

互動：
- 選 dropdown → 側欄填 items（新到舊）；側欄表頭顯示 summary。
- 點 item → 以其 `time` 為中心載入並捲動置中；有 entry/exit/levels 就畫箭頭 + 進場價虛線 + 持倉底色，並標損益點數。
- 切 tf / 盤別 / 價格 → 以目前中心日重載、保持中心。
- 拉到圖左/右邊緣 → lazy load 相鄰交易日（range API）。
- **↑/↓ 鍵在清單上下移並即時跳轉**（快速一天天翻看，配合最常用的「所有交易日」）。
- tf / 盤別 / 價格 選擇記在 localStorage。
- 日期一律帶星期幾顯示。

交易標記豐富度＝「標準」：進/出場箭頭（紅做多/綠做空）+ 進場價虛線 + 持倉期間底色 + 損益點數標籤。SL/TP 資料常為空，不畫。

## v1 範圍外（YAGNI）

- 技術指標（MA/MACD/KD…）：之後再加；架構沿用 Lightweight Charts 多 pane（screener-ui PANE_SETS）預留擴充。
- 即時報價 / 自動觸發 ETL：app 只讀現有 DB。
- 多商品：資料只有 TX。
- 標註 / 編輯 / 匯出。
- 認證：本機 + tailscale，預設關；需要時可加 screener-ui 的 BasicAuth。

## 開放的實作細節（交給實作計畫）

- hatchling packages 設定如何同時保留現有 `["src"]` 與新增 `chart_ui` 進入點（或改走 run-script 路線）。
- intraday epoch「當 UTC」編碼的精確做法與 DST（台灣無 DST，單純）。
- resample bucket 錨點與 60m 在 08:45 開盤的第一根處理。
- lazy load 的邊緣觸發門檻與緩衝交易日數。
- 持倉期間底色在 Lightweight Charts v5 的實作方式（無原生 region shading；候選：半透明 area/baseline series、垂直線標進出場、或進出場兩支 vertical line）；若成本過高可先以「進出場垂直線」替代底色。
