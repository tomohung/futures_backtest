# Tasks: 缺口日研究

## Phase 1: Distribution Research

- [x] 計算每日缺口（開盤價 vs 前收）
- [x] 缺口分級統計（微小/小/中/大）× 年度
- [x] 補缺口率統計（整體 + 分方向 + 分級距）
- [x] 補缺口時間分佈（開盤後幾分鐘補回）
- [x] 缺口大小 vs 當日 range%、oc% 交叉分析
- [x] 產出 distribution.md + GATE 決定

---
### GATE
**問題：分佈結果是否支持進入回測？**
**決定：** PASS — 進入 Phase 2（2026-03-25）

---

## Phase 2: Backtest

- [x] 若 GATE 通過：定義 E1 缺口竭盡反轉的 entry/exit 規則
- [x] 回測 E1 做空（開高破低 A 轉）+ 做多（開低破高 V 轉）
- [x] IS/OOS 驗證

### Verdict
**Rejected** — R:R 結構性不利，IS 全年度虧損（2026-03-25）
