# Tasks: BB Extreme Bypass MA Direction

## Phase 1: Distribution Research

- [ ] 計算歷史所有交易日的 30 分 K BB(20, open) %B 值
- [ ] 統計 BB%B > 1 或 < 0 的出現頻率與分佈
- [ ] 在 BB%B 極端日中，找出被 MA 方向濾網擋掉的 Reversal setup
- [ ] 分析這些被擋交易的 MFE / MAE 分佈（假設進場後的表現）
- [ ] 對比：BB%B 極端 vs 正常區間的 Reversal 交易績效差異
- [ ] 視覺化：BB%B 分佈 + 極端值時的價格走勢特徵

---
### GATE
**問題：分佈結果是否支持進入回測？**

- BB%B 極端事件的樣本數是否足夠？（最低門檻：30 筆）
- 被 MA 擋掉的交易，其 MFE 是否明顯 > MAE？
- 極端 BB%B 是否確實傾向反轉而非趨勢延續？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 在 Reversal 策略中加入 BB%B bypass 邏輯
- [ ] 設定回測參數（手續費、滑價沿用 Reversal）
- [ ] 執行 in-sample 回測（2021–2024）
- [ ] 執行 out-of-sample 驗證（2025–2026）
- [ ] 與原始 Reversal 策略對比（加入 bypass 前後差異）
- [ ] 參數敏感度：BB%B 門檻（1.0 / 0.0 vs 1.1 / -0.1 等）
