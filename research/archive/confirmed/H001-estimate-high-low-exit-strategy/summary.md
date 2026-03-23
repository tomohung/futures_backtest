# Archive: EstimateHL 離場機制（SatZone 兩段式出場）

## Status
Confirmed

## Summary
將 TradingView PineScript 的預估振幅演算法移植到 Python backtesting 框架，建立 SatZone（滿足區）兩段式出場機制。以 15 分鐘時間比重預估當日成交量與振幅，每個 slot 延遲一期廣播避免 lookahead，觸及滿足區後等 close 跌破 5MA 才出場。實測 1,251 個交易日中 83% 至少觸及一邊 SatZone。

## Key Evidence
- SatZoneUpper 觸及率 63%（795/1251 天），SatZoneLower 40%（501 天），至少一邊 83%
- 完全未觸及 34%（427 天）：縮量盤整日，振幅本來就小，非演算法失準
- 大幅突破 14%（181 天）：放量趨勢日，EMA(20) 反應慢致 SatZone 設太近
- EmaVol 範圍 143k-384k，EmaHL 範圍 108-456 點，符合預期
- 延遲一個 slot 廣播驗證正確，無 lookahead

## Why Confirmed
核心演算法成功移植且通過驗證（Step A + Step B），SatZone 在正常觸及日（52%）表現良好，成為 EstHL、Reversal 等多策略共用的出場模組。EstimateHLExitMixin 已穩定運作。

## Derived Hypotheses
- H002: ORB + EstHL 出場組合策略
- EstRange Volume-Weighted 改良版（5 分鐘 slot + 實際量 EMA，取代硬編碼 TIME_FACTORS）
- SatZone fraction 實驗（結算日校正）

## Links
- Proposal: specs/strategies/2026-03-09-estimate-high-low-exit-strategy.md
