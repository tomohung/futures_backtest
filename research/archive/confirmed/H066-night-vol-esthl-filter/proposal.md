# Proposal: Night Session Volatility as EstHL Filter

## ID
H066

## Derived From
H029（Weekday Effect）的 distribution 階段發現 EstHL 週四/五表現差
H059（Night-Day Vol Correlation）發現夜盤日盤波動 raw r=0.65 但跨年不穩
H060（Weekday Volatility）發現週四夜盤波動最大但日盤最弱

## Trading Intuition
EstHL 目前用星期濾網（跳過週四五），但星期可能只是表象。真正的驅動因素可能是前一晚夜盤的波動大小——夜盤波動大代表市場活躍（H059 r=0.65 同向），日盤也傾向有較大空間讓 EstHL 發揮。如果直接用夜盤振幅分組，可能比星期濾網更有解釋力，也更能適應市場結構變化。

## Hypothesis
以前一晚夜盤振幅（正規化後）的高低分組，EstHL 在「夜盤高波動」組的績效（勝率、PF）顯著優於「夜盤低波動」組。且此分組的解釋力優於或至少等同於現有的星期濾網。

## Expected Distribution
- 夜盤高波動組：勝率 > 55%，PF > 2.0
- 夜盤低波動組：勝率 < 50%，PF < 1.5
- 兩組差異在多數年份穩定存在（跨年穩定性優於 H059 的 raw correlation）

## Invalidation Condition
- 兩組 PF 差異 < 20%
- 跨年穩定性差（半數以上年份方向不一致）
- 效果不如現有星期濾網（無法取代或補充）

## Notes
- 夜盤定義：前一日 15:00 ~ 當日 05:00（歸屬當日日盤交易日）
- 正規化方式：EMA20 正規化，避免絕對振幅受市場環境影響
- 分組方式：先用中位數分割，再嘗試不同分位數門檻
- 可進一步交叉分析：夜盤波動 × 星期，看是否夜盤波動能解釋星期效應
