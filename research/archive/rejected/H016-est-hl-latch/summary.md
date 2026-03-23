# Archive: EstHL Latch + 新高確認策略

## Status
Rejected

## Summary
在 EstHL 的 OR 突破信號後加入 latch 機制，等待後續出現新的 session high 才進場，目的是過濾假突破。兩種確認模式（any_bar 新高、5min_close 新高）均測試，結果顯示 latch 沒有產生新信號，只是延遲進場墊高成本。

## Key Evidence
- Mode 0 (any_bar)：155 筆，WR 58.7%，總損益 +4,216（基準 161 筆 +4,686）
- Mode 1 (5min_close)：153 筆，WR 56.9%，總損益 +3,672
- **100% 重疊**：Latch 155 筆全部在基準 161 筆裡，0 筆獨有交易
- 僅過濾 6 筆（全虧，avg -68.5 pts，total -411 pts），但過濾效果不穩定
- 平均進場延遲 2.8 分鐘，92% 在 1-5 分鐘內
- 進場平均貴 5 點，EV 下降幾乎等於進場價差（29.1 → 27.2 pts）

## Why Rejected
92% 的交易在突破後 1-5 分鐘內就會創新高，新高確認本身就是突破動能的一部分，不具備獨立的 alpha。Latch 沒有產生任何新的交易信號，作為加碼點也無意義。

## Derived Hypotheses
- 若要找加碼點，應尋找時間或邏輯上獨立的信號（回踩不破、盤中二次突破等）
- OR 突破後的新高確認不適合作為進場條件改善

## Links
- Proposal: specs/strategies/2026-03-22-est-hl-latch.md
