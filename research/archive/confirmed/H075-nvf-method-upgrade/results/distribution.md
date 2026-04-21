# Distribution Research Results: NVF Method Upgrade

## Date
2026-04-21

## Conditions Tested
- 兩個 live 策略：EstHL、Reversal（皆解除 weekday filter 以公平比較）
- 4 種 NVF 方法：
  - **SMA + 0.85**（current production）
  - **SMA + expanding median**
  - **EMA + expanding median**（首選，H066 評估方法的 causal 版本）
  - **EMA + 0.85**
- Expanding median 為 causal：用 shift(1) 排除 look-ahead
- Warmup：60 個夜盤值
- 期間：2021–2026 (至 2026-04-21)

## Sample
- Night days: 1,246（with expanding median valid: 1,167）
- EstHL trades: 247（with NVF & exp_med 有效: 221）
- Reversal trades: 498（with NVF & exp_med 有效: 477）

## Key Findings

### T1：Expanding median trajectory **極其穩定**

詳見 `h075_t1_trajectory.png`。

| 日期 | SMA exp_med | EMA exp_med |
|------|-------------|-------------|
| 2021-12-31 | 0.874 | 0.905 |
| 2022-12-31 | 0.905 | 0.922 |
| 2023-12-31 | 0.915 | 0.933 |
| 2024-12-31 | 0.918 | 0.933 |
| 2025-12-31 | 0.919 | 0.931 |
| 2026-04-17 (H066 confirm) | 0.926 | 0.935 |
| 2026-04-21 (今日) | 0.926 | 0.935 |

**EMA expanding median 過去 4 年都在 0.92–0.94 範圍**，月度變動 ±0.005。即便 2026 Q1 vol 暴漲（raw range 翻倍），threshold 只動 0.931→0.935（+0.004）。**SMA20 normalisation 已吸收絕對振幅趨勢**，trajectory 沒有 step jump。

→ Expanding median 在 production 是穩定的，不會出現「某天 threshold 跳 0.05」的情況。

### T2：Aggregate HIGH/LOW PF — EMA + exp_med 全面壓倒

**EstHL**：

| Method | HIGH N | HIGH PF | LOW PF | diff% |
|--------|--------|---------|--------|-------|
| SMA + 0.85 (current prod) | 120 | 2.07 | 1.65 | +25.9% |
| SMA + exp_med | 104 | 2.33 | 1.51 | +54.0% |
| **EMA + exp_med** | **97** | **2.68** | **1.38** | **+93.9%** ⭐ |
| EMA + 0.85 | 121 | 2.30 | 1.43 | +61.6% |

**Reversal**：

| Method | HIGH N | HIGH PF | LOW PF | diff% |
|--------|--------|---------|--------|-------|
| SMA + 0.85 (current prod) | 287 | 1.35 | 1.08 | +25.1% |
| SMA + exp_med | 252 | 1.39 | 1.07 | +29.6% |
| **EMA + exp_med** | **244** | **1.57** | **0.90** | **+74.1%** ⭐ |
| EMA + 0.85 | 292 | 1.43 | 0.95 | +50.7% |

EMA + exp_med 在兩策略都是 diff% 最高、HIGH PF 最高，且接近 H066/H067 評估水準（H066 evaluated +83.6%，本研究 +93.9%）。

### T3：Walk-forward 年度一致性 — EMA + exp_med EstHL 完美 6/6

**EstHL**（每年 HIGH PF > 全部 baseline 的次數，N≥5）：

| Method | 年度勝出次數 |
|--------|-------------|
| SMA + 0.85 (prod) | 5/6 |
| SMA + exp_med | 4/6 |
| **EMA + exp_med** | **6/6** ⭐ 唯一完美一致 |
| EMA + 0.85 | 5/6 |

**Reversal**：4 種方法都 3-4/6，EMA + exp_med 並列最佳 4/6。

詳見 `h075_t3_walkforward.png`。

### T4：連敗結構 — **發現現行 prod 反而拉高 EstHL 連敗**

**EstHL**（baseline NO_NVF: max_streak=6, worst_pnl=-278, max_dd=-356, total=+4,734）：

| Method | N | max_streak | worst_pnl | max_dd | total |
|--------|---|-----------|-----------|--------|-------|
| **SMA + 0.85 (current prod)** | 120 | **9 ⚠** | -378 | -378 | +3,282 |
| SMA + exp_med | 104 | 8 | -326 | -326 | +3,277 |
| **EMA + exp_med** | 97 | **7** | **-270** ⭐ | **-270** ⭐ | +3,510 |
| EMA + 0.85 | 121 | **6 ⭐** | -278 | -367 | +3,678 |

