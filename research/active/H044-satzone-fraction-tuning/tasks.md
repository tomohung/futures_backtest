# Tasks: SatZone Fraction 策略別調校

## Phase 1: Distribution Research

- [ ] 各策略（S001/S002/S003）在各 fraction（0.80~1.00）下的 touch rate
- [ ] 各策略目前 untouched 日的最終出場方式與損益分佈
- [ ] 各 fraction 下觸及後剩餘續行空間（確認降 fraction 的代價）
- [ ] 各策略 × fraction 的 EV% 粗估（不需完整回測，用分佈推算）

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 是否有至少一個策略在某 fraction 下 touch rate 顯著提升且損益方向正確？
- 降 fraction 的代價（錯失續行）是否可接受？
- 三個策略的最適 fraction 是否有分化（支持「策略別調校」的前提）？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 各策略分別回測最佳 fraction（IS: 2022~2024）
- [ ] OOS 驗證（2025~2026）
- [ ] 逐年一致性檢驗（每年 EV% >= baseline）
