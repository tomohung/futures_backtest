# Tasks: CHOP 斬波指標作為 EstHL 盤整日濾網

## Phase 1: Distribution Research

- [x] 計算每日 CHOP(14)，分析分佈與季節性
- [x] 比對 CHOP 分區（>61.8 / 38.2~61.8 / <38.2）的次日 EstHL 交易績效
- [x] 統計 CHOP > 61.8 日的 EstHL 交易勝率、PF、avg PnL
- [x] 測試不同 CHOP 期間（10, 14, 20）和門檻（55, 61.8, 65）
- [x] 也測試對 S002 Reversal 的濾網效果

---
### GATE
**問題：CHOP 濾網是否有效改善 EstHL？**

- 過濾後 PF 提升 > 0.05？
- 被過濾的交易中虧損比例 > 60%？
- 門檻敏感度是否穩定？

**決定：** [x] 繼續 Phase 2（CHOP(10) > 61.8，Mon~Wed 額外濾網）

---

## Phase 2: Backtest

- [x] 在 EstHL backtest.py 加入 CHOP 濾網
- [x] IS/OOS 驗證
- [x] 與現有濾網（weekday / ORB width / ADX）的交互效果
- [x] 確認無 data snooping（門檻穩定性）
