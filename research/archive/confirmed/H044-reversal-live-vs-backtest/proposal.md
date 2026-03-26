# Proposal: Reversal 實盤 vs 回測比對

## ID
H044

## Derived From
S002-reversal（live strategy）

## Trading Intuition
Reversal 策略已上線實盤，但實盤與回測之間可能存在落差——進場時機、成交價、出場判斷、漏接信號等。透過逐筆比對實盤與回測的交易記錄，找出系統性偏差的來源，確認策略實作是否忠實反映回測邏輯。

## Hypothesis
實盤 Reversal 策略的績效與回測結果存在可量化的差異，且差異來源可歸因於特定因素（如滑價、信號延遲、手動判斷偏差、或策略邏輯實作差異）。

## Expected Distribution
- 實盤與回測在大部分交易日的進場方向一致
- 損益差異集中在少數幾筆大幅偏離的交易
- 可能發現實盤漏接或多做的信號

## Invalidation Condition
- 實盤與回測無法對齊（交易日期/方向完全不匹配），表示比對方法或策略版本有根本差異
- 實盤樣本數過少（< 15 筆），統計意義不足

## Notes
### 分析方向
1. 逐筆比對：同一交易日的進場方向、進場時間、進場價、出場價、損益
2. 差異分類：滑價、信號延遲、漏接、多做、出場時機差異
3. 彙整統計：實盤 vs 回測的勝率、均損益、PF 比較

### 資料來源
- 實盤記錄：由使用者提供，放入 `research/active/H044-reversal-live-vs-backtest/data/`
- 回測記錄：從 ReversalStrategy 回測產出的 trades 提取對應日期範圍
