# Proposal: SatZone 觸碰後三情境機率統計

## ID
H032

## Derived From
H021（策略 F — SatZone 後 Credit Spread）

## Trading Intuition
EstRange 的 SatZone 代表「當日預估波動已消耗」的區域。觸碰 SatZone 後，市場可能出現三種情境：長尾延續（趨勢繼續突破）、橫盤（波動耗盡）、反向（碰到對面 SatZone）。若橫盤+長尾的合計機率夠高，SatZone 觸碰後賣出反向 credit spread 就是正期望值策略。

## Hypothesis
SatZone 觸碰後，「橫盤」和「長尾延續」兩種情境的合計機率 >= 75%，「反向碰到對面 SatZone」的機率 <= 10%。這使得 SatZone 觸碰作為 credit spread 進場信號具有統計優勢。

## Expected Distribution
- 橫盤機率 >= 50%
- 長尾延續機率 >= 20%
- 反向觸碰對面 SatZone 機率 <= 10%
- 分年度穩定（各年度不應有劇烈偏離）

## Invalidation Condition
- 反向觸碰對面 SatZone 機率 > 20%（風險太高，credit spread 不可行）
- 三情境分佈在不同年度間不穩定（效果不可靠）

## Notes
### 分析方法
1. 用 `ohlcv_1m` + EstRange/SatZone 計算每日 SatZone upper/lower
2. 逐日判斷是否觸碰 SatZone（任一邊）
3. 觸碰後統計收盤時的情境：
   - **長尾延續**：收盤在觸碰方向的 SatZone 外
   - **橫盤**：收盤回到 SatZone 與中線之間
   - **反向**：收盤觸碰或超過對面 SatZone
4. 依年度、方向（UP/DOWN）、觸碰時間分層統計

### 資料需求
- `ohlcv_1m`（TX 日盤）
- EstRange 計算邏輯（`src/backtest/estimate_hl.py`）
- 不需要選擇權資料（這是 Step 0 機率統計，不是回測）

### 與 H021 的關係
這是 H021 spec 中「下一步 1」的獨立假設化。結果直接決定策略 F（SatZone 後 Credit Spread）是否值得發展。
