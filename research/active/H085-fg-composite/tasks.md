# Tasks: TW F&G 合成版 forward-return 驗證

## Phase 1: Distribution Research

### Step 1.1：資料準備
- [ ] 從 H084 的 results/indicators.csv 載入 4 個非冗餘指標 + 0050 標的需要的價格
- [ ] 取得 0050 含息調整收盤（yfinance 0050.TW 或 TWSE TR Index）
  - 起始日：H084 indicators 起始（2008-01）但 0050 上市於 2003-06 → 用 2008 起算
- [ ] 計算每月最後一交易日的 monthly DCA baseline 序列

### Step 1.2：合成 score 計算
- [ ] 實作 z-score 加總版本（4 指標各自方向標準化後加總）
- [ ] 實作計票版本（每個指標達 ≥85 / ≤15 百分位算 1 票）
- [ ] 比較兩種合成法的時間序列是否一致

### Step 1.3：閾值分析
- [ ] 對每個合成版本取 top 5%、top 10%、top 20% 為觸發日
- [ ] 計算每個閾值下的觸發日總數與時間分佈
- [ ] 畫出合成 score 時間序列 + 觸發日標記疊在 0050 圖上

### Step 1.4：Forward-return 分析
- [ ] 對每個觸發日，計算 +60D / +120D / +250D 的 0050 含息報酬
- [ ] 對應的 DCA baseline：同期間累積的 DCA 平均成本 vs 終值
- [ ] 輸出表格：觸發日 → forward returns vs baseline

### Step 1.5：分佈對比
- [ ] 視覺化觸發日 vs 隨機日 forward-return 分佈
- [ ] 計算統計：median、mean、25/75 百分位、勝率（forward return > baseline 的比例）
- [ ] 分 mode 看：parent_macro_tier=A 的觸發日 vs B/C 的觸發日，行為是否不同

---

### GATE

**問題：合成 score 是否系統性優於 baseline？**

通過條件（皆需成立）：

- [ ] 高分日（top 10%）的 forward 120D/250D 報酬中位數 ≥ baseline + 3%
- [ ] 樣本 ≥ 30 個觸發日，且不集中於單一事件群（事件 cluster ≥ 5 個）
- [ ] 至少一種合成法（z-score 或 vote）通過
- [ ] 合成優於單因子最佳（VIX_pct 單獨表現）至少 1%

**決定：**
- [ ] 通過 → Phase 2 回測
- [ ] 修改後重跑（調整閾值、合成法）
- [ ] reject → 衍生假設：vix_pct 單因子（H08X，新編號）

---

## Phase 2: Backtest

- [ ] 進場規則：合成 score ≥ 閾值（單次或連續 ≥N 天）
- [ ] 出場規則：固定持有 N 個月 OR 達某個賣出條件
- [ ] In-sample 2008-2020、Out-of-sample 2021-2026 walk-forward
- [ ] 比較總報酬、Sharpe、最大回撤 vs DCA baseline
- [ ] 參數敏感度（閾值、持有期、合成權重）
