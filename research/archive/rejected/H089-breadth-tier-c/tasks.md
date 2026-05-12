# Tasks: 廣度指標作為 Tier C 標準回檔的獨立進場 trigger

## Phase 1: Distribution Research

### Step 1.1: 資料準備（重用 H087 + H088 已建好的）
- [ ] 載入 H087 `breadth_indicators.csv`（new lows 52w / high-low diff / adv/dec / new highs 52w）
- [ ] 載入 H084 `tiers.csv`（21 events 含 Tier 標籤）+ `fuse_state.csv`（macro_tier 序列）
- [ ] 載入 H085 trigger dates（comp_z_4 top 10% 觸發日）以便算 Jaccard
- [ ] 載入 0050 含息（H085 cache）

### Step 1.2: 單一指標 trigger 分佈
- [ ] 對每個廣度指標，取 top 5% / 10% / 20% threshold
- [ ] 觸發日 cluster count（gap > 5d）
- [ ] 觸發日的事件命中：對應到哪個 Tier B/C trough？
- [ ] 與 H085 panic days 的 Jaccard similarity

### Step 1.3: Forward-return vs DCA baseline
- [ ] 每個 trigger 變體計算 +60/120/250d 0050 含息報酬
- [ ] 比 monthly DCA baseline（H085 已建好的算法）
- [ ] 分 macro_tier 看（C vs B vs A）— 重點是 Tier C 子集

### Step 1.4: 「H085-excluded」 trigger 變體
- [ ] 排除 H085 panic days，純看「only-breadth」事件的 forward return
- [ ] 這才是真正 Tier C-specialist 的 forward-return

### Step 1.5: Combo trigger 探索（可選）
- [ ] 廣度 OR 邏輯（任一極值）vs AND 邏輯（多軸同時極值）
- [ ] AND 變體應該樣本少但訊噪比高，若 N >= 6 且 +120d > DCA + 5% 才看

---

### GATE
**問題：廣度單獨 trigger 對 Tier C 是否有 forward-return edge over DCA？**

通過條件（皆需成立）：

- [ ] 至少 1 個廣度 trigger 的 +120d **OR** +250d median return > DCA baseline + 5%
- [ ] 該 trigger cluster 數在 6 ~ 50 之間
- [ ] Jaccard similarity vs H085 panic days < 0.5（提供新覆蓋）
- [ ] 「H085-excluded」變體下仍有 N ≥ 6 + median > DCA + 5%

**決定：**
- [ ] 通過 → 進入 Phase 2 backtest（含手續費 / hold 期 / 倉位管理變體）
- [ ] reject → 把 H088 + H089 結論「Tier C 結構性無 edge」寫進 H085 spec.md
- [ ] inconclusive → 樣本太少不足判定

---

## Phase 2: Backtest（GATE 通過才執行）

- [ ] 選最佳 trigger + threshold
- [ ] 進場：trigger 當日收盤買 0050 含息
- [ ] 出場規則探索：固定 hold (60/120/250d) vs 條件出場（z125 回 0 / VIX 回均值）
- [ ] 倉位管理：cooldown / max_open
- [ ] IS/OOS split + walk-forward
- [ ] 比較 vs H085 (S004) + DCA + B&H
- [ ] 敏感度分析：threshold 上下 10%

---

## 注意事項

- **預設失敗機率高**：H087 + H088 都已關閉相鄰問題
- **不要 data snooping**：threshold 與指標選擇先在 IS（2017-2022）決定，OOS（2023+）只驗證
- 若 reject 不要硬找變體 — 接受結構性結論
