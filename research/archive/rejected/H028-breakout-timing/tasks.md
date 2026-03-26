# Tasks: 突破時間點與勝率分析

## Phase 1: Distribution Research

- [x] 設計分析方法（逐分鐘、5 分鐘桶、關鍵時段對比、年度穩定性）
- [x] 實作 `explore_breakout_timing.py`
- [x] EstHL 突破時間分析
- [x] ORBLong 突破時間分析

---
### GATE
**問題：分佈結果是否支持進入回測？**
**決定：** [待使用者決定] — 見 results/distribution.md

---

## Phase 2: Backtest

- [ ] 根據 Phase 1 結果決定是否需要修改進場時間窗口
- [ ] 若有顯著差異，在策略中加入時間區段濾網
