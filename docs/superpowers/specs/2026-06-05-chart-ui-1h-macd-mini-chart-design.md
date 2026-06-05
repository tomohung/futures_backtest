# Chart UI：左側 1 小時 K + MACD 參考圖

**日期**：2026-06-05
**狀態**：設計確認，待實作

## 目標

在 chart-ui 左側 sidebar 下方新增一張**唯讀**的 1 小時 K 線圖，下方附 MACD，作為覆盤時觀察大格局的參考。會跟著主圖目前的日期更新，但不需要任何遊標連動、點擊或進出場 marker。

## 動機

主圖通常看 1 分／5 分等較細的頻率，覆盤某一天時希望同時有一張較大週期（1h）的圖在旁邊，搭配 MACD 判斷波段方向。需求是「看得到就好」，不需要互動。

## 範圍

### 包含
- 左側 sidebar 下方固定高度區塊：上半 1h K 線、下半 MACD。
- 1h 圖**固定含夜盤**（session=full），不受主圖日盤/全日盤切換影響。
- 跟主圖日期：主圖載入某 center 日期時，mini 圖重抓對應區間的 1h K。
- MACD（標準 12/26/9）：DIF、DEA 兩條線 + 柱狀圖。
- 沿用主圖目前的 adjust（原始/調整）設定。

### 不包含
- 遊標連動（crosshair sync）。
- 點擊跳轉、進出場 marker、支撐壓力線、VWAP、MA 等主圖既有疊圖。
- 主圖的 session 切換不影響 mini 圖（mini 圖永遠 full）。
- tf 不可調整（mini 圖固定 60m）。
- 後端不需任何修改。

## 架構

### 後端（無變更）
沿用既有 `GET /api/kline`，已支援：
- `tf=60m`（`_TF_MINUTES` 已含）
- `session=full`（含夜盤聚合）
- `from`/`to` 明確區間
- `adjust=raw|adj`

**為什麼用 `from`/`to` 而非 `center`**：60m + full session 一天約 19 根 1h K（夜盤 ~14 + 日盤 5）。`center` 模式的自動載入會以 `_BARS_PER_DAY['60m']=5` 推算、目標 ~1100 根，往兩側各載約 110 個交易日的 1m 再聚合，每次換日期都偏重。改用 `from`/`to` 載入量有界、換日期反應快。

mini 圖請求：
```
GET /api/kline?from=<center-14 日曆天>&to=<center>&tf=60m&session=full&adjust=<主圖設定>
```
14 個日曆天約涵蓋 10 個交易日 ×19 ≈ 190 根 1h K，280px 寬可顯示其中最近的 6~8 天，餘量供些微平移。

### 前端

#### HTML（`static/index.html`）
在 sidebar 內、`list-table` 之後新增：
```html
<div class="mini-wrap">
  <div id="mini-chart"></div>
  <div id="mini-macd"></div>
</div>
```

#### CSS（`static/app.css`）
- `.list-table { flex: 1; min-height: 0; }`（已是 flex:1，維持可捲動，往上讓出空間）。
- `.mini-wrap`：固定高度（約 260px，flex 不縮）。
- `#mini-chart` 約 160px、`#mini-macd` 約 100px。

#### JS（`static/app.js`）
- 新增獨立狀態物件 `miniChartState`（chart / candle / macdLine(DIF) / signalLine(DEA) / hist），**與 `chartState` 完全隔離**，避免影響既有功能。
- 新增 `initMiniChart()`：建立兩個 lightweight-charts 實例（K 線一個、MACD 一個），唯讀選項（停用 crosshair 互動、不掛任何事件）。
- 新增 `loadMiniChart(center, adjust)`：
  1. 由 center 算 `from = center - 14 天`、`to = center`。
  2. fetch `/api/kline?from=..&to=..&tf=60m&session=full&adjust=..`。
  3. K 線 setData。
  4. 用收盤價算 MACD（見下），三條 series setData。
- 在主圖的載入流程（loadKline 完成、或日期變更 / adjust 變更時）呼叫 `loadMiniChart(currentCenter, state.adjust)`。

#### MACD 計算（前端，純函式）
標準參數 12/26/9：
- `EMA(12)`、`EMA(26)` → `DIF = EMA12 - EMA26`
- `DEA = EMA(9) of DIF`
- `histogram = DIF - DEA`

配色遵循台灣慣例（漲紅跌綠）：柱 >= 0 紅、< 0 綠；DIF/DEA 用對比明顯的兩色線。

## 資料流

```
主圖載入 center 日期 / 切換 adjust
        │
        ▼
loadMiniChart(center, adjust)
        │  from=center-14d, to=center, tf=60m, session=full
        ▼
GET /api/kline  ──► [1h OHLCV bars]
        │
        ├─► mini K 線 setData
        └─► computeMACD(closes) ─► DIF / DEA / hist setData
```

## 錯誤處理

- API 回空陣列（該區間無資料）：mini 圖清空、不報錯。
- bars 數 < 26（不足以算 MACD）：K 線照畫，MACD 留空。
- fetch 失敗：console 記錄，mini 圖維持上一次內容，不影響主圖。

## 測試 / 驗收

- 啟動 `uv run chart-ui`，左側下方出現 1h K + MACD。
- 點清單不同日期 → mini 圖跟著換到該日期區間。
- 主圖切「原始/調整」→ mini 圖跟著變。
- 主圖切「日盤/全日盤」→ mini 圖**不變**（永遠含夜盤）。
- mini 圖含夜盤 K（可見 15:00 之後的 1h K）。
- mini 圖無遊標連動、點擊無反應。
- 主圖既有功能（marker、VWAP、MA、支撐壓力、覆盤線）皆不受影響。

## 風險 / 備註

- full session 60m 的 bucket 以 origin="start" 對齊到區間第一根（前夜 15:00），日盤首根 1h K 可能只含 08:45–08:59（約 15 分），屬可接受的參考圖誤差。
- sidebar 280px 偏窄，1h K 當參考足夠；若日後想看更多根可再加可調高度，本期 YAGNI 不做。
