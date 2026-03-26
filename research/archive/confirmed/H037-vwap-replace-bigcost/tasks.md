# Tasks: VWAP 取代大戶成本

## Phase 1: Distribution Research

- [x] 計算歷史所有交易日的 BigCost vs VWAP 差異（絕對值、百分比）
- [x] 分析差異的分佈統計（mean, median, std, max）
- [x] 檢查差異是否與市場狀態相關（高波動日、結算日、趨勢日 vs 盤整日）
- [x] 視覺化差異分佈圖 + 時間序列圖

---
### GATE
**問題：BigCost 與 VWAP 的差異是否小到可以直接替換？**

- 大部分交易日差異是否 < 10 點？
- 差異是否在特定條件下系統性擴大？
- 差異對策略進出場判斷的影響是否可忽略？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 在 runner.py 中將 BigCost 替換為 VWAP，執行 ORB EstHL 策略回測
- [ ] 執行 Reversal 策略回測
- [ ] 比較替換前後的績效指標（Sharpe, 勝率, 最大回撤）
- [ ] 確認 Pine Script 指標中的大戶成本是否也需同步修改
- [ ] 如果通過，執行全面替換並清理 BigCost 相關程式碼
