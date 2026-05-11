# Tasks: TW F&G 合成版 forward-return 驗證

## Phase 1: Distribution Research

### Step 1.1：資料準備
- [x] 從 H084 的 results/indicators.csv 載入 4 個非冗餘指標 + 0050 標的需要的價格
- [x] 取得 0050 含息調整收盤（yfinance 0050.TW，auto_adjust=True）
  - 起始日：實際窗 2017-08-31（VIX_pct 1 年 rolling 限制），終止 2026-04-30
- [x] 計算每月最後一交易日的 monthly DCA baseline 序列（N=98 with +120d）

### Step 1.2：合成 score 計算
- [x] 實作 percentile-average（comp_pct, 0–100）
- [x] 實作 z-score 加總（comp_z）
- [x] 實作計票版本（comp_vote, 0–4 票，≥85 percentile 為 1 票）
- [x] 比較三種合成法的時間序列：corr(pct,z)=0.94, corr(pct,vote)=0.68, corr(z,vote)=0.78

### Step 1.3：閾值分析
- [x] 對每個合成版本取 top 5%、top 10%、top 20% 為觸發日
- [x] 計算每個閾值下的觸發日總數與 cluster 分佈（comp_pct top10% N=210/14 cluster）
- [x] 畫出合成 score 時間序列 + 觸發日標記疊在 0050 圖上 → composite_timeseries.png

### Step 1.4：Forward-return 分析
- [x] 對每個觸發日，計算 +60D / +120D / +250D 的 0050 含息報酬
- [x] 對應的 DCA baseline：每月最後交易日的同期 forward returns
- [x] 輸出表格：trigger_returns.csv + trigger_summary.csv

### Step 1.5：分佈對比
- [x] 視覺化觸發日 vs 隨機日 forward-return 分佈 → forward_return_dist.png
- [x] 計算統計：median、mean、勝率（vs DCA median baseline）
- [x] 分 macro_tier 看：tier=B 表現最強（+250d med +74%）

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

- [x] 進場規則：comp_z ≥ 3.97（IS top 10% fit）
- [x] 出場規則：固定持有 250 trading days
- [x] In-sample 2018-09~2022-12 / Out-of-sample 2023-01~2026-04 walk-forward（rolling 5yr percentile）
- [x] 比較總報酬、Sharpe、最大回撤 vs DCA baseline + Buy-and-hold
- [x] 參數敏感度（96 組合：score × top_pct × hold_days × mode）
- [x] **Phase 2.5 倉位管理：B0 vs V1 vs V2 比較 → V1 最終勝出（cooldown=5d, max=5）**

Verdict: **Confirmed (限定 comp_z + V1 倉位管理)；Rejected (comp_pct 變體)**
