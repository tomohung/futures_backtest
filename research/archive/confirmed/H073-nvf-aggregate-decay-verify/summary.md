# Archive: NVF Aggregate Signal Decay Verification

## Status
Confirmed

## Summary
H072 觀察到的「NVF aggregate 訊號從 H066/H067 confirm 時的 +83.6%/+64.3% 衰減到 +19.5%/+29.5%」**不是 regime drift，是方法學差異**。H066 explore.py 用 EMA20 + median split，H067 用 SMA20 + median split，H072 用 SMA20 + 0.85 fixed——三者都不同。用 H066 真實方法（EMA + median）跑 EstHL 當前資料 = +73.6%，與 H066 報告 +83.6% 差距僅 10pp（合理波動）。重大副發現：**實盤 (`src/analysis/key_prices.py`) 用 SMA + 0.85**，與 H066 評估方法不同，效果只有 H066 評估值的 1/4。

## Key Evidence
- **H066 方法重現**：EMA + median 法跑 EstHL 當前 = +73.6%；2026-04-13 cutoff 精確匹配 H066 +83.6%
- **方法差異拆解（EstHL）**：
  - EMA + median = +73.6%
  - EMA + 0.85 fixed = +37.2%
  - SMA + median = +15.3%
  - SMA + 0.85 fixed = +19.5%（H072 + 實盤方法）
- **Expanding window 無 step change**：2025-12 ~ 2026-04 區間波動 60–84%，無 4 天衰減 4× 的證據
- **Reversal H067 方法重現**：SMA + median = +50.7%（H067 報告 +64.3%，差 13pp）
- **逐年 norm_sma 中位數穩定**（2021–2025: 0.87–0.94），確認 SMA20 normalisation 對絕對振幅的吸收有效；2026 Q1 因 vol regime shift 略飄到 1.061

## Why Confirmed
1. 用 H066 真實方法（EMA + median）跑當前資料能精確重現 H066 報告數字（差 10pp 屬合理波動）
2. Expanding window 顯示 aggregate diff 平緩波動，無 step change
3. 「衰減」全部可由方法差異解釋：EMA→SMA 吃掉 ~37pp、median→0.85 fixed 吃掉 ~15pp
4. 三策略一致顯示方法差異論成立

## Implications
- H072 sub-cell drift 結論成立（H072 內部用一致方法切片）→ 可進 H072 Phase 2 patches
- **實盤 NVF 實作偏弱**：production = SMA+0.85（diff +19.5%），H066 評估 = EMA+median（diff +73.6%）→ 產生 H075（高優先實盤升級候選）
- H066 summary.md「EMA/SMA r=0.985, 結果一致」說法錯誤——PF diff 實際落差 58pp

## Derived Hypotheses
- **H075（高優先）**：實盤 NVF 應升級為 EMA + expanding median 方法。預期 PF/Sharpe/連敗保護全面提升。需驗證：(a) IS/OOS PF 差異 (b) walk-forward 穩定性 (c) 連敗結構 (d) 實作可行性（每日重算 expanding median）。
- H076 候選（低優先 audit）：H066 summary.md 「EMA/SMA 結果一致」說法不正確，應有更廣的文檔/程式一致性 audit。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Visualisation：results/h073_t4_expanding.png
- Explore script：explore.py