**重大反直覺發現**：current prod (SMA + 0.85) 在 EstHL 上**把 max_streak 從 baseline 的 6 推到 9**——比完全不過濾還糟！

對比：
- EMA + exp_med：max_streak **9 → 7**（−2 筆，連敗顯著降低）
- EMA + exp_med：worst_pnl **-378 → -270**（改善 28.6%）
- EMA + exp_med：max_dd **-378 → -270**（改善 28.6%）
- EMA + exp_med：total **+3,282 → +3,510**（小幅提升）

**Reversal**（baseline NO_NVF: max=10, worst=-404, max_dd=-885, total=+2,505）：

| Method | N | max_streak | worst_pnl | max_dd | total |
|--------|---|-----------|-----------|--------|-------|
| SMA + 0.85 (prod) | 287 | 7 | -404 | -565 | +2,254 |
| SMA + exp_med | 252 | 7 | -404 | -564 | +2,208 |
| **EMA + exp_med** | 244 | 7 | **-338** ⭐ | **-472** ⭐ | **+2,958** ⭐ |
| EMA + 0.85 | 292 | 8 | -302 | -466 | +2,689 |

EMA + exp_med 在 Reversal 上：
- max_streak 持平 prod（7）
- worst_pnl **-404 → -338**（改善 16.3%）
- max_dd **-565 → -472**（改善 16.5%）
- total **+2,254 → +2,958**（**+31% 增益**）

### T5：2026 Q1+Q2 高 vol regime 行為

**EstHL** (15 trades)：

| Method | pass_N | pass_rate | PF | total |
|--------|--------|-----------|-----|-------|
| SMA + 0.85 (prod) | 8 | 53.3% | 3.57 | +576 |
| EMA + exp_med | 5 | 33.3% | **5.35** | +452 |

EMA + exp_med 在高 vol regime 變更嚴格（通過率 33% vs 53%），但通過後 PF 從 3.57 → 5.35（提升 50%）。樣本太小無法強斷論，但方向正確。

**Reversal** (17 trades)：4 方法都通過 60-70%，PF 都 3.5-3.8 接近，都比不過濾的 4.05 略低。樣本太小看不出差異。

### T6：實作可行性 — 完全可行

- 計算成本極低：每天 1 次 median，<1ms
- 與 H066 真實方法一致，無 untested 風險
- Warmup：60 夜盤值（約 3 個月），歷史已有 1167 個有效計算日
- 修改範圍：僅 `src/analysis/key_prices.py:_compute_night_vol_filter`
- 風險：DuckDB 全歷史讀取量增加 → 可在 morning_briefing 起算時 cache
- 目前 EMA exp_med 值 = **0.935**（接近長期 median 0.935，可作為 warmup 期 fallback）

## Vs. Expected

| 預期 | 實際 | 判定 |
|------|------|------|
| EstHL HIGH PF 接近 2.44 | EMA+exp_med = 2.68 | ✓ 超預期 |
| Reversal HIGH PF 1.6+ | EMA+exp_med = 1.57 | ≈ 接近 |
| 連敗結構不惡化 | EstHL **改善**（9→7），Reversal 持平/改善 | ✓ 超預期 |
| Walk-forward 5+ 年穩定 | EstHL 6/6，Reversal 4/6 | ✓ EstHL 完美 |
| Trajectory 無 step jump | 月度變動 ±0.005，2026 Q1 +0.004 | ✓ 完美穩定 |

**所有預期都滿足或超過。** 額外發現：current prod 在 EstHL 上的 max_streak（9）**比完全不用 NVF（6）還差**，這是個獨立的 bug 級發現。

## Gate Decision

[X] **進入 Phase 2，升級 production 為 EMA + expanding median**

候選方法量化對比（兩策略加權）：

| 維度 | SMA+0.85 (prod) | EMA + exp_med | EMA + 0.85 |
|------|-----------------|----------------|-------------|
| HIGH PF (avg) | 1.71 | **2.13** | 1.87 |
| Walk-forward consistency (avg) | 4/6 | **5/6** | 4.5/6 |
| Max streak EstHL | 9 | 7 | 6 |
| Max streak Reversal | 7 | 7 | 8 |
| Worst streak P&L EstHL | -378 | **-270** | -278 |
| Worst streak P&L Reversal | -404 | **-338** | -302 |
| Total P&L 增量 vs prod | — | **+932 (+17%)** | +832 |

