# Tasks: Exhaustion 實盤 vs 回測比對

## Phase 1: Distribution Research

- [x] 從 live_parsed.csv 提取 exhaustion 交易
- [x] 跑同期間的 Exhaustion 回測，提取交易明細
- [x] 逐筆比對：進場日期、方向、時間、價格、損益
- [x] 分析重疊率與差異來源（濾網差異 / 進場條件 / 出場策略）
- [x] 彙整統計比較（勝率、均損益、PF）
- [x] 建立 ExhaustionStrategy + backtest.py，發現 H036 回測績效被高估

---
### GATE
**問題：比對結果是否揭示需要修正的系統性偏差？**

- 實盤與回測的交易日重疊率？→ 24.6%（filtered）/ 45.6%（raw）
- 程式化版本是否遺漏了實盤中高勝率的交易？→ 是，BB%B 門檻過嚴
- 是否有濾網或參數需要調整？→ 是，但更大的問題是 S003 整體 PF 只有 1.10

**決定：** [x] 繼續 Phase 2（重新評估 S003 + 測試修正方向）

---

## Phase 2: Backtest

- [x] 用 backtest.py（close 進場）重新評估 S003 是否值得繼續 live
- [x] 測試放寬 BB%B 門檻（> 0.85 / < 0.15 或 > 0.75 / < 0.25）
- [x] 測試移除夜盤新極值條件
- [x] 測試移除週三四濾網（實盤週三 100% 勝率）
- [x] IS/OOS 驗證修正後的效果
