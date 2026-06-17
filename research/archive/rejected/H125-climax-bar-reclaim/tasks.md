# Tasks: Climax Bar Reclaim 反轉做多

## Phase 1: Distribution Research

- [x] **Climax 定義**：改用持續放量錨定（近3根≥2.5×前10根 + 創新低），錨點=該段最大量單根 high（ZigZag-leg 版本因 theta 校準問題提早誤觸發，已捨棄）
- [x] **觸發定義**：後續 close > climax bar high（寬定義，不要求壓縮前提）
- [x] 撈出全部歷史觸發事件（N=1,847 / 1,006 日），統計每年事件數
- [x] 計算 forward 報酬分佈（+15/+30/+60、到收盤）
- [x] **虛無分佈對照**：同日隨機進場分鐘同 horizon → excess + pctile
- [x] **切片維度**：進場時段、leg 跌幅、持續放量量比、事前60分壓縮度、年度
- [x] 視覺化關鍵分佈圖（results/distribution.png）
- 結論：見 results/distribution.md（壓縮前提**反向**、edge 集中大跌幅 leg、2023–25 衰減、與高波 regime confound）

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 樣本數是否足夠？（最低門檻：**≥ 150 筆**觸發事件，且至少一個關鍵切片 ≥ 60 筆可獨立評估）
- forward 分佈相對虛無分佈是否有**顯著正向超額**（不是 ~52% drift）？
- 是否有切片維度脫穎而出（壓縮 / 時段 / leg 幅度）？
- 是否有明顯 data snooping / forward-looking tautology 疑慮？（比照 H063）

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 定義進出場規則（進場=收復 climax bar high；出場/停損/目標待定，考慮 EstRange/SatZone 動態出場）
- [ ] 設定回測參數（手續費、滑價 2 點）
- [ ] 執行 in-sample 回測（2021-2023）
- [ ] 執行 out-of-sample 驗證（2024-2026）
- [ ] Walk-forward 測試
- [ ] 參數敏感度分析（leg 幅度門檻、壓縮濾網、時段）