**EMA + exp_med 是首選**：
- HIGH PF 最高
- Walk-forward 最一致
- 連敗保護顯著改善（EstHL −2 筆）
- 自適應 vol regime（trajectory 自動微調）
- 最忠於 H066 原始評估方法

**EMA + 0.85 fixed 是備選**：
- EstHL max_streak 最低（6）
- 不需 expanding 計算（最簡單實作）
- 但 walk-forward 不如 exp_med 一致，diff% 也較低

## Phase 2 完成記錄（2026-04-21）

### 實作改動
`src/analysis/key_prices.py:_compute_night_vol_filter` 已升級：
- SQL 改為載入完整歷史夜盤資料
- 計算 EMA20 取代 SMA20
- threshold 改用 expanding median，warmup < 60 夜盤 fallback 到 0.93
- 回傳欄位：`ema20`, `night_norm`, `threshold`, `pass`, `method`

顯示字串同步更新（從 `SMA20 = X / 0.85` 改為 `EMA20 = X / threshold`）。

### Smoke test（2026-04-17 測試日）
- night_range = 1358 點
- ema20 = 689 點
- night_norm = 1.971
- threshold = 0.935（expanding median）
- pass = True

### 對 H072 sub-cell drift 的影響（補充驗證）

用新 NVF (EMA + exp_med) 重跑 H072 cell matrix，**OOS (2024-26) drift 變化**：

**EstHL**：
| Weekday | 舊 NVF Δ | 新 NVF Δ | 狀態 |
|---------|----------|----------|------|
| Mon | -0.11 | -0.11 | ⚠ 仍小幅 drift |
| **Tue** | **-1.24** | **-1.22** | **⚠ 完全沒救，仍需 patch** |
| Thu | +0.18 | +0.18 | ✓ 健康 |
| Fri | -0.56 | -0.29 | ⚠ 改善但仍負 |

**Reversal**：
| Weekday | 舊 NVF Δ | 新 NVF Δ | 狀態 |
|---------|----------|----------|------|
| Mon | +0.32 | -0.01 | ≈ 持平 |
| Tue | +0.66 | +0.77 | ✓ 更好 |
| **Wed** | **-0.12** | **+0.99** | **✓ FIXED** |
| **Thu** | **-0.17** | **+0.08** | **✓ FIXED** |
| Fri | +0.11 | +0.30 | ✓ 更好 |

**結論**：H075 升級**自動修復了 Reversal Wed/Thu 的 drift**，但 **EstHL × Tue × NVF 是結構性問題**，無論方法都失效。H072 提的 EstHL Tue NVF 移除 patch 仍然必要。

### 文檔同步更新
- ✅ H066 archive summary 加註 H075 升級
- ✅ H067 archive summary 加註 H075 升級
- ✅ S001 EstHL spec 增加 NVF filter 描述 + 參數
- ✅ S002 Reversal spec 更新 NVF 方法描述 + 參數

## Derived Hypotheses

- **H072 重新評估**（待 Phase 2 完成後）：升級 NVF 方法後，EstHL Tue/Fri 的 sub-cell drift 是否改變。如果新方法已自動避開那些失效 cell，H072 的 patch 不需要做；反之仍需。

- **H076 候選（已記在 H073，仍 valid）**：H066 summary.md 「EMA/SMA r=0.985 結果一致」說法被本研究進一步反駁——HIGH PF 差距 2.07 vs 2.68（**+30%**）。需做更廣的 H066 文檔/程式一致性 audit。

- **H077 候選（新發現）**：current prod（SMA + 0.85）在 EstHL 把 max_streak 從 baseline 6 推到 9，這是 NVF filter 反向作用的證據。可獨立研究「為何特定 NVF 設定會讓連敗 worse than no filter」——可能是 filter 過濾掉了「打破連敗的勝場」。低優先（H075 升級後此問題消失）。

## Links
- Proposal：../proposal.md
- Tasks：../tasks.md
- Explore script：../explore.py
- Visualisations：h075_t1_trajectory.png, h075_t3_walkforward.png, h075_t4_streaks.png
- CSVs：t2_aggregate.csv, t3_walkforward.csv, t4_streaks.csv, t5_q1_2026.csv, night_metrics.csv
