# Proposal: Reversal Skip After Breakout — 突破進場後跳過反轉

## ID
H041

## Derived From
Origin — 實盤觀察：Reversal 實戰勝率 ~70% 遠高於回測 ~46%

## Trading Intuition
實戰操作中，通常先觀察突破策略（EstHL / S001），如果 EstHL 已在 08:58-09:15
進場做多，當天就不再執行 Reversal 策略。這是一個隱性的人工濾網。

直覺上，當 EstHL 觸發了（ORB 突破 + VWAP/MA 方向正確），代表當天有明確的
趨勢動能。此時 Reversal 的「逆向反轉」訊號容易失敗——市場正在順勢走，
BB touch 只是回調而非反轉。

假設這個隱性濾網就是實戰勝率遠高於回測的主要原因。

## Hypothesis
在 EstHL 突破策略觸發進場的交易日，Reversal 策略的勝率和期望值顯著低於
EstHL 未觸發的交易日。將「EstHL 觸發日跳過 Reversal」作為濾網，
能顯著提升 Reversal 的回測績效。

測試方式：
- 定義「ORB 突破日」：08:58-09:15 內 close 突破 OR High 或 OR Low（不含 VWAP/MA 等濾網）
- 比較 ORB 突破日 vs 非突破日的 Reversal 績效
- 模擬「ORB 突破則跳過 Reversal」的回測

## Expected Distribution
- EstHL 觸發日的 Reversal 勝率 < 40%（趨勢日反轉容易失敗）
- EstHL 未觸發日的 Reversal 勝率 > 50%
- 套用濾網後，Reversal 交易次數減少但勝率和 PF 明顯提升

## Invalidation Condition
- EstHL 觸發日 vs 非觸發日的 Reversal 勝率無顯著差異（< 5%）
- 或 EstHL 觸發日的 Reversal 交易次數太少（< 30 筆），樣本不足
- 或 EstHL 觸發日的 Reversal 反而表現更好（原假設方向錯誤）

## Notes
- EstHL 進場窗口 08:58-09:15，Reversal 進場窗口 09:10-10:05，有 5 分鐘重疊
- EstHL 只做多（且跳過 Thu/Fri），Reversal 做多做空都有
- 需要同時跑兩個策略的資料載入，找出 EstHL 觸發的日期集合
- 這不只是策略間的衝突問題，更可能反映「趨勢日 vs 震盪日」的 regime 差異
