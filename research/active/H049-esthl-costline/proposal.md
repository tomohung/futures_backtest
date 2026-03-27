# Proposal: EstHL Costline — VWAP 突破進場

## ID
H049

## Derived From
H045（EstHL 實盤 vs 回測比對）的 distribution 階段

## Trading Intuition
實盤中有一類「開盤區間突破成本線」交易，進場邏輯與 EstHL 的 OR 突破不同：早盤在 VWAP 下方（或上方）整理一段時間後，突破 VWAP 進場。H045 分析發現這 21 筆實盤交易勝率 71.4%、PF 高，值得獨立研究是否能系統化。

## Hypothesis
早盤整理後突破 VWAP 的進場方式，相較於 OR 突破，可能在不同市場條件下提供額外的交易機會，且具有正期望值。

## Expected Distribution
- 進場時間較 EstHL 晚（預期多在 09:05~09:30）
- 與 EstHL OR 突破的交易日重疊率低（多數是 EstHL 沒有信號的日子）
- 損益分佈偏正，平均獲利 > 平均虧損

## Invalidation Condition
- 無法從實盤記錄中歸納出可量化的進場規則
- 歷史回測樣本數不足（< 30 筆/年）
- 回測期望值為負或 PF < 1.2

## Notes
### 實盤數據（from H045）
- 21 筆交易，勝率 71.4%（15/21），總 PnL +1483 點，平均 +70.6 點
- 進場時間範圍：09:00~09:33
- 出場策略同 EstHL（SatZone 兩段式 + 移動停損）
- 其中 8 筆與回測同日有交易（不同進場邏輯），13 筆回測無信號

### 待釐清
- 進場時間窗口：目前無法明確定義，需從數據反推
- 方向判斷邏輯：目前無法明確定義，需從走勢分析歸納
- 「成本線」的精確定義：用戶描述為 VWAP，但需驗證是哪個 VWAP（當日/前日/機構成本）

### 資料來源
- 實盤交易明細：`research/archive/confirmed/H044-reversal-live-vs-backtest/data/live_parsed.csv`（strategy=esthl_costline）
- 回測比對：`research/archive/confirmed/H045-esthl-live-vs-backtest/compare.py`
