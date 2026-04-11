# Archive: Morning Dip Reversal

## Status
Rejected

## Summary
探索台指期日盤早盤下殺後反彈做多的策略可行性。Phase 1 確認 morning dip 現象普遍存在（80% 交易日），但 Phase 2 回測顯示用機械式規則（BB 超賣 + MA5 確認 + SMA 趨勢）無法產生穩定正期望值。

## Key Evidence
- Phase 1：1,024/1,274 天有明確 morning dip，single dip 到收盤 win rate 86.6%
- Phase 2 v1（dip detection）：IS EV=-13.7, PF=0.96
- Phase 2 v2（BB+MA5, 9:15~9:45 窗口）：IS EV=-21.6, PF=0.93
- Phase 2 v3（+SMA 趨勢濾網）：所有 SMA 組合 IS 均為負
- 參數敏感度：所有參數組合 IS 期望值在 -40 ~ +20 之間，無穩定正區域

## Why Rejected
Morning dip 的統計現象真實存在，但從「現象存在」到「可交易」之間有巨大鴻溝。BB/KD 在 1 分 K 上幾乎每天都會觸發超賣，導致交易過於頻繁且沒有選擇性。加入日線 SMA 趨勢濾網後交易量減半但期望值更差。核心問題是機械式規則無法捕捉 morning dip reversal 需要的判斷力（盤勢判讀、力道感知）。

## Derived Hypotheses
無

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md
- 探索腳本：explore.py
- 回測腳本：backtest.py
