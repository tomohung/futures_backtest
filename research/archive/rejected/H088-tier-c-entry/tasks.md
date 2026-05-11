# Tasks: Tier C 標準回檔進場訊號

## Phase 1: Distribution Research

### Step 1.1：資料準備
- [x] 載入 H084 indicators.csv + trough_mode_state.csv + 0050 + H085 comp_z

### Step 1.2：候選訊號定義
- [x] 10 個變體：z125≤{-1.5,-2.0} × {econ≥17, notA, nonH085} + margin≤-5

### Step 1.3：觸發日數與分佈
- [x] n_trig + cluster + Jaccard with H085

### Step 1.4：Forward-return
- [x] +60/+120/+250d med vs all-day & monthly DCA baseline

### Step 1.5：必抓事件覆蓋
- [x] margin_drop60≤-5 命中 11/13 Tier C 含必抓 2024-08 + 2026-03
- [x] z125-only 系列必抓 0/2

GATE：**Invalidation #1 觸發 — 沒有訊號 forward 120d 中位數超過 baseline + 1%**
（margin 系列命中率 85% 但 forward 跑輸 -1.3%；z125 系列命中率 30% 但漏抓必抓）

---

### GATE

**問題：H088 訊號是否能補充 H085 沒覆蓋的 Tier C 行情？**

通過條件（皆需成立）：
- [ ] Tier C 觸發日 forward 120d 中位數 ≥ baseline + 1%
- [ ] 樣本 N ≥ 30
- [ ] 與 H085 訊號重疊度 < 50%（jaccard）
- [ ] 必抓 2024-08 / 2026-03 至少 1 次

**決定：**
- [ ] 通過 → Phase 2 回測
- [ ] 修改後重跑（調整訊號定義）
- [ ] reject

---

## Phase 2: Backtest

- [ ] 進場規則：訊號日收盤買 1 倉
- [ ] 出場規則 sweep：固定 30/60/120d vs 條件出場（z 125MA ≥ 0 OR SMA60 站上）
- [ ] 倉位管理：cooldown + max_open（仿 V1，但因觸發頻率高，可能需 cooldown=10d）
- [ ] In-sample 2018-09~2022-12 / Out-of-sample 2023-01~ 同 H085 切分
- [ ] 比較總報酬 / Sharpe / MaxDD vs H085 + DCA + B&H
- [ ] **互補組合**：H085 + H088 同時 live 的綜合 equity 曲線
- [ ] 參數敏感度
