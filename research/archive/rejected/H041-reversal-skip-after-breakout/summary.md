# Archive: Reversal Skip After Breakout

## Status
Rejected

## Summary
假設 EstHL 觸發日（ORB 突破 + 趨勢確認）是 Reversal 低品質交易的來源，跳過這些天可提升績效。實際數據顯示方向完全相反：EstHL 觸發日的 Reversal 表現更好（WR 50% vs 43%，PF 1.44 vs 1.26）。

## Key Evidence
- EstHL 觸發日 Reversal：N=48, WR=50.0%, PF=1.44, +381 pts
- 非觸發日 Reversal：N=421, WR=43.0%, PF=1.26, +2,347 pts
- 觸發日全部為 Long（0 筆 Short），與 EstHL 方向一致
- 跳過觸發日反而讓 PnL 退步 -381 pts
- Raw ORB 突破覆蓋 89% 交易日，無區分力

## Why Rejected
假設方向錯誤。EstHL 觸發代表多頭趨勢確認，Reversal 在同方向做多時反而有更好的條件（回調後的第二次進場機會），而非逆勢失敗。實戰 WR 高於回測的原因需另尋解釋。

## Derived Hypotheses
（無）

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
