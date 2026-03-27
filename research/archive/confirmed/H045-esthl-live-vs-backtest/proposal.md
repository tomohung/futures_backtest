# Proposal: EstHL 實盤 vs 回測比對

## ID
H045

## Derived From
S001-esthl（live strategy）

## Trading Intuition
EstHL 策略已上線實盤，需要比對實盤與回測的差異，找出系統性偏差來源，確認策略實作是否忠實反映回測邏輯。

## Hypothesis
實盤 EstHL 策略的績效與回測結果存在可量化的差異，且差異來源可歸因於特定因素（如滑價、信號延遲、手動判斷偏差、或策略邏輯實作差異）。

## Expected Distribution
- 實盤與回測在大部分交易日的進場方向一致
- 損益差異集中在少數幾筆大幅偏離的交易
- 可能發現實盤漏接或多做的信號

## Invalidation Condition
- 實盤與回測無法對齊（交易日期/方向完全不匹配），表示比對方法或策略版本有根本差異
- 實盤樣本數過少（< 15 筆），統計意義不足

## Notes
### 資料來源
- 實盤記錄：從 H044 的 `data/live_parsed.csv` 提取 strategy=esthl 的交易
- 回測記錄：從 ORBWithEstHLExitStrategy 回測產出的 trades 提取對應日期範圍
- 另有 esthl_costline（開盤區間突破成本線）21 筆，為未回測的變體，可獨立分析
