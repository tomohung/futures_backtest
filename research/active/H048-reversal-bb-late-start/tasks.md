# Tasks: Reversal BB Latch 延後起算時間

## Phase 1: Distribution Research

- [ ] 統計現行 08:45 起算下，BB latch 首次觸發的時間分佈
- [ ] 分離 08:45~09:05、09:05~09:10、09:10 後三個時段的 BB latch 觸發次數
- [ ] 分析各時段 BB latch 最終產生的交易損益分佈
- [ ] 比較三組 setup window（08:45 / 09:05 / 09:10）的進場次數與品質指標
- [ ] 視覺化：BB latch 時間 vs 交易結果散佈圖

---
### GATE
**問題：延後 BB latch 起算時間是否有統計上的改善？**

- 08:45~09:05 期間的 BB latch 交易結果是否明顯較差？
- 延後起算後進場次數是否仍足夠？（損失不超過 20%）
- 改善幅度是否值得改動策略？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 以 09:05 和 09:10 分別修改 ReversalStrategy 的 BB latch 起始時間
- [ ] 執行 in-sample 回測，與 08:45 基準比較
- [ ] 執行 out-of-sample 驗證
- [ ] 參數敏感度分析（09:00 ~ 09:15 每 5 分鐘一組）
