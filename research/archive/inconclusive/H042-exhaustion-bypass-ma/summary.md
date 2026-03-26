# Archive: Exhaustion Bypass MA Direction

## Status
Inconclusive

## Summary
探索在 Reversal 策略中，當對手方動能已耗盡（Exhaustion）時 bypass MA 方向檢查，允許逆 MA 進場。原假設為 BB%B 極端值 bypass，但修正計算後交叉樣本僅 4 筆，轉向用 Exhaustion 作為 bypass 條件。完整回測顯示改善微幅（PF 1.32→1.33, +443 pts/5年），不值得增加策略複雜度。

## Key Evidence
- 46 筆被 MA 擋掉的交易中，exhausted 的 36 筆 WR 55.6%（Phase 1 MFE/MAE 分析）
- Phase 2 完整回測：bypass 多出 49 筆交易，WR 36.7%，Total +443 pts
- 整體 PF 1.32 → 1.33（幾乎無差異），Sharpe 不變
- H044 DIR_BLOCKED 12 筆只捕捉到 4 筆（33%）

## Why Inconclusive
- 改善方向正確（正向 delta），但幅度太小不足以確認為有意義的改進
- Extra trades 低 WR（36.7%）依賴少數大贏家，分佈 skewed
- IS 2021-2023 PF 略降，只有 2024 明顯改善
- 策略複雜度增加 vs 邊際收益的 tradeoff 不划算

## Derived Hypotheses
- H04X：extra trades 低 WR 高 EV 特徵，是否用更寬鬆 SL 或更長持倉時間可改善？
- H04X：H044 未捕捉的 8 筆 DIR_BLOCKED，是否有其他共同特徵可作為 bypass 條件？

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md
