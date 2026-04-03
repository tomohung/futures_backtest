# Proposal: Weekday Volatility Pattern

## ID
H060

## Derived From
H029 (weekday-effect) — H029 看的是策略績效 by weekday，這裡看原始振幅分佈

## Trading Intuition
不同星期幾的波動特性可能不同——例如週一受週末消息影響跳空大、
週三結算效應、週五提前減倉使波動縮小。
若存在穩定的星期別差異，可用於調整每日的 EstRange fraction（目前已有 Tue/Wed vs 其他的區分）。

## Hypothesis
台指期的日盤、夜盤、全日盤振幅在不同星期幾之間存在顯著差異，
且此差異在不同年份間具有穩定性。

## Expected Distribution
- 某些星期幾的振幅中位數 > 其他天的 1.15 倍以上
- 目前 EstRange 的 Tue/Wed = 0.75、其他 = 0.618 設定有實證基礎
- 夜盤的星期別效應可能與日盤不同

## Invalidation Condition
- Kruskal-Wallis 檢定 p > 0.1（各星期無顯著差異）
- 或差異存在但逐年不穩定（某年 Mon 最大、某年 Fri 最大）

## Notes
- 全日盤定義：前一天 15:00 夜盤 + 當天日盤
- 星期歸屬以日盤交易日為準（週一日盤 = 週一，其對應夜盤 = 週五 15:00 開始）
- 需排除結算日以避免混淆效應（或分組分析）
- 結果可用於優化 EstRange 的 weekday fraction 設定
