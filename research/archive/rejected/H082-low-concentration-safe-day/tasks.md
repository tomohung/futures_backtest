# Tasks: 低集中度 × weekday 安全日訊號

## Phase 1: Distribution Research

### 1A. 樣本與大跌事件確認
- [ ] 從 concentration_index 取 Q1 × Wed、Q1 × Fri、(Q1+Q2) × Fri 三個子樣本
- [ ] 列出每個樣本中所有大跌事件（trade_date + tx_dir + tx_range）
- [ ] 視覺化：tx_dir 分佈直方圖（與整體 baseline 疊圖對比）

### 1B. Wilson confidence interval（核心 GATE）
- [ ] 對 P(crash) = k/n 計算 95% Wilson CI 上限（不用正規近似，n 小才嚴謹）
- [ ] 若上限 < 13.85% (baseline)，拒絕「等於 baseline」虛無假設
- [ ] 三個子樣本各記錄結果

### 1C. Permutation test
- [ ] 對 (weekday, quintile) 雙標籤 shuffle 1000 次
- [ ] 每次重算「最低 P(crash) 格」的值
- [ ] 計算實際「Q1×Wed = 0%」在 shuffle 分佈中的 percentile rank
- [ ] 若 percentile ≥ 95%，效應穩健；< 95% 可能 multiple-comparison 假象（25 格中找最小）

### 1D. 樣本穩定性
- [ ] 切兩半：2020-12 ~ 2023-06（約 600 天）vs 2023-07 ~ 2026-05（約 591 天）
- [ ] 各段獨立計算 Q1×Wed、Q1×Fri 的 P(crash)
- [ ] 若任一段 P(crash) > 10%，安全日效應不穩定

### 1E. 加上 H079 訊號濾網的進階分析
- [ ] 在「Q1 × Wed」範圍內進一步切分 H079 訊號（up_ratio、lu_ratio）
- [ ] 看是否能找出更純的「絕對安全」子集
- [ ] 對應 H084 候選方向

---
### GATE
**問題：低集中度 × weekday 的安全日效應是否穩健？**

通過條件（H082-A、B、C 各自評估，**任一**通過即進 Phase 2）：
1. **Wilson CI 上限 < 10%**（明顯低於 baseline 13.85%）
2. **Permutation percentile ≥ 95%**
3. **前後半樣本穩定**（兩段 P(crash) 都 < 10%）

額外觀察：
- **mean_dir** 在通過子樣本中應 ≥ 0（不偏空）
- 若有任一通過，記錄為「risk-off 條件」可作為 long-only 策略的入場濾網

**決定：** [ ] 繼續 Phase 2（A/B/C 哪個通過）　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest（GATE 通過後規劃）

- [ ] 進場規則：t 屬於通過 GATE 的「安全日」格子，long TX 開盤
- [ ] 出場規則：日盤收盤平倉
- [ ] 期望結果：sharpe 不一定高，但 max DD 顯著低於整體 baseline
- [ ] 對比 baseline (long-every-day) 看 Sharpe / Sortino / max DD 改善
- [ ] 與 H080 振幅濾網疊加（c_low + 振幅小 = 雙重過濾）

## Phase 1.5: 早盤即時集中度驗證（同 H080）

- [ ] 累積即時集中度日記
- [ ] 驗證早盤即時 share 與全日 share 的 corr
- [ ] 通過 corr ≥ 0.85 才進 Phase 2 實戰
