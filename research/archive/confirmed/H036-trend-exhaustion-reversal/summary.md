# Archive: 趨勢竭盡反轉

## Status
Confirmed

## Summary
趨勢延伸到極端（30 分 K BB%B(open) > 1 或 < 0）+ 夜盤創近二日新高/低後，日盤 ORB 反向突破進場做反轉。搭配跳過週三四 + ORB% >= 0.25% 濾網，IS PF=1.08, OOS PF=1.70。已建立為 S003-exhaustion 策略。

## Key Evidence
- Phase 1：破 ORB 後反轉勝率 56.3%（基準 51.8%），oc% +0.10%
- Phase 2（最終配置）：N=91, PF=1.34, IS=1.08, OOS=1.70
- 實盤驗證：2026-03 共 4 筆交易，全部獲利（+1,028pt）
- 週一效果特別好（PF=1.50），寬 ORB 和 BB%B 越極端效果越好

## Why Confirmed
IS 勉強正（PF=1.08）但方向正確，OOS 強（PF=1.70），且有 4 筆實盤獲利驗證。策略邏輯有清楚的市場直覺（趨勢極端後的均值回歸），不是純粹的數據挖掘。

初版回測因週末夜盤對齊 bug 導致結論為 Rejected，修正後翻正——這也說明正確的資料處理對回測結論的重要性。

## Derived Hypotheses
- H0XX-weekday-gap-interaction：非週一需要大跳空才有反轉動力
- H0XX-exhaustion-fail-continuation：竭盡反轉被停損 → 反手做趨勢延續

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md
- Live Strategy：strategies/live/S003-exhaustion/
