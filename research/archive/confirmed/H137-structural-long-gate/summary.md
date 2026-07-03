# Archive: 日盤結構閘做多加權

## Status
Confirmed（限定用途：風控 / regime 加權 tile，非獨立 alpha 策略）

## Summary
從 H136（rejected）翻轉而來。H136 證明「開盤 vs 均線」不能預測日內窗方向，但發現「開盤破長均」是乾淨的 regime 標籤。H137 把它從方向訊號改為**做多強度閘門**：`開盤adj > MA60 且 MA60 斜率向上（20日）`，僅在閘開時做多日盤全段（08:45→13:45）。閘門 100% 因果、盤前可算，能即時辨識 2022/2025 型持續崩盤。

## Key Evidence
- 全期 gross：結構閘 +5284pt / Sharpe **0.67** / maxDD −3875（N=755） vs 無條件做多 +1856pt / Sharpe **0.05** / maxDD −4061（N=1252）。勝率兩者皆 52%，edge 全在避開負漂移日。
- OOS（2024-01~2026-07，含 2025 關稅崩盤）：結構閘 Sharpe **+0.93** vs 無條件 +0.48；2025 崩盤為 OOS 未見事件仍被擋（閘 +1282 vs 無 +483）。
- 逐年不翻號：崩盤年大勝（2022 −187 vs −2721；2025 +1282 vs +483），純多頭年小輸（2023/2026 略低）。
- 參數穩健：MA{20,60,120}×slope{10,20,40} 全 9 組正 total、正 Sharpe。成本 3 點 round-trip 仍 +3019pt。
- 崩盤覆蓋率（因果閘）：2022=89%、2025=100%；多頭年 26–34%。

## Why Confirmed
閘門因果、參數穩健、逐年不翻號、OOS 成立且能即時辨識崩盤，正是「結構弱降做多強度、不反手做空」的 kill-switch。

**已知限制（誠實標註）**：崩盤剝離後，平時「閘關」日仍為正（+3.97/天），代表戲劇性防守價值幾乎全來自 2022+2025 **兩個獨立事件（事件 N=2）**。因此限定為風控/regime tile；純多頭年當獨立多單策略會略輸無條件做多，不建議如此使用。

## Implementation
- 落地為 `src/analysis/key_prices.py` 方向加分新增「結構位階」tile：閘開→多方票；閘關→中性（不投空票）。
- 非 strategies/live/ 獨立策略（用途是 scorecard 濾網，非 alpha）。

## Derived Hypotheses
- H138（候選）：閘關期間改主動避險（put/減碼）而非單純空手，須測日級（H136 已示日內反手翻號）。
- 觀察：MA20 版 maxDD 較大（whipsaw），靈敏崩盤觸發可配 VIX regime 降 whipsaw。

## Links
- Proposal：proposal.md
- Phase 1：explore.py（= H136 regime_detect.py）
- Backtest：results/backtest.md、backtest.py、results/equity.png、results/daily.csv
