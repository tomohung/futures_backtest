# Archive: Night Session Volatility as EstHL Filter

## Status
Confirmed

## Summary
前一晚夜盤振幅（SMA20 正規化）可有效區分 EstHL 績效：高波動夜盤後的日盤交易品質顯著優於低波動夜盤。作為現有星期濾網（skip Thu+Fri）的補充層，在不改動星期邏輯的前提下過濾低波動日，Config D（skip TF + night_norm ≥ 0.85）OOS PF 從 2.67 提升至 3.46。

## Key Evidence
- Phase 1 中位數分割：HIGH vol PF=2.44 vs LOW vol PF=1.33（差異 83.6%），跨年一致 6/6（N=241）
- Config D IS/OOS：IS PF=3.02, OOS PF=3.46（SMA20, thr=0.85）
- 門檻穩定區間 0.85–0.95，IS/OOS 均 PF > 2.0
- EMA/SMA 相關 r=0.985，結果一致；採用 SMA 以求直覺

## Why Confirmed
1. 分組區分力強且跨年穩定（6/6 年高組勝低組）
2. IS/OOS 一致性佳（Config D PF 差 Δ < 0.5）
3. 門檻對參數不過度敏感（0.85–0.95 均可）
4. 實作簡單——盤前即可計算，不影響現有策略邏輯

注意：Walk-forward 中 Night HIGH only 贏基線僅 2/5 年，單獨無法取代星期濾網。定位為「補充層」而非「取代」。

## Derived Hypotheses
- H067：週四改用夜盤波動門檻取代全面跳過（Config C，已驗證可行但未採用）
- H068：Q2 死區（night_norm 略低於 median）結構性原因
- H069：週五弱勢的非夜盤波動因素探索

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md
- Explore script：explore.py
- Backtest script：backtest.py
