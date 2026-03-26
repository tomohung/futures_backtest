# Proposal: BB Extreme Bypass MA Direction

## ID
H042

## Derived From
S002-reversal + S003-exhaustion（H036）概念延伸

## Trading Intuition
Reversal 策略使用 30 分 K 20MA 方向作為進場濾網，避免逆勢交易。但在極端行情中（30 分 K BB%B > 1 或 < 0），價格已偏離均值甚遠，反轉機率提高。此時 MA 方向仍可能指向趨勢方向（因為 MA 反應滯後），導致有效的反轉訊號被過濾掉。

例如：開盤急殺，30 分 K BB%B < 0，MA 方向仍向下，但 1 分 K 出現 BB touch + CCD 轉向等 Reversal setup，這筆多單被 MA 濾網擋掉。實際上這正是極端後反彈的好機會。

## Hypothesis
當 30 分 K BB(20, open) %B > 1 或 < 0 時，bypass Reversal 策略的 MA 方向檢查，允許逆勢進場。在此條件下的 Reversal 交易，其勝率與期望值不低於整體 Reversal 策略。

## Expected Distribution
- 30 分 K BB%B 極端值（>1 或 <0）的出現頻率：預估每月數次
- 在這些極端日中，被 MA 方向擋掉的 Reversal setup 數量
- 這些被擋掉的交易若執行，其 P&L 分佈應偏正（因為極端後反轉）
- MFE 應有足夠空間（極端後的反彈幅度通常較大）

## Invalidation Condition
- 極端 BB%B 時 bypass MA 後的交易，勝率顯著低於整體 Reversal（< 40%）
- 期望值為負或 Profit Factor < 1.0
- 樣本數過少（< 30 筆）無法得出統計結論
- 大部分「被擋掉」的交易實際上是趨勢延續而非反轉（MAE > MFE）

## Notes
- 進出場邏輯完全沿用 Reversal 策略（BB latch + trigger + SatZone exit）
- 唯一差異：當 30 分 K BB%B 極端時，跳過 MA 方向檢查
- 可視為 Exhaustion 策略的變形——用 BB%B 極端值替代 EstRange 走完 50% 作為「耗竭」判定
- 需確認 30 分 K BB%B 的計算方式：BB(20, open) 是以 open 為基準的 20 期 BB
