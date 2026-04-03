# Archive: VSA 無供應 — 趨勢回檔賣壓枯竭進場

## Status
Rejected

## Summary
測試威科夫 VSA「No Supply」概念在台指期 5mK 上的表現：上升趨勢中出現窄幅低量收跌 bar，下一根收漲確認後做多。No Supply 做多方向無 edge（PF=0.98），H050 初步報告的 PF=2.00 無法重現。No Demand 做空方向有穩定小 edge（PF=1.40），但整體假說的核心主張（No Supply 做多）不成立。

## Key Evidence
- No Supply (Long): N=478, WR=49.6%, PF=0.98, AvgPnL=-0.4pt — 無正期望值
- IS/OOS 分裂：IS PF=1.11 → OOS PF=0.80
- 門檻敏感度：嚴格組合（0.4x/0.3x）PF=1.84 但 N=59，放寬後快速衰減至 PF≈1.0
- MA 期間（10/20/40/60）無顯著差異，PF 皆在 0.94~1.05
- No Demand (Short): N=366, PF=1.40, 每年正期望值 — 但非本假說核心主張

## Why Rejected
- No Supply 做多方向（假說核心）整體 PF < 1.0，IS/OOS 不一致
- H050 初步篩選的 PF=2.00 在完整驗證中無法重現
- No Demand 做空雖有 edge，但 PF=1.40 扣除成本後空間有限，且為假說的附帶發現而非核心主張

## Derived Hypotheses
- No Demand 做空 + 時段濾網：分析 No Demand 的時段效率是否可提升 PF
- VSA + EstHL 出場：用 SatZone 動態出場取代固定持有
- 更嚴格趨勢定義：ADX > 25 + MA 下降取代單純 MA 方向

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Explore Script：explore.py
