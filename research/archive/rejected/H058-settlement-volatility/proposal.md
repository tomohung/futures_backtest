# Proposal: Settlement Volatility Effect

## ID
H058

## Derived From
Origin

## Trading Intuition
台指期每月第三個星期三結算，結算前後市場參與者的避險與轉倉行為可能導致波動放大。
若結算日附近振幅確實較大，可用於調整 EstRange fraction 或 Credit Spread 的進場條件。

## Hypothesis
結算日（第三個星期三）及其前後 1~2 個交易日的振幅（H-L），
在日盤、夜盤、全日盤（夜盤 15:00 + 隔天日盤）三個維度上，
均顯著大於非結算週的同星期日。

## Expected Distribution
- 結算日振幅中位數 > 非結算日同星期中位數的 1.2 倍以上
- 結算前 1 日（通常是週二）也可能偏大
- 夜盤可能比日盤效應更明顯（轉倉多在夜盤）

## Invalidation Condition
- 結算日振幅中位數與非結算日無統計顯著差異（p > 0.1）
- 或差異 < 10%，不具交易意義

## Notes
- 全日盤定義：前一天 15:00 夜盤開始 ~ 當天 13:45 日盤收盤
- 需處理結算日遇假日順延的情況（系統已有 settlement day 偵測邏輯）
- 可進一步看結算前 1/2/3 日的漸進效應
