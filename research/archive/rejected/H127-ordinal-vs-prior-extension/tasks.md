# Tasks: 序數 vs 前置延伸 — L2 拉回續攻 edge 的真正 driver

## Phase 1: Distribution Research

- [x] 重用 H126 detect_day 進場集合，對每筆新增 causal `prior_run_L`（open-anchored 同向已走幅度）
- [x] 備援欄位：進場前是否已有同向 phase 達 ≥L2 / ≥L3（以關卡計的離散前置延伸代理）
- [x] 單變量：forward L4/L5 reach vs `prior_run_L` 分桶（看單調性）
- [x] 雙向分層：序數(1st/2nd+) × `prior_run_L` 分桶 → 看「同 prior 分層內序數是否還分得開」
      與「同序數內 prior 是否還分得開」（哪個 survive 條件化）
- [x] 限定 H126 的 edge 窗 entry∈[09:30,11:30] 重跑分層（避免尾盤死區稀釋）
- [x] logistic：reach_L4 ~ ordinal + prior_run_L + entry_min，比較邊際/係數，三方互證
- [x] 視覺化：reach vs prior_run 曲線、序數×prior 熱圖

---
### GATE
**問題：driver 歸因是否清楚到能定義 Phase 2 進場條件？**

- `prior_run_L` 分層 N 是否足夠（edge 窗內每 cell ≥ 一定樣本，門檻待 Phase 1 給數）？
- 控制 prior_run 後序數增量是否消失（H127 成立）／仍在（H127 拒、序數乾淨）？
- 是否可分？若不可分（兩者皆顯著且互不涵蓋）→ Inconclusive，Phase 2 併用。

**決定：** [ ] 繼續 Phase 2（用勝出的 driver 設計進場）　[ ] Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest（視 GATE 結論定義）
> 若 driver = 前置延伸：進場條件改用連續「prior_run_L 門檻」（涵蓋第一次但已延伸的日子）。
> 若 driver = 序數：沿用 H126「2nd+」離散旗標，回到 H126 Phase 2。
> 若不可分：兩條件併用，回測比較三種進場定義的淨 EV。

- [ ] 依勝出 driver 定義進出場規則
- [ ] in-sample / out-of-sample / walk-forward
- [ ] 對照 H126 「2nd+」基準，量化前置延伸定義的增量
