# Proposal: STARC 下軌觸及後反轉做多

## ID
H055

## Derived From
H050 Phase 0 批次 2 評估（D1 候選）

## Trading Intuition
STARC（Stoller Average Range Channel）用 SMA ± ATR 倍數建立通道。當日收盤跌破下軌，表示短期超跌——價格偏離均值太遠、波動率暗示過度延伸，次日反彈機率高。

H050 初步測試顯示：觸及 STARC 下軌後次日平均 +67~124pt，反轉率 64-67%。上軌則無明顯反轉效果（50%），因此聚焦下軌做多。

## Hypothesis
日線收盤低於 STARC 下軌（SMA(6) - 2×ATR(15)）時，次日做多有正期望值。反轉率 > 60%、次日平均報酬 > 50pt。

## Expected Distribution
- 信號頻率：~5%（63/1265 天，SMA6/ATR15/×2）
- 次日反轉率 > 60%（H050 初步：64-67%）
- 次日平均 PnL > +50pt（H050 初步：+67~124pt）
- 可能與 Exhaustion（S003）互補——都是超跌反轉，但 STARC 是日線級別

## Invalidation Condition
- IS/OOS 反轉率 < 55%（與隨機無異）
- 次日平均 PnL < +20pt（扣除成本後無 edge）
- 上軌做空也有相似效果（說明 STARC 只是捕捉波動，無方向性 edge）
- 樣本數不足（< 30 筆 IS）

## Notes
- 這是日線信號 → 日盤當沖策略，需要定義盤中的進出場時機
- SMA(6)/ATR(15)/×2 信號較少但較強；SMA(10)/ATR(14)/×2 信號多但稍弱
- 上軌觸及後次日並無明顯反轉（反轉率 ~48%），只測下軌
- 可考慮與 CHOP（H053）組合：STARC 觸下軌 + CHOP 非盤整 → 更強的反轉信號
- STARC 通道可對比 EstRange SatZone——兩者都是波動率通道，概念相似
