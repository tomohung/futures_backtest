# Tasks: NVF Method Upgrade (Production)

## Phase 1: Distribution Research

### Task 1: Expanding median trajectory 分析
- [x] SMA + EMA expanding median 計算
- [x] **Trajectory 極穩定**：EMA 過去 4 年都在 0.92–0.94，月度變動 ±0.005
- [x] 2026 Q1 vol 暴漲下 EMA exp_med 只動 +0.004
- [x] H066 confirm 日 EMA exp_med = 0.935

### Task 2: 4 方法 aggregate 對比
- [x] **EMA + exp_med 全面最佳**：EstHL diff +93.9%, Reversal +74.1%
- [x] HIGH PF：EstHL 2.07 → 2.68 (+30%), Reversal 1.35 → 1.57 (+16%)

### Task 3: Walk-forward 年度一致性
- [x] **EMA + exp_med EstHL 6/6 完美**（唯一）
- [x] Reversal 4/6（並列最佳）

### Task 4: 連敗結構（最高優先）
- [x] **重大發現：current prod (SMA+0.85) 把 EstHL max_streak 從 baseline 6 推到 9**
- [x] EMA + exp_med EstHL max_streak 9→7（**−2 筆**），worst_pnl -378→-270 (改善 28.6%)
- [x] EMA + exp_med Reversal max_streak 持平 7，worst_pnl -404→-338 (改善 16.3%)
- [x] **invalidation 通過**：max streak 改善而非惡化

### Task 5: 2026 Q1 高 vol regime
- [x] EMA + exp_med 在 EstHL Q1 通過率 33% (vs prod 53%)，PF 5.35 (vs 3.57)
- [x] 樣本太小（< 17）但方向對

### Task 6: 實作可行性
- [x] 計算成本 <1ms，無風險
- [x] Warmup 60 夜盤值，目前已有 1167 個有效計算日
- [x] 修改範圍：僅 `src/analysis/key_prices.py`

---
### GATE
**問題：是否進入 Phase 2 升級實盤？**

- 候選方法的 walk-forward PF ≥ 5/6 年贏 baseline？
- 連敗 max length 持平或改善？
- expanding median trajectory 平滑（無 step jump）？
- 實作可行（每天重算 median 在 pipeline 內可承受）？

**判斷分支：**
- 全部 ✓ → Phase 2 改 production
- 連敗惡化 → Archive Rejected（保護心理資本優先）
- PF 不夠穩定 → Archive Inconclusive（持續觀察）
- 實作不可行 → 改用 fixed 接近 median 的數字（如 0.93），重新驗證

**決定：** [ ] 進 Phase 2　[ ] Archive　[ ] 修改假設後重跑

**Phase 1 結果（2026-04-21）**：
- EMA + exp_med 在 PF / Walk-forward / 連敗 / 自適應 全面最佳
- 連敗保護**改善**而非惡化（EstHL −2 筆）
- Trajectory 過去 4 年穩定在 0.92-0.94
- 實作可行性 0 風險

詳見 `results/distribution.md`。等 GATE 裁示。

---

## Phase 2: Production Upgrade（GATE 通過後）

- [ ] 修改 `src/analysis/key_prices.py:_compute_night_vol_filter`
- [ ] 加 unit tests（causal expanding median 行為）
- [ ] 更新 morning_briefing 顯示邏輯
- [ ] 跑完整端對端 backtest，確認與 research 結果一致
- [ ] 更新 H066/H067 archive summary（注記方法升級）
- [ ] 更新 strategies/live/S001/S002 spec
- [ ] 回 H072 重新評估 sub-cell drift（看新方法是否仍有 EstHL Tue 失效）
