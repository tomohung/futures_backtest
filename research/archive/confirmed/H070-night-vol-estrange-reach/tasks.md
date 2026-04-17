# Tasks: Night Vol → EstRange Reach Rate

## Phase 1: Distribution Research

- [ ] 計算每日日盤 HL / EstRange ratio
- [ ] 與 night_norm 配對
- [ ] 分組比較 reach rate（HL >= EstRange 的比例）
- [ ] 分析超過 1×、1.2×、1.5× 的頻率
- [ ] 跨年穩定性
- [ ] 交叉分析：night_norm × weekday，哪個解釋力更強
- [ ] 相關性分析（Pearson/Spearman）
- [ ] 視覺化

---
### GATE
**問題：夜盤波動是否能預測日盤 EstRange 觸及率？**

- [x] 高低組 reach rate 差異 > 10%？→ 48% vs 34% ✓
- [x] 跨年穩定 > 4/6？→ 5/6 ✓
- [x] 解釋力優於星期加權？→ R² 7.4 倍 ✓

**決定：** [x] 繼續 Phase 2

---

## Phase 2: Backtest

- [ ] 現有 SatZone 在高/低夜盤的出場效率（SatZone 觸發率 vs 時間停損率）
- [ ] 進場價到 SatZone 距離 vs 停損距離（R/R ratio）× night_norm 分佈
- [ ] 測試 SatZone 縮放：低夜盤時 est_avg × scale factor
- [ ] EstHL 回測：縮放 SatZone + R/R 門檻
- [ ] Reversal 回測：同上
- [ ] IS/OOS 驗證
