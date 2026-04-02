# Tasks: Night Session 30m MACD + SMA Regime Classification

## Phase 1: Distribution Research

### Step 0: 資料準備
- [ ] 確認 ohlcv_1m 含夜盤資料，建構 30 分 K（含夜盤 + 日盤連續）
- [ ] 計算 SMA(5/21/65/130/233) on 30m bars
- [ ] 計算 MACD(12,26,9) on 30m bars

### Step 1: 定義分類規則
- [ ] 量化 SMA 排列狀態（多頭/空頭/壓縮/部分壓力）
- [ ] 量化 MACD 狀態（零軸位置、交叉、histogram 方向）
- [ ] 定義背離偵測邏輯（價格 vs MACD 高低點比較）
- [ ] 確定觀察時點：夜盤收盤（05:00）vs 日盤第一根（09:15）

### Step 2: 分類與統計
- [ ] 對每個交易日套用分類規則，標記 regime (A/B/C/D/E)
- [ ] 統計各 regime 出現頻率與分佈
- [ ] 計算各 regime 的日盤報酬分佈（open-to-close、intraday high/low）
- [ ] 跨 regime 比較：KS test、均值差異檢定

### Step 3: 視覺化
- [ ] 各 regime 的報酬分佈直方圖
- [ ] MACD + SMA 狀態的散佈圖（維度降低後視覺化）
- [ ] 時間序列上標記 regime，觀察是否有 regime 切換的規律

---
### GATE
**問題：分類後的 regime 是否具有預測力？**

- 各類樣本數 ≥ 50 筆？
- 趨勢型 regime (A/B) 的方向命中率 > 55%？
- 各 regime 的報酬分佈有統計顯著差異？（KS p < 0.05）
- 分類規則是否過於複雜或有 data snooping 疑慮？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改分類規則後重跑

---

## Phase 2: Backtest

- [ ] 根據 regime 決定當日策略方向（多/空/不做）
- [ ] 整合現有 EstHL / Reversal 策略作為進場引擎
- [ ] 設定回測參數（手續費、滑價）
- [ ] 執行 in-sample 回測
- [ ] 執行 out-of-sample 驗證
- [ ] Walk-forward 測試
- [ ] 與無 regime filter 的基準策略比較
