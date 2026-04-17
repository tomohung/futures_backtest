# Tasks: Night Session Volatility as EstHL Filter

## Phase 1: Distribution Research

- [x] 計算每日夜盤振幅（H-L），EMA20 正規化
- [x] 與 EstHL 每日損益配對（確認夜盤歸屬日期正確）
- [x] 以中位數分割高/低夜盤波動組，比較 EstHL 勝率、PF、平均損益
- [x] 嘗試不同分位數門檻（Q1/Q3、tercile）
- [x] 跨年穩定性檢驗（逐年分組方向是否一致）
- [x] 交叉分析：夜盤波動 × 星期，確認是否能解釋週四效應
- [x] 視覺化：分組績效比較圖、逐年穩定性圖

---
### GATE
**問題：夜盤波動分組是否對 EstHL 績效有顯著區分力？**

- 樣本數是否足夠？（每組最低 150 筆）
- 高低組 PF 差異是否 > 20%？
- 跨年方向一致性是否 > 2/3 年份？
- 解釋力是否優於或補充現有星期濾網？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [x] 定義夜盤波動門檻的進場濾網規則
- [x] 設定回測參數（手續費、滑價）
- [x] 執行 in-sample 回測（與現有星期濾網比較）
- [x] 執行 out-of-sample 驗證
- [x] Walk-forward 測試
- [x] 參數敏感度分析（門檻值的穩定性）
