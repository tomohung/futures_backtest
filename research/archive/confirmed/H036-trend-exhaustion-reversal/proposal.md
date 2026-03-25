# Proposal: 趨勢竭盡反轉

## ID
H036

## Derived From
Origin（用戶實盤策略，未經回測驗證）；部分概念延續 H033（缺口竭盡反轉的教訓）

## Trading Intuition
當日盤趨勢已經走到極端（30 分 K 20MA 方向明確 + BB%B(open) > 1 表示已超出常態），且夜盤進一步推升創近二日新高/低並收在高/低位，代表多/空方力竭。此時若日盤開盤區間被反向突破，是竭盡反轉的高概率進場點。

與 H033 的差別：H033 只看夜盤缺口大小，不考慮趨勢背景和延伸程度。本假設的核心是**趨勢已延伸到極端**才做反轉，是有條件的逆勢交易。

## Hypothesis
在以下複合條件同時成立時，ORB 反向突破後的反轉交易具有正期望值：
1. 30 分 K 20MA 方向明確（趨勢存在）
2. 30 分 K BB%B(20, open) > 1 或 < 0（價格在趨勢方向已超出常態）
3. 夜盤創近二日新高/低，且收在相對高/低位（close > high - EmaHL×0.5 或 close < low + EmaHL×0.5）
4. 日盤 ORB(08:45-08:58) 被反向突破

## Expected Distribution
- 符合條件的交易日：年均 30~60 天（每 4~8 個交易日一次）
- 反轉方向勝率 >= 55%
- 平均獲利 / 平均虧損 >= 1.0（搭配 EstHL 出場）
- Profit Factor >= 1.3
- IS/OOS 績效一致

## Invalidation Condition
- 符合條件的樣本 < 每年 15 筆（太少無統計意義）
- 勝率 < 45% 且 PF < 1.0（無 edge）
- IS 正但 OOS 崩壞（over-fit）

## Notes

### 條件定義

**30 分 K 20MA 方向：**
- 日盤 30 分 K close 的 SMA(20)
- 方向判定：MA > 前一根 MA → 向上；反之向下

**BB%B(20, open)：**
- 對日盤 30 分 K 的 **open** 計算 Bollinger Bands(20, 2σ)
- BB%B = (open - lower) / (upper - lower)
- > 1 表示開盤價在上軌之上（多方極端）
- < 0 表示開盤價在下軌之下（空方極端）
- 使用 open 的好處：08:45 開盤就有值，不需等 bar 收完

**夜盤創新高低 + 收相對高低：**
- 近二日 = 最近 2 個完整交易日的日盤 high/low
- 夜盤 high > 近二日 high → 創新高；夜盤 low < 近二日 low → 創新低
- 收相對高：night_close > night_high - EmaHL × 0.5
- 收相對低：night_close < night_low + EmaHL × 0.5

**進場：**
- 多方竭盡（做空）：MA↑ + BB%B > 1 + 夜盤創新高收高 → ORB 破低進場
- 空方竭盡（做多）：MA↓ + BB%B < 0 + 夜盤創新低收低 → ORB 破高進場

**出場：同 EstHL（S001）**
- SatZone 兩段式（觸碰 SatZone → 跌破/突破 5MA）
- 停損 = EmaHL × 0.25
- Dow Theory trailing stop
- 13:45 強制平倉

### 與現有策略的關係
- EstHL (S001)：同向（順趨勢），本策略逆向
- Reversal：都是反轉策略，但 Reversal 的進場條件不同
- 兩者可能有互補效果（不同市況觸發不同策略）
