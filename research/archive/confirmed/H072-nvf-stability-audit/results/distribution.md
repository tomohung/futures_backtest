# Distribution Research Results: NVF Stability Audit

## Date
2026-04-21

## Conditions Tested
- 三策略：EstHL、Reversal、Exhaustion（皆解除 weekday filter）
- night_norm = night_range / SMA20（與 H066/H067 一致）
- NVF 主門檻 = 0.85；sweep = 0.70 / 0.85 / 1.00 / 1.15
- 期間：2021–2026 (至 2026-04-21)
- IS = 2021–2023, OOS = 2024–2026
- Cell 樣本門檻：N ≥ 5 才標記為「反向 cell」

## Sample
- EstHL trades: 247（with NVF: 235）
- Reversal trades: 498（with NVF: 483）
- Exhaustion trades: 134（with NVF: 131）
- Cell 總數（strategy × weekday × year）：3 × 5 × 6 = 90
- 有效 cell（baseline N ≥ 1）：約 75

## Key Findings

### T1：NVF Aggregate 訊號已大幅衰減

| Strategy | 本研究 (2026-04-21) | H066/H067 confirm 時 | 衰減 |
|----------|----------------------|------------------------|------|
| EstHL    | HIGH 2.10 / LOW 1.75, **+19.5%** | HIGH 2.44 / LOW 1.33, **+83.6%** | **−4.3×** |
| Reversal | HIGH 1.39 / LOW 1.08, **+29.5%** | HIGH 1.58 / LOW 0.96, **+64.3%** | **−2.2×** |
| Exhaustion | HIGH 0.94 / LOW 1.08, **−12.5%** | （未測） | — |

**重大發現**：NVF 訊號在僅 4 天前的 confirm 與本研究之間就已大幅衰減（用了相同方法、僅樣本期間略有更新）。差異主要來自 H066/H067 用 median split 而本研究用固定 0.85，但即便調整方法差異，**訊號強度從 2× 變成 < 1.3× 是明顯的 regime drift**。

**Exhaustion 對 NVF 是負向的**（−12.5%）——若實盤用 NVF 過濾 Exhaustion 反而會虧。

### T2：Cell Matrix（strategy × weekday × year）

詳見 `h072_t2_heatmap.png`。三 strategy 各 5×6 cell 矩陣，色階 = ΔPF (NVF − baseline)：

**反向 cell 統計（ΔPF < 0 且 NVF N ≥ 5）：共 19 個**

| Strategy | 反向 cell 數 | 主要 cell |
|----------|-------------|-----------|
| EstHL    | 5 | Tue 2025 (Δ=-1.26), Mon 2024 (Δ=-4.69), Fri 2024 (-0.52), Fri 2025 (-0.03), Thu 2025 (-0.15) |
| Reversal | 10 | Tue 2022 (-0.93), Wed 2024 (-0.86), Thu 2025 (-0.42)，多為小幅度 |
| Exhaustion | 4 | Fri 2022 (-1.26), Tue 2025 (-0.83), Wed 2022 (-0.59), Mon 2022 (-0.43) |

EstHL 反向 cell 集中在 **Tue/Fri 的 2024–2025**，與 H071 發現完全一致。

### T3：Rolling 2-Year — EstHL Tue 呈「單調惡化」

詳見 `h072_t3_rolling.png`。EstHL Tue 是 5 個視窗中**唯一單調下滑**的 cell：

| Window | EstHL Tue ΔPF | 解讀 |
|--------|---------------|------|
| 2021-22 | **+0.76** | 正向（H066 confirm 期間） |
| 2022-23 | +0.22 | 弱正向 |
| 2023-24 | -0.46 | **轉負** |
| 2024-25 | -1.04 | 加深惡化 |
| 2025-26 | **-1.65** | **最深** |

EstHL Fri 全 5 視窗都是負/零（NVF 對 EstHL Fri 從來沒真正起作用過）。

Reversal/Exhaustion 沒有單一 cell 出現這種持續單調的惡化模式。

### T4：IS vs OOS — 4 個 DRIFT cell

