# Proposal: Night Session 30m MACD + SMA Regime Classification

## ID
H056

## Derived From
Origin（原創，結合實盤觀察）

## Trading Intuition
含夜盤資料的 30 分 K MACD 搭配 SMA(5/21/65/130/233)，可以在日盤開盤前建立方向偏多/偏空/不做的 regime filter。不同的 MACD 狀態 × 均線空間組合，對應不同的日盤策略（趨勢突破 vs reversal vs 觀望）。

核心觀察：
1. **夜盤 MACD 穿越零軸**確認方向 → 日盤順勢走的機率高
2. **夜盤 MACD 出現背離** → 日盤開盤拉高後反而是做空機會（reversal 切入）
3. **均線多頭/空頭排列明確** → 搭配區間突破可抓趨勢段
4. **均線壓縮或中間有壓力**（如 5/21 金叉但 65 SMA 在上）→ 反彈空間有限，reversal 做空機會，但做多空間受限

## Hypothesis
根據日盤開盤前（或含第一根 30 分 K）的 MACD 狀態與 SMA 排列，可將交易日分類為以下 regime，各 regime 在日盤的報酬分佈具有統計顯著差異：

### 初步分類框架

| Regime | MACD 狀態 | SMA 排列 | 預期日盤行為 | 策略方向 |
|--------|-----------|----------|-------------|---------|
| **A: Trend-Long** | 夜盤 MACD 在零軸上方，或穿越零軸向上 | 多頭排列（短均線 > 長均線） | 順勢向上 | 突破做多 |
| **B: Trend-Short** | 夜盤 MACD 在零軸下方，或穿越零軸向下 | 空頭排列 | 順勢向下 | 突破做空 |
| **C: Reversal-Short** | 夜盤 MACD 出現頂背離，或 histogram 漸減 | 5/21 金叉但 65/130 在上方形成壓力 | 反彈受阻後回落 | Reversal 做空 |
| **D: Reversal-Long** | 夜盤 MACD 出現底背離，或 histogram 漸增 | 5/21 死叉但 65/130 在下方形成支撐 | 下殺後反彈 | Reversal 做多 |
| **E: Neutral** | MACD 接近零軸，方向不明 | 均線糾結 | 震盪無方向 | 不做 |

### 補充觀察
- Regime C 中，因均線壓力在上，reversal 做多通常不划算（價格在前日成本以下，空間有限）
- 日盤第一根 30 分 K 可能修正夜盤建立的 regime（如 A → E）
- **30 分 K 僅用於方向判讀與大區間規劃**，實際進出場切換到 1 分 K 觀察
- 這裡的「區間突破」指的是 1 分 K 層級的觀察，不是 30 分 K 的區間

## Expected Distribution
- 各 regime 出現的頻率大致均勻（不會極端集中在某一類）
- Regime A/B（趨勢型）的日盤報酬分佈偏向該方向，且標準差較大
- Regime C/D（反轉型）的報酬分佈與趨勢型有顯著差異
- Regime E 的報酬分佈接近零均值、低標準差

## Invalidation Condition
- 分類後各 regime 的日盤報酬分佈無統計差異（KS test p > 0.05）
- 樣本嚴重不均：某一類佔 >60%，其他類樣本不足
- 趨勢型 regime 的方向命中率 < 55%

## Notes
- SMA 選用 5/21/65/130/233，這是市場上最多人看的均線組合，具有自我實現效果
- 30 分 K 含夜盤資料（15:00 ~ 隔日 05:00 + 08:45 ~ 13:45）
- MACD 參數先用預設 (12, 26, 9)，後續可測試敏感度
- 背離定義採 Dow Theory 風格：swing high/low 以前後 5 根 K 線定義（某根 K 線的高點高於前後各 5 根的高點即為 swing high），比較連續兩個 swing high/low 與對應 MACD 值的方向是否一致。後續可用實際案例微調
- 此假設若 confirmed，可作為現有 EstHL / Reversal 策略的 regime filter
