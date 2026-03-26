# Proposal: Reversal BB Touch + Intraday Level Retest Confluence

## ID
H038

## Derived From
H005-reversal / H006-reversal-v2 的實盤觀察

## Trading Intuition
2026-03-26 盤中觀察：開盤後價格在 33730~33850 之間形成 consolidation range，
33730 附近被連續測試三次都沒有跌破，09:20 出現 BB%B < 0 訊號。
這種「盤中自然形成的 range 邊界被多次測試 + BB extreme」的組合，
直覺上比單獨的 BB touch 更可信——多次測試不破代表該位置有真實買/賣盤承接。

目前 Reversal 策略已有 4 種 CCD bypass 條件，不想再單純加條件。
這個假設要驗證的是：盤中 level retest 次數是否能作為**獨立的** confluence 指標，
區分有效 vs 無效的 BB touch 訊號。

## Hypothesis
當 BB touch 發生時，如果該價位附近已在當天被多次測試（形成 intraday range 邊界），
後續反轉的成功率顯著高於未被多次測試的 BB touch。

Intraday level retest 定義：
- Long: BB touch 之前，當天有 >= N 根 bar 的 Low 落在 BB touch 價位 ± tolerance 範圍
- Short: BB touch 之前，當天有 >= N 根 bar 的 High 落在 BB touch 價位 ± tolerance 範圍
- tolerance 候選值：10pt, 20pt, 30pt（台指期最小跳動 = 1pt）
- retest 次數候選值：N >= 2, 3, 5

## Expected Distribution
- 多次 retest（>= 3 次）的 BB touch：反轉成功率 > 60%，或 MFE 顯著高於未 retest 組
- 未被 retest 的 BB touch：成功率較低，或 MFE 較小
- Retest 次數與成功率呈正相關

## Invalidation Condition
- 有/無 retest 兩組的勝率與期望值無顯著差異（勝率差 < 5%）
- 或 retest 組樣本數太少（< 30 筆）
- 或結果對 tolerance / N 參數過度敏感

## Notes
- 這不是歷史 S/R（前次探索已否定），而是當天盤中動態形成的 price level
- 如果 confirmed，可能的應用方式是用 retest count 取代或補充現有的 bypass 條件
- 先前以歷史 30 日 S/R 測試的結果（無效）保留在 results/distribution_v1.md
- 現有 bypass 條件的邊際貢獻回顧留給未來獨立假設
