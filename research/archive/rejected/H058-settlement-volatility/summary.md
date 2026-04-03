# Archive: Settlement Volatility Effect

## Status
Rejected

## Summary
假設結算日（第三個週三）前後振幅顯著放大，可用於調整 EstRange。
實際數據顯示效應微弱且不一致，無法支持策略應用。

## Key Evidence
- 日盤結算日振幅 median 222 vs 非結算日 188（ratio 1.18x），但 p=0.19 不顯著（N=61）
- 夜盤結算日振幅反而偏小（ratio 0.91x），方向相反
- 全日盤 ratio 僅 1.09x，EMA 標準化後幾乎消失（1.004x）
- 無漸進效應：結算前 -2/-1 日無放大跡象
- Weekday control（結算週三 vs 非結算週三）p=0.099 邊緣，效應量不足

## Why Rejected
1. 三個維度（日/夜/全日）不一致，夜盤方向相反
2. 日盤效應 18% 但不顯著，EMA 標準化後僅 8.5%
3. 無漸進效應，不符合「避險轉倉逐漸放大」的邏輯
4. 效應量不足以設計可靠的策略調整

## Derived Hypotheses
- （無）

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Explore script：explore.py
