# Archive: Exhaustion 實盤 vs 回測比對

## Status
Rejected

## Summary
比對 S003 Exhaustion 策略的實盤交易（N=57）與程式回測結果，發現兩者本質上是不同策略（filtered 重疊率僅 24.6%）。更重要的是，使用正確的 close 進場回測後，S003 整體 PF 從原本認定的 1.34 降至 1.10，OOS PF=1.00，策略無系統性 edge。

## Key Evidence
- 實盤 vs 回測 filtered 重疊率 24.6%（< 30% invalidation 門檻）
- S003 Baseline：IS PF=1.18, OOS PF=1.00（零收益）
- 放寬 BB%B 門檻全面惡化（實盤高勝率來自主觀篩選，非寬鬆門檻）
- 移除夜盤條件是唯一正向改善（OOS PF 1.00→1.07），但仍偏弱
- Best combo 年度極不穩定：6 年中 4 年虧損，僅 2022 明確獲利（PF=2.20）
- H036 原始回測使用 ORB 價格進場導致績效高估（PF 1.34→1.10, +914pt→+256pt）

## Why Rejected
S003 以 close 進場的真實績效 PF=1.00~1.10，OOS 無 edge。實盤的優異表現（PF=9.37）來自主觀篩選能力，無法系統化複製。即使最佳參數組合（移除夜盤條件）OOS PF=1.07 也不足以支撐 live 策略。

## Derived Hypotheses
- H0XX-exhaustion-entry-timing：ORB 反向突破時 close 已偏離太多，測試限價單進場是否改善
- H0XX-exhaustion-exit-study：比較不同出場方式（SatZone 兩段式 vs 固定 TP vs 移動停損）

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md
