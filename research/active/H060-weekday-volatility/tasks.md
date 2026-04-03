# Tasks: Weekday Volatility Pattern

## Phase 1: Distribution Research

- [ ] 計算每日三種振幅：日盤 H-L、夜盤 H-L、全日盤 H-L
- [ ] 按星期幾分組，box plot 比較
- [ ] Kruskal-Wallis 檢定（非參數，不假設常態）
- [ ] 逐年分析穩定性（heat map: 年份 × 星期 × 中位振幅）
- [ ] 排除結算日後重跑，確認效應非結算日驅動
- [ ] 以振幅 / EMA(20) 標準化，消除市場波動水準差異

---
### GATE
**問題：星期別振幅差異是否顯著且穩定？**

- 樣本數是否足夠？（每個星期至少 100+ 筆）
- 差異是否逐年穩定？
- 效應大小是否具交易意義（> 15%）？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 根據分佈結果優化 EstRange 的 weekday fraction
- [ ] 回測 weekday-aware fraction vs 固定 fraction
- [ ] Out-of-sample 驗證
- [ ] 驗證日/夜盤是否需要不同的 fraction 設定
