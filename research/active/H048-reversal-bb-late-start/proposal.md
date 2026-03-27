# Proposal: Reversal BB Latch 延後起算時間

## ID
H048

## Derived From
S002-reversal 實盤觀察

## Trading Intuition
觀察到 Reversal 策略中，有些 BB touch 在 09:10 前就出現，但最終決定進場的 5MA crossing 信號往往在 09:10 後才觸發。這代表 08:45 就開始累計 BB latch 可能沒有實質意義——開盤前 20 分鐘的 BB touch 只是噪音，真正有效的 setup 要等到盤勢稍微穩定後才成立。

## Hypothesis
將 Reversal BB latch 的 setup window 起始時間從 08:45 延後至 09:05（或 09:10），可以過濾開盤噪音期間的無效 BB touch，在不顯著減少有效進場次數的前提下，提升整體進場品質（hit rate 或 profit factor）。

## Expected Distribution
- 09:05 起算：過濾掉少量早期噪音 latch，進場次數略減但品質提升
- 09:10 起算：過濾更多，可能錯過部分有效信號
- 兩者與 08:45 基準比較，預期 win rate 或 avg profit 有改善

## Invalidation Condition
- 延後起算導致進場次數大幅下降（> 20%）且整體績效未改善
- 08:45~09:05 之間的 BB latch 實際上有相當比例最終產生獲利交易
- Profit factor 在延後版本反而下降

## Notes
- 測試三組：08:45（現行）、09:05、09:10
- 重點觀察 08:45~09:10 之間觸發的 BB latch 最終交易結果分佈
- 此假設不改變 5MA crossing 進場時機，只改變 BB latch 開始監控的時間
