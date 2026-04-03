# Tasks: Settlement Volatility Effect

## Phase 1: Distribution Research

- [ ] 標記所有結算日（第三個週三或順延），區分結算前 -2/-1/0/+1 日
- [ ] 計算每日三種振幅：日盤 H-L、夜盤 H-L、全日盤 H-L
- [ ] 比較結算日 vs 非結算日的振幅分佈（box plot + 統計檢定）
- [ ] 分析結算前後漸進效應（-2, -1, 0, +1）
- [ ] 以振幅 / EMA(20) 標準化，消除市場波動水準差異

---
### GATE
**問題：結算日振幅是否顯著大於非結算日？**

- 樣本數是否足夠？（最低門檻：結算日 30+ 筆）
- 三個維度（日/夜/全日）是否一致？
- 效應大小是否具交易意義（> 10%）？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 根據分佈結果設計結算日專用的 EstRange fraction 調整
- [ ] 回測調整後 vs 未調整的 Credit Spread 績效差異
- [ ] Out-of-sample 驗證
