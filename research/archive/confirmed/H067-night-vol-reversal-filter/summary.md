# Archive: Night Session Volatility as Reversal Filter

## Status
Confirmed

## Summary
夜盤波動濾網（night_range / SMA20 >= 0.85）對 Reversal 策略效果顯著。低波動夜盤後 Reversal 是負期望值（PF=0.96），所有利潤來自高波動夜盤（PF=1.58）。Quartile 完美單調遞增，Walk-forward 5/5 全勝。與 H066（EstHL）共用同一指標和門檻。

## Key Evidence
- Median split：HIGH PF=1.58 vs LOW PF=0.96（差異 64.3%，N=240/240）
- Quartile：Q1 PF=0.95, Q2=0.97, Q3=1.15, Q4=1.93（完美單調）
- 跨年一致 5/6，Walk-forward 5/5 全勝
- 門檻不敏感（0.70–1.10 OOS PF 都 > 2.0）

## Why Confirmed
1. 低波動夜盤後 Reversal 負期望值——過濾完全合理
2. Walk-forward 5/5 全勝，比 H066 的 2/5 更穩定
3. 邏輯清楚：反轉策略需要波動空間，夜盤平靜 = 日盤沒什麼好反轉的
4. 與 H066 共用 SMA20 + 0.85 門檻，無額外複雜度

## Derived Hypotheses
無（共用 H066 基礎設施）

## Links
- Proposal：proposal.md
- Results：results/distribution.md
- Explore script：explore.py
