# Archive: H020 — 波動潛力日分析工具

## Status
Confirmed

## Summary
建立分析工具找出「值得交易的日子」並按時段分類，作為策略覆蓋分析的基礎。以 Fixed 1.0% range_pct 門檻篩出潛力日，按邊際波幅分為 EarlyTrend/LateTrend/Afternoon/Spread 四類。工具本身完成且產出有用的分類，但作為獨立研究尚未直接產出可交易策略。

## Key Evidence
- 潛力日（range_pct >= 1.0%）：645 日（全期 51%）
- 類型分佈：EarlyTrend 72%、Spread 18%、Afternoon 6%、LateTrend 5%
- 曾嘗試 P67（當年前 1/3）作為相對門檻，但在極端年份（如 2026 年初）門檻被拉到 1.87%，排除正常中高波動日。Fixed 1.0% 跨年度更穩定
- 時段定義：MorningEarly 08:45-10:00 / MorningLate 10:00-11:00 / Midday 11:00-12:00 / Afternoon 12:00-13:45

## Why Confirmed
分析框架完成且產出有用的日類型分類（EarlyTrend/LateTrend/Afternoon/Spread）。Fixed 1.0% 門檻經驗證優於 P67 相對門檻。分類結果已被 H021 消化並衍生出具體策略方向（H032、H033）。

## Derived Hypotheses
- H021 strategy-candidates-from-volatility（5 個候選策略方向）
- 策略覆蓋率分析框架（哪些潛力日被現有策略遺漏）

## Links
- Proposal: specs/strategies/2026-03-22-volatility-potential-days.md
- Companion data: research/archive/confirmed/H020-volatility-potential-days/volatility_potential_days.csv
