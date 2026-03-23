# Tasks: ORB Phase 2 全參數掃描

## Phase 1: Distribution Research

- [x] 確認 Phase 1 結論：Trend MA(10) 為唯一有效 filter
- [x] 設計 896 組有效參數網格
- [x] 執行全期掃描（2023-2025 train）

---
### GATE
**問題：分佈結果是否支持進入回測？**
**決定：** 通過。Phase 2 最佳組合達到 PF 1.22（2024）、勝率 56.8%（2025），累計 +4,632 pts。但 2021/2022 強制出場率僅 27%，TP 很少被打到，暴露固定 % TP 的結構問題。進入 Phase 4 自適應 TP（→ H025）。

---

## Phase 2: Backtest

- [x] 2023-2025 train 回測完成
- [x] 2021-2026 全期驗證完成：累計 +4,632 pts
- [x] 診斷發現：2021/2022 強制出場率 27%，TP=0.75% 與當日波動無關
- [x] 結論：TP 是固定百分比，不考慮當日波動度，為根本原因
- [x] Phase 3 嘗試換 SL 方案均失敗（OR SL、Super Trend、動量停滯）
- [x] 確認固定百分比 SL 已是最穩定，進入 Phase 4 改善 TP
