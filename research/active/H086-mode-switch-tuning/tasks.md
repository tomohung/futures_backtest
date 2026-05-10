# Tasks: Mode 1 / Mode 2 切換規則調校

## Phase 1: 規則網格搜尋

### Step 1.1：規則參數定義
- [ ] blue_streak 門檻：{0（current 月 藍/黃藍 即可）, 1, 2, 3, 4, 6}
- [ ] econ_score 門檻直接版：{17（藍燈以下）, 23（黃藍以下）}
- [ ] 250MA below 持續天數：{0（單日即可）, 5, 10, 20, 60}
- [ ] 邏輯組合：{AND, OR, EITHER（任一達極端版）}

### Step 1.2：每組規則的 confusion matrix
- [ ] 載入 H084 的 fuse_state.csv（或 indicators.csv 重算）
- [ ] 對每組規則計算：
  - Tier A days 中觸發 Mode 2 的比例（recall）
  - Bull days 中觸發 Mode 2 的比例（FPR）
  - Tier B/C 內觸發 Mode 2 的比例（理想：B 比 C 高）
  - 規則切換 lag（從 Tier A 進入到首次觸發 Mode 2 的天數）

### Step 1.3：Pareto frontier 視覺化
- [ ] 散點圖：x = bull FPR, y = Tier A recall，每組規則一點
- [ ] 標記理想象限（左上：高 recall + 低 FPR）
- [ ] 識別 frontier 上的「次優」規則群

### Step 1.4：In-sample / Out-of-sample 切分
- [ ] In-sample：2008-2018（含 2008-2014 Tier A）
- [ ] Out-of-sample：2019-2026（含 2022-2024 Tier A）
- [ ] 比較最佳規則在 IS vs OOS 的表現一致性

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
