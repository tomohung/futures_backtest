# Tasks: NVF Aggregate Signal Decay Verification

## Phase 1: Distribution Research

### Task 1: Aggregate baseline 重現（固定 0.85）
- [x] H072 數字重現：EstHL +19.5%, Reversal +29.5%, Exhaustion -12.5% ✓

### Task 2: Median split 方法重做
- [x] SMA+median: EstHL +15.3%, Reversal +50.7%
- [x] **EMA+median (H066 真實方法): EstHL +73.6%, Reversal +84.0%**
- [x] 重現 H066 +83.6%、H067 +64.3% 的核心數字（差距 < 14pp 屬合理波動）

### Task 3: H066 confirm 日 cutoff 重現
- [x] 三策略 trades 100% 都在 cutoff 之前，cutoff 與 full data 結果一致

### Task 4: Expanding window
- [x] 21 個 cutoff 點（2025-12 ~ 2026-04）
- [x] **2026-04-13 EstHL EMA+median = +83.6% 精確匹配 H066**
- [x] 全區間波動 60-84%，無 step change
- [x] h073_t4_expanding.png

### Task 5: 演算法 cross-check
- [x] H066 用 EMA+median，H067 用 SMA+median，H072 用 SMA+0.85（**三者皆不同**）
- [x] **副發現：實盤 (key_prices.py) 用 SMA+0.85，與 H066 評估方法不同**

---
### GATE
**問題：H072 的 baseline 是否健康？**

- median split 後 EstHL aggregate diff ≥ 60%？
- 截至 2026-04-17 cutoff 數字與 H066/H067 一致（差距 < 20%）？
- expanding window 沒有 step change？

**判斷分支：**
- 三項皆 ✓ → **方法學差異，H066/H067 健康**，H072 sub-cell 結論成立
- median split 後仍 < 40% → **真實 drift**，開 H075 重審 NVF
- pipeline 數字不一致 → **資料 bug**，必先修復

**決定：** [ ] H072 sub-cell 結論成立，回 H072 GATE　[ ] 開 H075 NVF 重審　[ ] 修 pipeline bug

**Phase 1 結果（2026-04-21）**：
- 用 H066 真實方法（EMA+median）跑 EstHL = **+73.6%**（H066 報告 +83.6%）→ 方法學差異論證實
- expanding window 顯示 2026-04-13 EstHL EMA+median = +83.6% 精確匹配 H066
- 副發現：實盤 NVF（SMA+0.85）= +19.5%，比 H066 評估的 EMA+median（+73.6%）弱 4×

詳見 `results/distribution.md`。

---

## Phase 2
（純除錯研究，原則上無 Phase 2。Verdict 後直接回 H072 或開新假設）
