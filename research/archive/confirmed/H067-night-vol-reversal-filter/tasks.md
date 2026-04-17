# Tasks: Night Session Volatility as Reversal Filter

## Phase 1: Distribution Research

- [x] 計算夜盤振幅 SMA20 正規化（沿用 H066 邏輯）
- [x] 與 Reversal 每日損益配對
- [x] 中位數分割：高/低組 WR、PF、avg PnL
- [x] Quartile 分析（確認單調性）
- [x] 跨年穩定性檢驗
- [x] 門檻敏感度（0.70–1.10）
- [x] 視覺化

---
### GATE
**問題：夜盤波動分組是否對 Reversal 績效有顯著區分力？**

- 每組樣本數 ≥ 100 筆？
- 高低組 PF 差異 > 20%？
- 跨年一致 > 2/3？
- Quartile 呈現單調或近似單調趨勢？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [x] IS/OOS 切分（2021-2024 / 2025-2026）
- [x] 不同門檻的 IS vs OOS 比較
- [x] Walk-forward 測試
- [x] 與現有 Reversal 基線比較
- [x] 參數敏感度分析
