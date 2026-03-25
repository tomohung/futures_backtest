# Tasks: 趨勢竭盡反轉

## Phase 1: Distribution Research

- [x] 計算 30 分 K 20MA 方向與 BB%B(20, open)
- [x] 計算夜盤 OHLC + 近二日新高低判定 + 收相對高低
- [x] 統計各條件單獨與複合的觸發頻率（年度分佈）
- [x] 分析觸發日的 ORB 反向突破率
- [x] 觸發日的日盤反轉方向 oc% 分佈
- [x] 產出 distribution.md + GATE 決定

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 樣本數是否足夠？（最低門檻：年均 15 筆）
- 觸發日是否有反轉傾向？
- 條件是否在不同年度穩定？

**決定：** PASS — 進入 Phase 2（2026-03-25）

---

## Phase 2: Backtest

- [x] 實作策略（進場 + EstHL 出場）
- [x] IS (2021-2024) / OOS (2025-2026) 回測
- [x] 參數敏感度（BB 門檻、夜盤收位定義、ORB 時長、BC 距離、SL 倍數）
- [ ] 與 EstHL / Reversal 的交易日重疊分析（略，因 Rejected）

### Verdict
**Confirmed** — 修正夜盤對齊 + 跳過週三四 + ORB%>=0.25% 後，IS PF=1.08, OOS PF=1.70, 實盤 4/4 獲利。（2026-03-25）
