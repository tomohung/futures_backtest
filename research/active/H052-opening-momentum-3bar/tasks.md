# Tasks: 開盤 3 分鐘連續收紅動能

## Phase 1: Distribution Research

- [ ] 確認 N=3 連續收紅的分佈（分年度、分星期）
- [ ] 測試反向（N=3 連續收綠 → 做空）
- [ ] 分析信號日的日內走勢特徵（MFE 時間分佈、最大回撤時機）
- [ ] 比對信號日與 EstHL/Reversal 的重疊率
- [ ] 測試加入量能條件（3 根都放量 vs 不限量）

---
### GATE
**問題：加入出場策略後是否仍有正期望值？**

- N=3 做多的 IS/OOS PF 是否 > 1.2？
- 與現有策略的重疊率是否 < 50%（有互補價值）？
- 反向做空是否也有正期望值？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 實作 OpeningMomentumStrategy（含 EstHL 出場）
- [ ] IS/OOS 回測（2021-2024 / 2025-2026）
- [ ] 測試不同出場策略（SatZone vs trailing vs 固定 TP）
- [ ] 參數敏感度（N=2,3,4 / 量能門檻 / 進場時機）
- [ ] Walk-forward 驗證
