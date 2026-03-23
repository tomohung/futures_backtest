# Archive: EstHL OR 量比調整 — 用開盤量縮放預估振幅

## Status
Confirmed

## Summary
EstHL 用 EMA(20) 預估當日波幅，但每天給同一個值，無法區分活躍日與清淡日。研究發現 OR 段量比（08:45-09:30 成交量 / 20 日 OR 均量）與日波幅高度相關（r=+0.469），用公式 `EstHL_adj = EmaHL x (alpha + (1-alpha) x OR_vol_ratio)` 調整後，MAE 從 72 降到 63（改善 12.5%），SatZone 精準度從 55% 升到 61%，策略 PF 從 2.38 升到 2.71（+14%）。

## Key Evidence
- OR 量比 vs 日波幅 Pearson r = +0.370；vs (日波幅/EmaHL) r = +0.469
- 靜態分析最佳 alpha=0.3（MAE 72->63），策略回測最佳 alpha=0.5（PF 2.38->2.71）
- EstHL 策略（alpha=0.5）：134 筆，勝率 59.0%，total +4,349（原始 +3,631，+20%）
- 每一年都改善或持平，無任何年度惡化：2021 +128->+319, 2024 +1301->+1386, 2026 +402->+808
- 交易次數不變（134 筆），僅改善出場 SatZone 精準度
- SatZone 精準度：zone 內% 55.2%->61.6%，偏低率 13.5%->8.1%

## Why Confirmed
alpha=0.5 在所有年度（2021-2026）均改善或持平，PF +14%、total +20%，且只有一個參數（過擬合風險低）。OR 量比在 09:30 已知，無 lookahead，物理意義明確（成交量與波幅正相關）。

## Derived Hypotheses
- Reversal 策略同步受益（也使用 EstHL 的 SatZone 出場）
- Portfolio 配置可能需重新計算（EstHL 績效改善後權重變化）

## Links
- Proposal: specs/strategies/2026-03-15-esthl-or-volume-adjustment.md
