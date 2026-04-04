# Proposal: Exhaustion 實盤 vs 回測比對

## ID
H046

## Derived From
S003-exhaustion（live strategy）

## Trading Intuition
Exhaustion 策略的實盤原型（bb<0.25/bb>0.75 後反向突破）已有數月交易記錄，且近期已完成程式化（S003）。需比對實盤主觀交易與程式回測的差異，確認程式化版本是否捕捉到實盤的核心邏輯。

## Hypothesis
實盤 Exhaustion 交易的績效與 S003 回測結果存在可量化的差異，且差異來源可歸因於：進場條件差異（實盤較主觀 vs 程式嚴格過濾）、出場策略差異（實盤移動停損 vs 程式 SatZone 兩段式）、或交易日篩選差異（程式跳過週三四）。

## Expected Distribution
- 實盤交易日與回測交易日的重疊率可能偏低（實盤無週間過濾、無 ORB% 門檻）
- 實盤勝率可能較高（主觀判斷加持），但單筆獲利可能不同
- 方向應該大致一致（都是逆勢）

## Invalidation Condition
- 實盤與回測的交易日重疊率 < 30%，表示兩者本質上是不同策略
- 實盤樣本數過少（< 15 筆），統計意義不足

## Notes
### 資料來源
- 實盤記錄：從 H044 的 `data/live_parsed.csv` 提取 strategy=exhaustion 的交易（N=57, 49 筆有損益）
- 回測記錄：從 ExhaustionStrategy 回測產出的 trades 提取對應日期範圍（2024/11~2026/3）

### 特殊考量
- 實盤標記為「放棄」但實際有做，代表當時不認為是正式策略信號
- S003 有 ORB% >= 0.25% 和跳過週三四的濾網，實盤沒有這些限制
- 比對重點不在精確匹配，而在理解程式化後損失/增加了什麼
