# Tasks: Night Session 30m MACD + SMA Regime Classification

## Phase 1: Distribution Research

### Step 0: 資料準備
- [x] 確認 ohlcv_1m 含夜盤資料，建構 30 分 K（含夜盤 + 日盤連續）
- [x] 計算 SMA(5/21/65) on 30m bars
- [x] 計算 MACD(12,26,9) on 30m bars
- [x] MACD 正規化（除以價格水準）避免跨年度尺度偏差

### Step 1: 定義分類規則
- [x] 量化 SMA 排列狀態（多頭/空頭/壓縮/部分壓力）
- [x] 量化 MACD 狀態（零軸位置、histogram 方向）
- [ ] 定義背離偵測邏輯 — 未實作，僅用 MACD 線/histogram 方向
- [x] 確定觀察時點：夜盤最後一根 30m bar（~05:00）

### Step 2: 分類與統計
- [x] 單因子分析（5 個布林條件 + t-test + KS test）
- [x] MACD% 正規化分桶（5 桶 × 晨盤報酬）
- [x] MACD Histogram% 分桶
- [x] 組合分析（MACD × SMA5>21 × SMA21>65）
- [x] 不對稱效應確認：只有空方反彈顯著（p=0.010），多方拉回不顯著（p=0.293）

### Step 3: 視覺化
- [x] 各因子 True/False 報酬分佈（直方圖 + boxplot + CDF）
- [x] MACD% vs Morning Move% 散佈圖（含 rolling mean）
- [x] 組合條件 bar chart

---
### GATE
**問題：夜盤 30m MACD/SMA 能否預測日盤前四根方向？**

- ✅ 樣本數充足：MACD < 0 有 399 筆，組合最少 73 筆
- ⚠️ 方向命中率：空方反彈 56.9%（> 55% 門檻），但多方拉回僅 53.4%
- ✅ 統計顯著：MACD > 0 t-test p=0.007, Price > SMA21 p=0.001
- ⚠️ 原假設方向不成立：效果是反轉而非順勢
- ❓ 尚未確認跨年穩定性

**決定：** 等待使用者決定

---

## Phase 2: Backtest
（待 GATE 決定）
