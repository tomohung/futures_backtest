# Tasks: Reversal 實盤 vs 回測比對

## Phase 1: Distribution Research

- [x] 使用者提供實盤交易記錄至 `data/` 子目錄
- [x] 跑同期間的 Reversal 回測，提取交易明細
- [x] 逐筆比對：進場日期、方向、時間、價格、損益
- [x] 分類差異來源（滑價 / 信號延遲 / 漏接 / 多做 / 出場差異）
- [x] 彙整統計比較（勝率、均損益、PF）

---
### GATE
**問題：比對結果是否揭示需要修正的系統性偏差？**

- 實盤與回測的方向一致率是否 > 80%？ → 共同交易日 98.1%，通過
- 損益偏差是否集中在可解釋的因素？ → 是，65% TRIGGER_MISSED + 25% DIR_BLOCKED
- 是否有策略邏輯需要修正？ → 是，觸發條件太嚴格 + BC zone 方向限制太強

**決定：** [x] 繼續 Phase 2（修正策略）

---

## Phase 2: Backtest

- [x] 根據 Phase 1 發現的偏差，調整策略邏輯或參數
  - BC zone 放寬：無效（+24 pts），不採用
  - Near-SatZone pullback reset（sat_pullback_fraction=0.5）：PF 1.28→1.32，已採用
- [x] 重跑回測確認修正後的效果（ALL: N=556, Win=45.0%, PF=1.32, Total=+3757）
- [x] 驗證修正是否縮小實盤 vs 回測的落差
  - 重疊率 52.5%→61.4%，NEAR_SATZONE 類別 24→0
  - 剩餘 live-only 39 筆（TRIGGER_MISSED 22 + DIR_BLOCKED 12 + NO_BB_SETUP 4）交由 H042/H043 處理
