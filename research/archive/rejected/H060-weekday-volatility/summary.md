# Archive: Weekday Volatility Pattern

## Status
Rejected

## Summary
探索台指期不同星期幾的日盤、夜盤振幅差異。統計上顯著（日盤標準化 p=0.002, 夜盤 p<0.001），但效應大小不足以產生交易價值，且現行 EstRange fraction 設定已涵蓋此效應。

## Key Evidence
- 日盤標準化振幅：Tue 最高 (0.999) / Wed 最低 (0.878)，差異 13.7%（N=1,237）
- 夜盤標準化振幅：Thu 最高 (1.013) / Tue 最低 (0.865)，差異 17.0%
- 日盤與夜盤效應方向相反——可能因日盤受台灣因素驅動、夜盤受美股因素驅動
- Tue 日盤偏高在 5/6 年穩定，但最小值星期逐年不穩定

## Why Rejected
1. 效應大小 13.7% 未達 15% 門檻，不足以改變進出場決策
2. 現行 EstRange 的 Tue/Wed fraction = 0.75 vs 其他 = 0.618 已反映此效應
3. 夜盤反向效應有趣但目前只做日盤當沖，無法利用
4. 確認現有設定正確，但無新的 actionable edge

## Derived Hypotheses
- 夜盤星期別效應可用於調整夜盤 EstRange（Thu 夜盤振幅偏高）
- Tue 日盤振幅偏高是否因週末消息累積（gap 大小 vs 振幅相關性）

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Explore script：explore.py
