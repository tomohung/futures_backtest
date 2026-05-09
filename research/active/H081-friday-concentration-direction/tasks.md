# Tasks: 週五的權值股集中度方向訊號

## Phase 1: Distribution Research

### 1A. 樣本與分佈確認
- [ ] 從 concentration_index + ohlcv_1m 撈 ~241 個週五
- [ ] 切 5 桶 quintile（top20_dev_pct）→ 每桶樣本數
- [ ] 視覺化：Q5 × Fri vs Q1 × Fri 的 tx_dir 分佈直方圖

### 1B. 統計顯著性檢驗（核心 GATE）
- [ ] Mann-Whitney U：Q5×Fri vs Q1×Fri tx_dir 分佈（alternative='greater'）→ p-value
- [ ] 同樣對 Q5×Fri vs **整體週五 baseline** 做檢驗
- [ ] 同樣對 Q5×Fri vs **整體 1191 天 baseline** 做檢驗
- [ ] 三個 p-value 都應 < 0.05

### 1C. Permutation test（避免 weekday cherry-picking）
- [ ] 對 weekday label shuffle 1000 次，每次重算 Q5-Q1 (pp) 在 5 個 weekday
- [ ] 計算「實際週五 +15.99 pp」在 shuffle 分佈中的 percentile rank
- [ ] 若 percentile > 95%，則週五效應顯著；若 < 95%，可能 cherry-picking 假象

### 1D. 同期 vs 「未來 5 分鐘 / 30 分鐘」
- [ ] 雖然 Phase 1.5 還未做，但可以分析：「8:45-9:00 的 TX 報酬」與全日 tx_dir 的 corr
- [ ] 若極早盤已有方向訊號，週五策略可在 9:00 附近進場
- [ ] 注意：這仍是「同期相關性」，但縮短了實戰需要的時窗

### 1E. 樣本穩定性檢查
- [ ] 切兩半：2020-12 ~ 2023-06 vs 2023-07 ~ 2026-05
- [ ] 在兩段期間內分別跑 Q5×Fri p_up 與 Q5-Q1 (pp)
- [ ] 若兩段差距 ≥ 10 pp，效應可能不穩定

---
### GATE
**問題：週五的 Q5×Fri 方向 effect 是否穩健？**

通過條件（**全部** 通過才進 Phase 2）：
1. **MW p < 0.05**（Q5×Fri 顯著高於 Q1×Fri 與整體週五 baseline）
2. **Permutation test percentile > 95%**（不是 cherry-picking）
3. **樣本穩定性**：前後半 Q5×Fri p_up 差距 < 10 pp

任一不通過則歸檔 inconclusive，並嘗試：
- 換訊號分桶（top10、top5 改用，看訊號是否更純）
- 加入「結算週」二維濾網（結算前/後週五是否不同）

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest（GATE 通過後規劃）

- [ ] 進場規則：t = 週五 且 top20_dev_pct[t] > Q5 切點，long TX 開盤
- [ ] 出場規則：日盤收盤平倉
- [ ] In-sample (75%) + Out-of-sample (25%) 分割
- [ ] 與 H080 振幅濾網互動（同時集中度高，振幅也高 → 倉位減半？）
- [ ] 與 H082 安全日衝突檢測（Q1 vs Q5 互斥，無重疊）

## Phase 1.5: 早盤即時集中度驗證（同 H080）

- [ ] 累積即時集中度日記
- [ ] 驗證早盤即時 share 與全日 share 的 corr
- [ ] 通過 corr ≥ 0.85 才進 Phase 2 實戰
