# Proposal: Reversal Weekday Effect

## ID
H068

## Derived From
H029（Weekday Effect，EstHL confirmed）的延伸，檢驗 Reversal 是否也有星期效應

## Trading Intuition
初步分析顯示 Reversal 在週一（PF=0.75）和週五（PF=0.93）表現差，週二最強（PF=2.16）。EstHL 已確認星期效應並加入濾網（skip Thu+Fri），Reversal 也可能有類似的結構性星期差異。但跨年穩定性待驗證——週一在 2025 年突然變好（PF=2.37）。

## Hypothesis
Reversal 在特定星期（初步指向週一和週五）的績效顯著低於其他星期，跳過這些天可提升整體 PF 和 Sharpe。

## Expected Distribution
- 週一 PF < 1.0，跨年多數方向一致
- 週五 PF < 1.0，跨年多數方向一致
- 跳過弱勢星期後 PF 提升 > 20%

## Invalidation Condition
- 跨年穩定性 < 4/6（方向不一致的年份過多）
- 跳過後 IS/OOS PF 差異不穩定
- 效果不如單獨使用夜盤波動濾網

## Notes
- Reversal 已有夜盤波動濾網（H067），需測試星期濾網是否在此基礎上額外有效
- 需同時測試：星期濾網 only、夜盤濾網 only、兩者結合
- 樣本數：498 筆（無濾網），每星期約 95-109 筆，足夠分析
