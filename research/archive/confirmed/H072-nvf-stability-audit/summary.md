# Archive: NVF Stability Audit by Weekday × Strategy × Period

## Status
Confirmed（**多數 patches 已由 H075 自動修復；剩 EstHL Tue 仍需獨立 patch**）

## Summary
H071 偶然發現 EstHL × Tue × 2024–2025 NVF 失效，本研究系統性切片 (strategy × weekday × year) 三維 cell matrix 全面審查 NVF 穩定性。發現 19 個反向 cell + 4 個 IS→OOS drift cell，且 NVF aggregate 訊號從 H066/H067 confirm 時的 +83%/+64% 衰減到 +19.5%/+29.5%。後續 H073 釐清「衰減」是方法學差異（H066 用 EMA+median，H072 用 SMA+0.85），H075 升級 production 為 EMA + expanding median 後**自動修復了 Reversal Wed/Thu 兩個 drift cell**。剩餘 **EstHL × Tue × NVF 是結構性失效**（無論哪種方法 OOS Δ 都 ≈ -1.2），仍需獨立 patch。

## Key Evidence

### 反向 cell（baseline ΔPF < 0 且 NVF N ≥ 5）
- 19 個（EstHL 5、Reversal 10、Exhaustion 4）

### IS vs OOS drift cells（IS NVF positive, OOS negative）
- EstHL Mon: IS Δ +2.38 → OOS -0.11
- **EstHL Tue: IS Δ +0.68 → OOS -1.24 (嚴重)**
- Reversal Wed: IS Δ +0.21 → OOS -0.12（H075 已修復）
- Exhaustion Thu: IS Δ +0.25 → OOS -0.80

### EstHL Tue rolling 2-year ΔPF（單調惡化）
+0.76 → +0.22 → -0.46 → -1.04 → **-1.65**（5 視窗）

### Threshold sweep — EstHL Tue 不可救
| Threshold | 0.70 | 0.85 | 1.00 | 1.15 |
|-----------|------|------|------|------|
| EstHL Tue OOS Δ | -0.88 | -1.24 | -1.63 | **-1.85** |
越高門檻越糟，與其他 cell 反向。

### Exhaustion control 對照
- EstHL Mon/Tue：同 OOS 期間 Exhaustion NVF Δ 反向為正 → **EstHL 策略特性問題**，非市場結構

### H075 升級後的 OOS Δ 變化
| Cell | 舊方法 | 新方法 | 結論 |
|------|--------|--------|------|
| EstHL Tue | -1.24 | -1.22 | ❌ 結構性失效，新方法救不回 |
| Reversal Wed | -0.12 | +0.99 | ✓ FIXED by H075 |
| Reversal Thu | -0.17 | +0.08 | ✓ FIXED by H075 |
| Reversal Mon | +0.32 | -0.01 | ≈ 持平 |

## Why Confirmed
1. Sub-cell drift 確實存在（19 個反向 cell + 4 個 drift cell），不是噪音
2. EstHL Tue 失效跨 measurement method（SMA/EMA、fixed/median）一致
3. Exhaustion control 排除「市場結構問題」假設，確認 EstHL 策略特性
4. H075 升級後**多數 patches 自動 cover**，剩 EstHL Tue 是真正需要獨立處理的

## Phase 2 patches 最終狀態
| 原 H072 patch | 處理方式 |
|----------------|----------|
| EstHL Tue 移除 NVF | **❌ 仍待執行**（H078 候選） |
| EstHL Fri 移除 NVF | n/a — production 已 skip Fri |
| Reversal Wed 改門檻 | ✓ 由 H075 自動修復 |
| Reversal Thu 移除 NVF | ✓ 由 H075 自動修復 |
| Exhaustion 不加 NVF | ✓ 確認（非 live 策略） |

## Derived Hypotheses
- **H073（confirmed）**：NVF aggregate 衰減驗證——確認為方法學差異而非 regime drift
- **H075（confirmed）**：NVF 方法升級到 EMA + expanding median——已實作 production
- **H078 候選（待執行）**：EstHL Tue NVF 移除 patch。雙重證實結構性失效，需在 EstHL 策略碼或 morning_briefing 加 weekday-specific bypass。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Visualisations：results/h072_t2_heatmap.png, h072_t3_rolling.png, h072_t5_threshold_sweep.png
- Explore script：explore.py
