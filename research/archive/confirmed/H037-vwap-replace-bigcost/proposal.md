# Proposal: VWAP 取代大戶成本

## ID
H037

## Derived From
Origin（原創觀察）

## Trading Intuition
大戶成本（BigCost）的計算方式是先篩選 volume >= 20MA(volume) 的 1 分 K bar，再對這些 bar 計算 VWAP。但實際觀察發現，這個值與直接用全日所有 bar 算出的 VWAP 幾乎一致。既然兩者接近，不如直接用 VWAP 取代，減少計算複雜度。

## Hypothesis
以全日 VWAP（sum(close×volume)/sum(volume)）取代大戶成本（volume-filtered VWAP），各策略的回測績效不會顯著下降。

## Expected Distribution
- 大多數交易日，BigCost 與 VWAP 的差異 < 10 點
- 替換後策略績效在統計噪音範圍內

## Invalidation Condition
- 替換後任一策略的 Sharpe 下降超過 0.1，或勝率下降超過 3%
- BigCost 與 VWAP 的差異在特定市場狀態下系統性偏離（例如高波動日差異顯著擴大）

## Scope
需驗證的使用點：
1. `src/backtest/runner.py` — `load_data_for_orb_est_hl()`（BigCost1~5）
2. `src/backtest/runner.py` — `load_data_for_reversal()`（BigCost1~2）
3. `src/analysis/key_prices.py` — 早盤簡報大戶成本顯示
4. 各 Pine Script 指標中的大戶成本水平線

## Notes
- 如果驗證通過，可以移除 BigCost 的 volume filter SQL，直接改用已有的 VWAP 計算
- key_prices.py 已同時算 VWAP 和 BigCost，可直接比較
