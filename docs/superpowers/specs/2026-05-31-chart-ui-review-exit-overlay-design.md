# Chart-UI 覆盤：出場資訊右欄 + 主圖關卡標示 — 設計

**日期**：2026-05-31
**狀態**：設計定稿（待 writing-plans）
**相關研究**：H093/H094（關卡達到率階梯、觸及續航）、H095（出場框架、DCI 方向共識指標）

## 目標

在 chart-ui 覆盤（選交易日）時，把 H095 發展出的出場框架資訊呈現出來：
1. **右欄**：當日 DCI（方向共識指標）+ regime 分帶；保留現有兩段式觸及提示；新增「建議出場法」。
2. **主圖**：標示當日關卡 ladder（多空 L1–L4 + 今高/今低）、各階首次觸及 marker、09:30/10:45 時間線。

用途：覆盤時一眼看到「這天是不是強 regime 日、關卡在哪、何時觸及、框架建議怎麼出場」。

## 非目標（YAGNI）

- 不做盤中即時 DCI（盤中廣度資料不在 DB；DCI 一律當日收盤值、標「事後」）。
- 不改回測清單既有的進出場 marker 流程（`drawTradeMarkers`），兩者並存。
- 不做空方進場訊號（無空方進場模型）；空方關卡/觸及/建議仍照樣標示（對稱）。

## 架構

沿用既有資料流：`selectItem(date)` → `renderDayStats(date)` 取 `/daystats` → 渲染右欄 + 畫主圖。

### 後端

**新模組 `src/chart_ui/services/dci_daily.py`**
- 純函式 `compute_daily_dci(conn, date) -> dict | None`
- 回傳 `{W, H, B, dci_long, dci_short, regime_long, regime_short}`（皆當日收盤值）
- 資料來源：
  - `B` = `market_breadth`（TWSE）：`(up_count − down_count) / listed_count`
  - `H` = `stock_day` 當日成交值前 20 大，`Σ sign(change)·value / Σ value`
  - `W` = `stock_day` 中**固定權值清單**（模組常數 `TOP_WEIGHT_SYMBOLS`，~20 檔台股權值股）內，`Σ sign(change)·value / Σ value`
- 公式（同 `dci_spec.md`）：`dci_long = 0.40W+0.35H+0.25B`、`dci_short = 0.30W+0.30H+0.40B`
- regime 分帶（起始門檻，同 spec）：long 強≥+0.3/弱≤−0.1；short 強空≤−0.2/弱≥+0.1
- 缺資料（無 breadth / 清單股不足）→ 回 `None`

**`daystats.compute_daystats()` 擴充 payload**
- `dci`：上述物件，附 `hindsight: true`、`w_proxy: true`（W 用固定清單+成交值近似權重的旗標）
- `touches`：`{bull: [{level, price, time}...], bear: [...]}`，各階 L1/L2/L3 首次觸及（擴充現有 `_level1_signals` 只到 L2 的範圍）
- `exit_advice`：`{bull, bear}` 每方向一段建議字串，由 `_exit_advice(touches, regime)` 產生（見下）

**建議出場法 `_exit_advice(direction_touches, regime)`**
- 純函式，依情境表把「實際觸及時間 + 時間閘(09:30/10:45) + EOD regime」映射成動作字串。
- 規則（多方；空方對稱）：
  - 碰 L1：一律「移 BE」；09:30 前→瞄 L3、否則→收 L2；強 regime→即使 09:30 後也續抱 L3
  - 碰 L2：早於 10:45→中 regime 啟 trail 博 L3 / 強 regime 靜態抱並可放 L4 / 弱 regime 守 L2；晚於 10:45→守 L2（強可放寬）
  - 碰 L3：中/弱→trail 收割；強→寬 trail 博 L4
- 輸出範例：`"多 09:25碰L1(早)→瞄L3抱BE；10:10碰L2(早)·中regime→Dow trail博L3"`
- regime 取對應方向（多看 `regime_long`、空看 `regime_short`），標「(事後)」。

### 前端 `app.js`

- **右欄新增 DCI 區塊**（`renderDci(d.dci)`）：DCI 值 + regime 圖示（🟥強/⬜中/🟦弱）+ W/H/B 分項 + 「事後·收盤」標註；W 標「權值清單近似」。下方接 `exit_advice` 多/空兩行。
- **主圖 `drawReviewOverlay(d)`**（沿用 `markerState`/`priceLines`，與 `drawTradeMarkers` 並存）：
  - 關卡水平線：多空 L1–L4 + 今高/今低（多紅系、空綠系、虛線；用 `d.bull`/`d.bear`）
  - 觸及 marker：`d.touches` 各階首次觸及點（標「多L2 10:10」之類）
  - 時間線：09:30 / 10:45 —— 優先垂直線；若 lightweight-charts 版本無垂直線 primitive，退為該根 K 的軸標記（實作時驗證版本）
  - 在 `renderDayStats` 末尾呼叫；切日期時先 `clearMarkers()`

## 元件邊界

| 元件 | 職責 | 依賴 |
|---|---|---|
| `dci_daily.compute_daily_dci` | 算當日 DCI（純資料） | DuckDB market_breadth / stock_day |
| `daystats._exit_advice` | 觸及+regime → 建議字串（純函式） | 無（吃參數） |
| `daystats.compute_daystats` | 組裝 payload | dci_daily、既有 helpers |
| `app.js renderDci / drawReviewOverlay` | 呈現 | daystats payload |

## 如實限制（標在 UI 與註解）

1. **DCI 為收盤/事後值**，非盤中重現 → 右欄明標「事後」，建議出場法標「(事後 regime)」。
2. **W 用固定權值清單 + 成交值近似權重**（無真實市值/指數權重）；清單需偶爾維護（模組常數，附更新日期註解）。
3. **時間線**畫法視 lightweight-charts 版本；fallback 為軸標記。

## 測試

- `dci_daily`：對 1–2 個已知日子單點驗算，對照 `regime_weighted_breadth.py` 的成交值加權值（量級一致）。
- `_exit_advice`：幾組 (觸及時間, regime) 輸入驗證輸出字串符合情境表。
- 目視：`uv run chart-ui` 選數個交易日，確認右欄 DCI/建議、主圖關卡線/marker/時間線正確、與回測清單 marker 不衝突。

## 未來（不在本次）

- 接盤中三序列 → 盤中即時 DCI（取代事後值）。
- 權值清單改自動由市值資料更新。
