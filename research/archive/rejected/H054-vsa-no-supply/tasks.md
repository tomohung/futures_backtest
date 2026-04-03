# Tasks: VSA 無供應 — 趨勢回檔賣壓枯竭進場

## Phase 1: Distribution Research

- [x] 確認 No Supply 信號的時段分佈（幾點最多、幾點最有效）
- [x] IS/OOS 分年度績效（2021-2024 / 2025-2026）
- [x] Range/Volume 門檻敏感度（0.3x~0.7x 組合）
- [x] 測試不同 MA 期間（10, 20, 40）和趨勢定義
- [x] No Demand（反向做空）的獨立分析
- [ ] 與 EstHL/Reversal 的信號日重疊率（改用不同持有期間分析替代）
- [x] 每日觸發次數分佈（是否過度交易？）

---
### GATE
**問題：IS/OOS 是否一致，且加入成本後仍有 edge？**

- IS 和 OOS 的 PF 都 > 1.3？
- 每日平均觸發次數 < 3？
- 與現有策略重疊率 < 50%？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 實作 VSANoSupplyStrategy（含 EstHL 出場）
- [ ] 只取每日第一次信號 vs 允許多次進場
- [ ] IS/OOS 回測 + walk-forward
- [ ] 加入交易成本測試
- [ ] 與 EstHL 組合測試（互補效果）
