# Tasks: 時序版集中度預測

## Phase 1: Distribution Research

### 1A. IS / OOS 樣本切分驗證
- [ ] 從 concentration_index + ohlcv_1m 取 1191 天，加 lag-1 dev_pct
- [ ] 切 IS (2020-12 ~ 2024-08，~899 天) + OOS (2024-09 ~ 2026-05，~292 天)
- [ ] 確認兩段 dev_pct 分佈相近（mean、std、極端值）— 若 OOS 有 regime shift，需加註

### 1B. H083-A 純 t-1 預測力（pooled）
- [ ] 在 IS 上：5 桶 quintile by lag-1 dev_pct，計算每桶 t 振幅 mean/median
- [ ] 計算 IS 的 Q5/Q1 比例，記錄是否達 1.25
- [ ] 在 OOS 上重複，記錄 Q5/Q1 是否達 1.20
- [ ] 視覺化：IS vs OOS 5 桶振幅疊圖（看穩定性）

### 1C. H083-B weekday-conditional（核心）
- [ ] 在 IS 上：5 桶 × 5 weekday = 25 格，計算每格 t 振幅 mean
- [ ] 找 Tue/Wed 的 Q5/Q1 比例，記錄是否達 1.40
- [ ] 在 OOS 上重複
- [ ] **Permutation test**：對 (lag1_dev, weekday) 雙標籤 shuffle 1000 次
  - 每次重算 25 格 Q5/Q1 比例的最大值
  - 計算實際 Tue/Wed 的 Q5/Q1 在 null dist 中的 percentile rank
  - percentile ≥ 95% 才通過
- [ ] 視覺化：5 桶 × 5 weekday 的 IS/OOS heatmap

### 1D. H083-C 對既有 ema_range 的增量
- [ ] 計算 ema_range[t-1]（用 TX 振幅的 EMA-N，N 待定，常見 5/10/20）
- [ ] OLS：`range[t] ~ ema_range[t-1] + top20_dev_pct[t-1]`
- [ ] 看 dev_pct 係數的 t-stat 與 p-value
- [ ] 加 weekday dummy 與 dev × weekday interaction，看完整模型解釋力 R²
- [ ] Vif / multicollinearity check：dev_pct 與 ema_range 是否高度相關

### 1E. 多 N 比較
- [ ] 對 N ∈ {1, 5, 10, 20} 重複 1B（pooled Q5/Q1）
- [ ] 比較哪個 N 的 lag-1 預測力最強
- [ ] 預期 N=20 最強（auto-corr 最高），但其他 N 可能在某些 weekday 更純

### 1F. 不同 lag 比較
- [ ] 計算 corr(top20_dev_pct[t-k], range[t])，k = 1, 2, 3, 5, 10
- [ ] 確認 lag-1 是最強的（已知 lag-1 corr +0.18）
- [ ] 可疊加多 lag 看是否有獨立增量

### 1G. distribution.md 撰寫 + GATE 評估
- [ ] 將 1A–1F 結果整合進 `distribution.md`
- [ ] 顯眼處標記方法論：本研究是真正的「時序預測」（不是同期相關），但仍是 paper trading 級訊號
- [ ] 填寫 GATE 結論
- [ ] 列出 Phase 2 套到 S001-esthl 的具體規格建議

---
### GATE
**問題：t-1 集中度的振幅預測力是否穩健到值得套到 S001-esthl？**

通過條件（**至少 H083-A 與 H083-B 都通過**才進 Phase 2）：

1. **H083-A pooled**：IS Q5/Q1 ≥ 1.25 + OOS Q5/Q1 ≥ 1.20 + 兩段都單調
2. **H083-B weekday**：Tue 或 Wed 的 IS Q5/Q1 ≥ 1.40 + OOS ≥ 1.30 + permutation percentile ≥ 95%
3. **H083-C 增量**：dev_pct OLS t-stat ≥ 2（**這條可選，不入 GATE 主軸但入解讀**）

額外檢查：
- 樣本：IS ≥ 800 天、OOS ≥ 250 天
- IS / OOS 分佈相似（KS test p > 0.05）
- N=20 應為最佳 N；若小 N 顯著贏，記錄並考慮升級

**決定：** [ ] 繼續 Phase 2 套 S001-esthl　[ ] Archive Inconclusive　[ ] 修改假設後重跑

---

## Phase 2: 套用到 S001-esthl（GATE 通過後規劃）

- [ ] 設計 k_prior 對應表：(lag-1 quintile × weekday) → 倍數修正係數
- [ ] 修改 `src/strategies/estimate_hl_exit.py` 接受 dynamic 倍數
- [ ] In-sample 回測（2020-12 ~ 2024-08）：base vs k_prior-adjusted
- [ ] Out-of-sample 驗證（2024-09 ~ 2026-05）
- [ ] 評估指標：Sharpe、max DD、勝率、與 baseline 的差異
- [ ] 參數敏感度：k_prior 表 ±20% 看是否仍贏

### Phase 2 增強候選（需 Phase 1.5 即時資料管線）
- [ ] Bayesian update：盤中加入即時 share，動態混合 k_prior 與 k_realtime
- [ ] 比較 prior-only vs prior+update 的 Sharpe 差異

## Phase 1.5：即時集中度資料管線（與 H080/H081/H082 共用）

- [ ] 設計即時資料蒐集 schema（每天 8 個時點 × top 20 個股 × 累計成交額）
- [ ] 從 TWSE 即時 API 拉資料
- [ ] 累積 60–100 個交易日後，分析「累計到 t1 時點 share」與「全日 share」的 corr 演變
- [ ] 設計 Bayesian update 公式（先驗 vs 即時樣本權重隨時間變化）
- [ ] 給 H083 Phase 2 提供 k_realtime 的計算邏輯
