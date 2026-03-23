# Archive: Reversal v2 — 力竭 + VWAP bypass 改善捕捉率

## Status
Confirmed

## Summary
Reversal v1 在強趨勢單邊行情中因 CCD 方向衝突、BB 觸碰時間過早、vol_ratio 過嚴等問題，只能捕捉約 43% 的實單關鍵價轉折交易。v2 引入 exhaustion latch（EstRange x 0.5 力竭判定）、VWAP bypass（09:30 後盤中成本確認）、獨立 BB latch + setup window 提前至 08:45，大幅提升捕捉率與績效。

## Key Evidence
- 2026-03 回測：v1 5 筆 +547 pts（勝率 60%） -> v2 10 筆 +1482 pts（勝率 70%）
- 實單關鍵價轉折捕捉率：v1 3/7（43%） -> v2 6/7（86%）
- 2026-01 回測：v2 11 筆 +679 pts（勝率 64%），實單捕捉率 8/11（73%）
- VWAP bypass 成功解決 CCD 結構性為負的問題（01/20 實單 +118，v2 +203）
- 未捕捉交易主因：MA 走平翻覆（接受）、BC zone 限制（需更多樣本）、BB+vol 不同步（拆分有副作用已復原）

## Why Confirmed
v2 在不增加參數複雜度的前提下（只新增 exhaust_fraction=0.5），將實單捕捉率從 43% 提升到 73-86%，損益從 +547 提升到 +1482（2026-03），且出場機制統一為 SatZone 兩段式（與 EstHL 一致），簡化了整體策略維護。

## Derived Hypotheses
- exhaust_fraction 敏感度（0.3/0.4/0.5/0.618）待全期回測驗證
- 跳空開低情境是否應放寬 BC zone 規則，需收集更多樣本
- MA 走平翻覆問題是否需要重新引入 min_slope_pct 或其他平坦期濾網

## Links
- Proposal: specs/strategies/2026-03-21-reversal-v2.md
