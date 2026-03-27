# Tasks: Multi-Day Rebound Exhaustion

## Phase 1: Distribution Research

- [x] 定義篩選條件：open vs BC zone + 5m 120MA 方向，4 種情境分類
- [x] 統計頻率 → H043 目標 20.8%（rebound_short 10.6% + pullback_long 10.2%），逐年穩定
- [x] BB setup 觸發率 → H043 場景 80%（高於 aligned 72%）
- [x] MFE/MAE 比較 → **H043 無 edge**：MFE>MAE 僅 48.6%，Net -0.027~-0.040
- [x] VWAP vs Close → VWAP 更穩定，建議沿用
- [ ] ~~視覺化~~（數據不支持假設，略過）

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 樣本數是否足夠？（門檻待定）
- 反彈竭盡後反轉的方向性是否明確？
- 與一般 Reversal 是否有足夠差異化？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 在 Reversal 策略中加入多日竭盡情境的識別邏輯
- [ ] 設定回測參數（沿用 Reversal）
- [ ] 執行 in-sample 回測（2021–2024）
- [ ] 執行 out-of-sample 驗證（2025–2026）
- [ ] 與原始 Reversal 策略對比
- [ ] 參數敏感度：BB%B 門檻、「多日」定義（2 日 vs 3 日）
- [ ] 回頭比對 H044 live-only 清單：22 筆 TRIGGER_MISSED（91% 勝率），確認捕捉率
