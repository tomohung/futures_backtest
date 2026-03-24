# Proposal: 滾動潛力日密度作為市場 regime 指標

## ID
H035

## Derived From
H021（strategy-candidates-from-volatility）的 distribution 階段 — 潛力日定義與覆蓋分析

## Trading Intuition
用戶觀察到 EstHL 和 Reversal 在 2026 年 1 月和 3 月績效特別好。如果這兩段期間的潛力日（range >= 1%）密度較高，就能解釋策略績效的波動。滾動 20 日的潛力日比例可以量化市場波動 regime 的轉變，讓我們知道什麼時候策略在「好的環境」中運作。

## Hypothesis
滾動 20 個交易日中潛力日（range_pct >= 1.0%）的比例可以有效反映市場波動 regime。2026 年 1 月和 3 月的潛力日密度應高於其他月份，對應策略績效較好的期間。

## Expected Distribution
- 2026 年 1 月和 3 月的潛力日密度高於同期其他月份
- 密度高低與市場重大事件（如崩盤、結算）有對應關係
- 密度的時間序列能辨識出明顯的高/低波動 regime 區段

## Invalidation Condition
待 Phase 1 探索後根據實際分佈再定義具體門檻。初步方向：
- 2026 年 1 月/3 月的密度是否確實偏高
- 密度指標是否能有效區分不同 regime
- 歷史上密度的波動幅度是否足夠大到有實用價值

## Notes
- 先做一次性探索分析，如果結果有價值再考慮整合進 morning_briefing
- 只看潛力日密度本身，暫不疊加策略績效對照
- 重點是理解市場 regime 轉變，不限於季節性
