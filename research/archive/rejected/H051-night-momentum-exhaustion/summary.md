# Archive: Night Session Momentum Exhaustion

## Status
Rejected

## Summary
測試夜盤動能衰竭指標（RSI 背離、極值時間、尾段回落、成交量衰減）能否區分 S003 竭盡反轉策略的交易品質。四個指標中 RSI 背離完全失敗，其餘三個雖有中等區分力，但 median split 有 in-sample overfitting 風險，combined signals 堆疊反而稀釋效果，且近年訊號品質未如預期改善。

## Key Evidence
- N=67 筆 S003 信號，基準 WR=62.7%, PF=2.50
- RSI Divergence：方向相反（有背離 PF=1.96 vs 無背離 PF=3.90），且近年不穩定
- Extreme Time ≤01:00：PF=3.88 vs 1.87，但 cutoff 敏感（median 02:41 反轉）
- Tail Retracement ≥median：PF=3.90 vs 1.50，中等區分力但用 median split
- Volume Decay <median：PF=3.41 vs 1.83，中等區分力但用 median split
- Combined 2+ signals 未改善（PF 2.28 < baseline 2.50）
- 近年（2024-2026）WR 提升但 PF 下降（2.25 vs 早年 3.31），虧損擴大

## Why Rejected
- RSI 背離無效，方向與假設相反
- 其餘指標的分組效果依賴 median split（in-sample 最佳化），4 指標 × 2 cutoff = 8 次比較有 multiple testing 風險
- 指標堆疊（combined signals）無法改善績效，缺乏 synergy
- 夜盤量放大未帶來預期的訊號品質改善
- 整體判斷：個別指標有噪音中的微弱訊號，但不足以作為可靠濾網

## Derived Hypotheses
- H0XX：Tail Retracement 作為跨策略通用衰竭指標 — 尾段回落可能適用於其他反轉型策略（S002 Reversal）
- H0XX：夜盤極值時間與隔日開盤方向 — 極值在 01:00 前出現是否與隔日開盤 gap 方向有關聯

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Explore Script：explore.py