| Strategy | Weekday | IS Δ (N) | OOS Δ (N) | 嚴重度 |
|----------|---------|----------|-----------|--------|
| EstHL    | Mon | +2.38 (13) | -0.11 (9)  | 輕度 |
| **EstHL** | **Tue** | **+0.68 (18)** | **-1.24 (12)** | **嚴重** |
| Reversal | Wed | +0.21 (30) | -0.12 (26) | 輕度 |
| Exhaustion | Thu | +0.25 (10) | -0.80 (9)  | 嚴重（但 Exhaustion 不用 NVF） |

EstHL Tue 是 OOS NVF 失效最嚴重的 cell（從 +0.68 跳到 -1.24），且 OOS 樣本足夠（N=12）。

### T5：門檻 Sweep — 哪些 Cell 可被救？

詳見 `h072_t5_threshold_sweep.png`。

| Cell | 0.70 | 0.85 | 1.00 | 1.15 | 結論 |
|------|------|------|------|------|------|
| **EstHL Tue OOS** | -0.88 | -1.24 | -1.63 | **-1.85** | **無解，越高越糟** |
| EstHL Fri 2024-26 | -0.38 | -0.56 | -0.45 | -0.18 | 無解 |
| EstHL Mon OOS | -0.34 | -0.11 | -0.43 | **+0.76** | 1.15 救得回（N=6 偏小） |
| Reversal Mon 2024-26 | +0.06 | +0.32 | +0.03 | +0.05 | 全可用 |
| Reversal Wed OOS | +0.15 | -0.12 | -0.09 | -0.58 | 改用 0.70 較好 |
| Reversal Thu 2024-26 | +0.02 | -0.17 | -0.24 | +0.76 | 雙峰，0.70 或 1.15 |
| Reversal Fri 2024-26 | +0.06 | +0.11 | +0.02 | +0.34 | 全可用，1.15 最佳 |
| Exhaustion Thu OOS | -0.80 | -0.80 | -1.07 | -1.06 | 無解 |

### T6：Exhaustion Control — 區分「市場結構 vs 策略特性」

| Cell | OOS NVF Δ | Exhaustion 同 cell OOS NVF Δ | 結論 |
|------|-----------|-------------------------------|------|
| EstHL Mon | -0.11 | **+0.25** | **STRATEGY**（EstHL 特性問題） |
| EstHL Tue | -1.24 | **+1.04** | **STRATEGY**（EstHL 特性問題，最強的策略特性訊號） |
| Reversal Wed | -0.12 | -0.21 (N=5) | MARKET（雙方都負，但 N 很小） |
| Exhaustion Thu | -0.80 | -0.80 | 自身問題 |

→ **EstHL Tue 失效是 EstHL 策略本身的問題**（同 OOS 期間 Exhaustion Tue 的 NVF Δ 是 +1.04，方向完全相反）。不是夜盤波動指標壞了，是 EstHL 在大夜盤波動 + Tue 的組合下進場質量惡化。

## Vs. Expected

| 預期 | 實際 | 判定 |
|------|------|------|
| ≥ 1 個 cell 反向且 N ≥ 5 | 19 個（EstHL 5、Reversal 10、Exhaustion 4） | ✓ 遠超 |
| ≥ 1 個 cell IS 正向 OOS 反向 | 4 個 drift cell | ✓ 符合 |
| 部分 cell 在更高門檻變正向 | EstHL Mon 1.15 救回；Reversal Thu 雙峰；EstHL Tue 完全救不回 | ✓ 部分符合，但**最關鍵的 EstHL Tue 不可救** |

額外未預期發現：
- **NVF aggregate 訊號從 H066/H067 的 +83%/+64% 衰減到 +19.5%/+29.5%**
- **Exhaustion aggregate NVF 是負的（−12.5%）** ← 若曾經想加 NVF 到 Exhaustion，現在已無證據支持
- **EstHL Fri 從歷史看 NVF 從未真正有效**（5/5 rolling window 都負/零）

## Gate Decision

[X] **進入 Phase 2** — 強烈支持，至少 3 個 actionable patch 候選

證據強度：
- 19 個反向 cell + 4 個 drift cell + EstHL Tue 單調惡化 + threshold sweep 顯示無解
- Exhaustion control 確認 EstHL Tue/Mon 是策略特性問題（非市場結構）
- NVF aggregate 訊號衰減到不到當初的 1/3
- 樣本：EstHL Tue OOS N=12（NVF 部分）足以信賴判斷

**Phase 2 建議優先處理**（按 actionable 強度排序）：

