# Tasks: Multi-Day Rebound Exhaustion

## Phase 1: Distribution Research

- [ ] 定義「多日趨勢 + 反彈/回調竭盡」的篩選條件（BB%B + MA 方向 + 前幾日走勢）
- [ ] 統計 BB%B > 1 + MA↓ 與 BB%B < 0 + MA↑ 的歷史出現頻率
- [ ] 分析這些情境下的日內走勢特徵（反轉幅度、時間）
- [ ] 對比：此情境 vs 一般 Reversal setup 的 MFE/MAE 差異
- [ ] 探索「昨/前日成本」的最佳定義（VWAP vs 收盤價）
- [ ] 視覺化：多日走勢 + BB%B 極端 + 日內反轉的典型 pattern

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
