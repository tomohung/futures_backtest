# Tasks: 選擇權未平倉量（OI）支撐壓力與 Max Pain

## Phase 0: ETL — 建立 OI 資料 Pipeline

- [ ] 調查期交所 OI 資料格式與下載方式
- [ ] 設計 DuckDB schema（options_oi 表）
- [ ] 實作下載腳本
- [ ] 實作 parse 腳本
- [ ] 驗證資料品質
- [ ] 整合進 daily_update.py

## Phase 1: Distribution Research

### A. OI 支撐壓力
- [ ] 每日 Put OI 最大 strike → S1，Call OI 最大 → R1
- [ ] 觸及反應 vs 隨機 vs H064 成交量版本

### B. OI 增減量
- [ ] 每日 OI 日增量最大的 strike
- [ ] 比較 OI 存量 vs OI 增量的 S/R 效果

### C. Max Pain 磁吸效應
- [ ] 每日計算 Max Pain
- [ ] 到期週（結算前 3 天）價格收斂到 Max Pain 的機率
- [ ] 非到期週作為對照

### D. PCR（OI-based）
- [ ] 用 OI 計算 PCR，vs 成交量 PCR，比較預測力

---
### GATE
**問題：OI 資訊是否提供超越成交量的額外預測力？**

- OI S/R 是否比 H064 成交量 S/R 更好？
- Max Pain 磁吸效應是否顯著？
- OI-PCR 是否比 Volume-PCR 更好？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 定義基於 OI S/R 和/或 Max Pain 的進出場規則
- [ ] 設定回測參數
- [ ] In-sample / Out-of-sample 驗證
- [ ] 參數敏感度分析
