# Tasks: 漲停熱絡持續作為動量延續訊號

## Phase 1: Distribution Research

### Step 1.1: 資料準備
- [ ] 從 stock_day 算每日 lu_value（漲停成交額）, total_value
- [ ] 算 lu_value_ratio + ma7
- [ ] 載入 0050 含息 (H085 cache) + forward returns 60/120/250d
- [ ] 載入 H084 fuse_state.csv 取 macro_tier 序列
- [ ] 載入 H085 panic days 算 Jaccard

### Step 1.2: 單一 threshold 分佈
- [ ] 取 lu_value_ratio_ma7 top 5% / 10% / 15% / 20% threshold
- [ ] 每個變體：n_triggers, n_clusters (gap >5d), Jaccard vs H085
- [ ] 觸發日 macro_tier 分佈

### Step 1.3: Consecutive 要求變體
- [ ] consec=1（單日達 threshold）vs consec=3 vs consec=5
- [ ] 看 forward return + cluster 數變化

### Step 1.4: Forward-return vs DCA baseline
- [ ] 每個 (threshold × consec) 組合算 +60/120/250d median, mean, win rate
- [ ] Lift vs DCA baseline
- [ ] 分 macro_tier 看（bull / A / B / C / D）

### Step 1.5: 拿掉 bull regime 後是否仍 robust
- [ ] 只取 macro_tier != 'bull' 子樣本，看 lift 是否還在
- [ ] 確認訊號不是「牛市定義 tautology」

---

### GATE
**問題：分佈結果是否支持進入回測？**

通過條件（皆需成立）：

- [ ] 至少 1 個 (threshold × consec) 組合的 +60d **OR** +120d median > DCA + 2%
- [ ] 該組合 cluster 數 8-30
- [ ] Jaccard vs H085 < 0.3
- [ ] macro_tier != 'bull' 子樣本下仍 lift > +1%

**決定：**
- [ ] 繼續 Phase 2（含手續費 + 出場規則 + IS/OOS）
- [ ] 直接 Archive (reject)
- [ ] 修改假設後重跑

---

## Phase 2: Backtest（GATE 通過才執行）

- [ ] 進場：trigger 當日收盤買 0050
- [ ] 出場規則探索：
  - 固定 hold (60/90/120d)
  - 條件出場（lu_value_ratio_ma7 跌破 50 分位 → 動能消失）
- [ ] 倉位管理：cooldown、max_open
- [ ] 手續費 + 滑價（同 H085）
- [ ] IS (2010-2020) / OOS (2021-2026) split
- [ ] Walk-forward 驗證
- [ ] 敏感度：threshold 上下 25%
- [ ] 對比基準：DCA、B&H、H085 (S004)
- [ ] 跟 H079 防守訊號的兼容性：兩者是否會打架？

---

## 注意事項

- **與 H079 對稱性**：訊號設計要對應（ma7 + consecutive + percentile）
- **不要 data snooping**：threshold 與 consec 在 IS 決定，OOS 驗證
- **Regime sensitivity**：動量訊號常在牛市過 fit，要做 regime-stratified 評估
- 若 confirm 並上線，與 S004（H085）形成「fear→panic 抄底」+「greed→momentum 加碼」雙策略
