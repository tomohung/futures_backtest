# Tasks: SatZone 觸碰後三情境機率統計

## Phase 1: Distribution Research

- [ ] 實作 SatZone 觸碰偵測（逐日判斷是否觸碰 upper/lower）
- [ ] 定義三情境分類規則（長尾/橫盤/反向）
- [ ] 全期統計（2021-2026）：觸碰率、三情境機率
- [ ] 分層分析：年度、方向（UP/DOWN）、觸碰時間
- [ ] 產出 distribution.md + GATE 決定

---
### GATE
**問題：分佈結果是否支持進入回測？**
**決定：** [TODO]

---

## Phase 2: Backtest

- [ ] 若 GATE 通過：定義 credit spread 進場/出場規則
- [ ] 用 `ticks_options` 回測實際選擇權價格
- [ ] IS/OOS 驗證
