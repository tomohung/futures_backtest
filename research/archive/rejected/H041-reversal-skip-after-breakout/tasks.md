# Tasks: Reversal Skip After Breakout

## Phase 1: Distribution Research

- [x] 跑 EstHL 回測，取得所有觸發進場的日期集合（160 天）
- [x] 跑 Reversal 回測，標記每筆交易當日是否有 EstHL 觸發（48/469 筆）
- [x] 比較「EstHL 觸發日」vs「非觸發日」的 Reversal 勝率、期望值、PnL
- [x] 分方向分析：EstHL 只做多，Reversal 同向做多 vs 反向做空的差異
- [x] 年度穩定性檢查

---
### GATE
**問題：EstHL 觸發日是否是 Reversal 低品質交易的主要來源？**

- 兩組勝率差 > 5%？
- 方向一致（至少 3 年以上）？
- 套用濾網後 PnL 改善 > 10%？

**決定：** [ ] 繼續 Phase 2　[x] 直接 Archive（Rejected）　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 實作「EstHL 觸發則跳過 Reversal」濾網
- [ ] 完整回測比較（含/不含濾網）
- [ ] Out-of-sample 驗證
- [ ] 考慮是否需要更新 Pine Script（加入 EstHL 觸發偵測）