1. **EstHL Tue：移除 NVF 條件**（不可救、單調惡化、嚴重 drift、Exhaustion control 證實是 EstHL 特性）
2. **EstHL Fri：移除 NVF 條件**（從未真正有效，5/5 視窗負/零）
3. **EstHL Mon：把 NVF 門檻提高到 1.15** 或維持 0.85（OOS 邊緣，1.15 救回但 N 小，需更多資料）
4. **Reversal：保持現狀**（minor drift 但小幅度，整體仍正向）
5. **Exhaustion：明確不要加 NVF**（aggregate 就是負的）

## Phase 2 / 後續行動（2026-04-21）

### H075 升級 NVF 方法後的 cell drift 變化

H073 揭露 H072 baseline 用的方法（SMA + 0.85）與 H066 評估方法（EMA + median）不一致。H075 升級 production 為 EMA + expanding median 後，重跑 H072 cell matrix：

**EstHL OOS (2024-26) drift 變化**：
| Weekday | 舊方法 OOS Δ | 新方法 OOS Δ | 結論 |
|---------|--------------|---------------|------|
| Mon | -0.11 | -0.11 | 仍小幅 drift（邊緣，可觀察） |
| **Tue** | **-1.24** | **-1.22** | **❌ 結構性失效，新方法救不回** |
| Thu | +0.18 | +0.18 | ✓ 健康 |
| Fri | -0.56 | -0.29 | 改善但仍負（production 已 skip Fri，moot） |

**Reversal OOS drift 變化**：
| Weekday | 舊方法 OOS Δ | 新方法 OOS Δ | 結論 |
|---------|--------------|---------------|------|
| Mon | +0.32 | -0.01 | ≈ 持平 |
| Tue | +0.66 | +0.77 | ✓ 更好 |
| **Wed** | **-0.12** | **+0.99** | **✓ FIXED** |
| **Thu** | **-0.17** | **+0.08** | **✓ FIXED** |
| Fri | +0.11 | +0.30 | ✓ 更好 |

### Phase 2 patches 最終狀態
| 原 H072 patch | 處理方式 |
|----------------|----------|
| EstHL Tue 移除 NVF | **❌ 仍待執行** — 新 NVF 救不回（H078 候選） |
| EstHL Fri 移除 NVF | n/a — production 已 skip Fri |
| Reversal Wed 改門檻 | ✓ 由 H075 自動修復 |
| Reversal Thu 移除 NVF | ✓ 由 H075 自動修復 |
| Exhaustion 不加 NVF | ✓ 確認（非 live 策略） |

## Derived Hypotheses

- **H073 候選：「H066/H067 的 NVF 訊號為何 4 天內就衰減 2-4×」**
  資料只多了幾天但 aggregate diff 從 83% 掉到 19.5%。可能解釋：
  (a) median split vs 固定 0.85 的方法差異（可重做 median split 驗證）
  (b) 2026-Q1 樣本剛好特殊
  (c) 樣本邊界效應
  值得獨立檢查，避免後續所有 NVF 相關研究的基線假設不對。

- **H074 候選：「為何 EstHL Tue 在大夜盤波動下進場質量特別差」**
  Exhaustion control 證實是 EstHL 策略特性問題。可能與 EstHL 在大波動日的 SL/SatZone 邏輯有關。如果找到根因，可能不只 Tue，其他大波動 cell 都能改善。

- **~~H075 候選~~ → 已執行並 confirmed**：NVF 升級為 EMA + expanding median，已修復本研究發現的多數 sub-cell drift。詳見 `research/archive/confirmed/H075-nvf-method-upgrade/`。

- **H078 候選（後續行動）**：EstHL Tue NVF 移除 patch。本研究 + H075 雙重證實 EstHL × Tue × NVF 結構性失效（OOS Δ -1.2，不論方法），需在 production 加 weekday-specific bypass。

## Links
- Proposal：../proposal.md
- Tasks：../tasks.md
- Explore script：../explore.py
- Visualisations：h072_t2_heatmap.png, h072_t3_rolling.png, h072_t5_threshold_sweep.png
- Cell-level data：reverse_cells.csv, drift_cells.csv, threshold_sweep.csv
- Trade-level data：trades_esthl_with_nvf.csv, trades_reversal_with_nvf.csv, trades_exhaustion_with_nvf.csv
