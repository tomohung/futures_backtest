# Archive: Night Session Volatility as Reversal Filter

## Status
Confirmed（**已被 H075 方法升級**：實作從 SMA + 0.85 fixed → EMA + expanding median，2026-04-21）

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

## H075 後續更新（2026-04-21）

H075 將 production NVF 升級為 EMA + expanding median（causal 版的 H066 評估方法）。對 Reversal 的改善：
- HIGH PF 1.35 → 1.57（+16%）
- max_streak 持平 7
- worst streak P&L 改善 16.3%（-404 → -338）
- max DD 改善 16.5%（-565 → -472）
- total P&L +31%（+2,254 → +2,958）

新方法亦修復了 H072 發現的 Reversal Wed/Thu OOS drift cells。

詳見 `research/archive/confirmed/H075-nvf-method-upgrade/`。

## Derived Hypotheses
無（共用 H066 基礎設施）

## Links
- Proposal：proposal.md
- Results：results/distribution.md
- Explore script：explore.py
