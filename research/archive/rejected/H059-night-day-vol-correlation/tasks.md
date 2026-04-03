# Tasks: Night-Day Volatility Correlation

## Phase 1: Distribution Research

- [x] 計算每日夜盤 H-L 與日盤 H-L，建立配對資料集
- [x] 計算 Pearson / Spearman 相關係數
- [x] 散佈圖 + 回歸線（以數值表格呈現）
- [x] 將夜盤振幅分 quartile，比較各組日盤振幅分佈
- [x] 檢查極端值：夜盤振幅 > 2 倍 EMA 時，日盤行為是否不同
- [x] 以振幅 / EMA(20) 標準化後重跑相關分析

---
### GATE
**問題：夜盤振幅能否預測日盤振幅？**

- 樣本數是否足夠？（最低門檻：200+ 配對）
- 相關係數是否 > 0.2 且統計顯著？
- 是否存在可利用的非線性關係？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 根據夜盤振幅 quartile 動態調整日盤 EstRange fraction
- [ ] 回測調整後 vs 固定 fraction 的績效差異
- [ ] Out-of-sample 驗證
