# Tasks: ORB Phase 4 自適應 TP 優化

## Phase 1: Distribution Research

- [x] Step 0：探索性分析 — 夜盤 vs 日盤波動關係（`explore_night_day.py`）
- [x] 計算相關性矩陣：night_range vs or_range / day_range
- [x] 夜盤四分位分層分析
- [x] 年度夜盤統計
- [x] 決定 TP 設計方向（方案 A / B / C）

---
### GATE
**問題：分佈結果是否支持進入回測？**
**決定：** 通過。OR 寬度是日盤波動的最佳代理（or_range vs day_range 相關性最強），採用方案 A（OR 寬度 TP）。Phase 4 Hybrid（ORBPhase4HybridStrategy）成為後續迭代基礎。

---

## Phase 2: Backtest

- [x] Step 1：TP 策略實作（ORBPhase4Strategy / ORBPhase4HybridStrategy）
- [x] Step 2：優化（21 組 tp_or_multiplier x sl_pct）
- [x] 歷史年度驗證（2021-2024）
- [x] 診斷指標分析（tp_exit% / sl_exit% / force_exit%）
- [x] 結果：Phase 4 Hybrid 2021-2026 累計 +5,653 pts（> Phase 2 +4,632）
- [x] 衍生：Phase 6 機制濾網（→ Phase 6 spec）、Long-only（→ H026）
