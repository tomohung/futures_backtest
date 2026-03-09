# ORB with Estimated H-L Exit Strategy

## 背景與動機
結合 ORB（Opening Range Breakout）進場邏輯與 Estimated H-L Satisfaction Zone 出場機制，
並加入大戶成本過濾、30分K 20MA 方向濾網，以及 9:45 後的 Dow Theory 追蹤停損。

---

## 前置指標

### 1. 30分K 20MA 方向
- 從連續1分K（含夜盤）重採樣為 30分K
- 計算 rolling(20).mean() → `MA30_20`
- 使用最後一根**已收盤**的 30分K（shift(1)，避免 lookahead）
- 判斷方向：`Close30 > MA30_20` → 上升趨勢；`Close30 < MA30_20` → 下降趨勢

### 2. 大戶成本（`BigCost`）
- 每日日盤（08:45–13:45）中，volume ≥ 20MA(volume) 的 bar 才計入
- 大戶成本 = `SUM(close × volume) / SUM(volume)`（篩選後的 VWAP）
- 使用**昨日**大戶成本（shift(1) 取前一交易日）

### 3. Estimated H-L 指標（已實作）
- `EmaHL`：20日平均日波動 EMA
- `SatZoneUpper`、`SatZoneLower`：滿足區間邊界
- 來源：`src/backtest/estimate_hl.py` → `compute_estimate_hl_zones()`

---

## 進場

### 開盤區間（Opening Range, OR）
- **時間**：08:45–08:57（含，共 13 根1分K）
- 追蹤 `or_high = max(High[08:45–08:57])`，`or_low = min(Low[08:45–08:57])`

### 進場窗口
- **時間**：08:58–09:05（共 8 根1分K）
- 每日最多 1 次進場，第一個觸發訊號優先

### 做多條件（三者同時成立）
1. Close > or_high（突破開盤區間高點）
2. Close30 > MA30_20（30分K 20MA 上升趨勢）
3. or_high > BigCost（突破位置高於昨日大戶成本 → 方向正確）

### 做空條件（三者同時成立）
1. Close < or_low（跌破開盤區間低點）
2. Close30 < MA30_20（30分K 20MA 下降趨勢）
3. or_low < BigCost（跌破位置低於昨日大戶成本）

> **BigCost 為 NaN** 時（資料不足）：略過此濾網，仍可進場。

---

## 出場（優先順序由高至低）

### 1. 固定停損（SL）
- `sl_dist = 0.25 × EmaHL`（進場當根的 EmaHL 值）
- 做多：`sl_price = entry_price - sl_dist`；做空：`sl_price = entry_price + sl_dist`
- 每根 K 線：若 Close 穿越 sl_price → 出場

### 2. SatZone 兩段式出場（已實作）
- 觸及 `SatZoneUpper`（做多）或 `SatZoneLower`（做空）後標記
- 標記後，1分K 5MA 反轉 → 出場
- 實作：`EstimateHLExitMixin._record_bar()` + `_check_long/short_exit()`

### 3. Dow Theory 追蹤停損（9:45 後啟動）
- **啟動時間**：09:45（日盤開始後第 60 分鐘）
- **Pivot Lookback Period = 5**（5根1分K視窗）
- Pivot 確認：bar(i-2) 是 pivot low 當且僅當 `low[i-2] == min(low[i-4:i+1])`
  （需等 2 根 K 通過才能確認，無 lookahead）
- 做多：追蹤最新確認的 pivot low 作為停損線；Close < dow_trail_stop → 出場
- 做空：追蹤最新確認的 pivot high；Close > dow_trail_stop → 出場

### 4. 強制平倉
- 時間：**13:30**（不管任何條件，強制出場）

---

## 實作順序

### Step 1：`src/backtest/runner.py`
新增 `load_data_for_orb_est_hl(start, end)` 函式：
- 呼叫既有的 `estimate_hl=True` 邏輯（取得 EmaHL, SatZone 等欄位）
- 新增 30分K 20MA 計算（`MA30_20`, `Close30`）
- 新增每日大戶成本查詢並 shift(1) 對齊（`BigCost`）

### Step 2：`src/strategies/orb_est_hl_exit.py`
新建 `ORBWithEstHLExitStrategy(EstimateHLExitMixin, Strategy)`：
- 參數：`sl_ema_fraction = 0.25`
- 實作進場、停損、SatZone 出場（繼承 mixin）、Dow Trend 追蹤停損、強制平倉

### Step 3：`src/backtest/run_orb_est_hl.py`
獨立執行腳本：
```bash
uv run python src/backtest/run_orb_est_hl.py --start 2024-01-01
uv run python src/backtest/run_orb_est_hl.py --start 2022-01-01
```

---

## 成功標準
- 所有進場時間落在 08:58–09:05
- SL 在正確距離觸發（0.25 × EmaHL）
- SatZone 出場兩段邏輯正常運作
- Dow Trail Stop 只在 09:45 後啟動，且用 pivot 確認（2根延遲）
- 強制平倉確實在 13:30 執行
