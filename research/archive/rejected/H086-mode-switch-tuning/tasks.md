# Tasks: Mode 1 / Mode 2 切換規則調校

## Phase 1: 規則網格搜尋

### Step 1.1：規則參數定義
- [x] blue_streak 門檻：{1, 2, 3, 4, 6}（5）
- [x] econ_score 門檻直接版：{≤16 (藍), ≤22 (黃藍以下)}（2）
- [x] 250MA below 持續天數：{0, 5, 10, 20, 60}（5）
- [x] 邏輯組合：{AND, OR}（2）→ 共 5×7×2 = 70 rules + 4 baseline

### Step 1.2：每組規則的 confusion matrix
- [x] 載入 fuse_state.csv，計算 cond_A persistence
- [x] 對每組規則計算 recall(A) / FPR(bull) / hit(B/C/D) / median lag
- [x] 222 rows (74 rules × 3 splits) → rules_grid.csv

### Step 1.3：Pareto frontier 視覺化
- [x] 3-panel scatter (IS/OOS/FULL)，標 target zone (0.10, 0.80) 與 baseline
- [x] 識別 frontier 上的次優規則群（A≥0d OR streak≥6 系列為 sweet spot）

### Step 1.4：In-sample / Out-of-sample 切分
- [x] IS=2008-2018（A=1505, bull=261），OOS=2019-2026（A=510, bull=406）
- [x] 最佳規則 OOS recall **反而上升 +30%**（不是退化），但 FPR 也升 +12%

GATE：**Invalidation #1 觸發 — 0 個規則達 recall≥80% AND FPR≤10%**
最佳次優：A≥0d OR streak≥6（recall 60%, FPR 8%, Youden J=0.53）。詳見 distribution.md。

---

### GATE

**問題：是否存在一組規則能滿足 recall ≥ 80% + FPR ≤ 10%？**

通過條件：

- [ ] Pareto frontier 至少有一點同時滿足 Tier A recall ≥ 80% AND bull FPR ≤ 10%
- [ ] 該規則在 OOS 表現 recall 下降 ≤ 15%
- [ ] 規則參數對微調（如 ±1 streak 門檻）不極敏感

**決定：**
- [ ] 通過 → 採用最佳規則整合到 H085 Phase 2 回測
- [ ] 修改後重跑（擴展規則空間、加廣度指標）
- [ ] inconclusive → 樣本太少無法區分；維持 H084 既有規則

---

## Phase 2（不適用）

H086 是純結構性研究，不單獨做回測。最佳規則直接餵到 H085 / 後續 backtest。
