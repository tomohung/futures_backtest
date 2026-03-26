# Tasks: Reversal CCD Bypass Conditions Audit

## Phase 1: Distribution Research

- [x] 重建 Reversal setup 邏輯：對每個 BB touch 事件，記錄哪些 bypass 條件成立
- [x] 統計各條件的觸發頻率與重疊度（co-occurrence matrix）
- [x] 對「只靠某條件才能進場」的事件（exclusive trigger），分析勝率與 MFE
- [x] 比較各條件的邊際貢獻：condition-specific 勝率 vs 全體基準
- [x] 分析條件移除的影響：逐一移除每個 bypass，觀察損失的交易數量與品質

---
### GATE
**問題：是否有 bypass 條件可以安全移除？**

- 各條件的 exclusive trigger 勝率是否有顯著差異？（> 5%）
- 是否有條件的 exclusive trigger 勝率 < 50%（負貢獻）？
- 各條件的樣本數是否足夠判斷？（>= 20 筆 exclusive triggers）

**決定：** [ ] 繼續 Phase 2（ablation 回測）　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] Ablation 回測：逐一移除 bypass 條件，比較完整策略 vs 簡化版的績效
- [ ] 最優子集回測：只保留有正貢獻的 bypass 條件
- [ ] Out-of-sample 驗證
- [ ] Walk-forward 測試
