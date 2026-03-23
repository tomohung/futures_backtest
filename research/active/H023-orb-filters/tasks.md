# Tasks: ORB 策略過濾器優化

## Phase 1: Distribution Research

- [x] Filter 1（Range Size）獨立測試 — 無效，PF 反而下降
- [x] Filter 2（Trend MA）獨立測試 — 有效，最佳 PF 1.229
- [x] Filter 3（Gap）獨立測試 — 無效，PF 反而下降
- [x] Trend MA 細掃（trend_ma_days 5~20）
- [x] Day-only MA vs Night MA 比較
- [x] 選定 trend_ma_days=10 作為最佳值

---
### GATE
**問題：分佈結果是否支持進入回測？**
**決定：** 通過。Trend MA Filter 單獨有效（PF 1.02 → 1.215），進入 Phase 2 全參數掃描（→ H024）。Range Size 與 Gap Filter 方向放棄。

---

## Phase 2: Backtest

- [x] 固定 trend_ma_days=10，進入 H024 全參數掃描
- [x] 組合測試不需執行（僅 Trend MA 有效，無法組合）
