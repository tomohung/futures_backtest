# Proposal: close vs 當日 VWAP 在 9:00/9:15/9:30/9:45 對後續 30 分鐘的預測力

## ID
H135

## Derived From
Origin（原創）；框架沿用 H134（同檢查時點、同 outcome、同守門與方法學），
差別在訊號改用**當日日盤 VWAP**（非 5分K 120MA）。

## Trading Intuition
在早盤固定時點（9:00 / 9:15 / 9:30 / 9:45）觀察指數相對「當日 VWAP」的位置：
- 若 close 在 VWAP 之上 → 多方掌控，預期接下來 30 分鐘走多機率與 EV 偏高
- 反之在 VWAP 之下 → 空方掌控，預期接下來 30 分鐘走空

VWAP 是當沖公認的多空分水嶺（機構均價），假設它比 MA 更能反映當日買賣力道。

## Hypothesis
在 9:00 / 9:15 / 9:30 / 9:45，以「當日日盤累積 VWAP（08:45 起、typical price=(H+L+C)/3 加權、每日重置）」為基準，
訊號 sign(close(T) − VWAP(T)) 能預測**接下來 30 分鐘**的價格方向：
- 方向命中率 / 走多機率顯著高於 base rate（drift-immune 分離度 > 0 且過洗牌 null）
- 順訊號方向持有 30 分鐘的報酬具正 EV（點數 / %）

## Expected Distribution
- 四個時點各自的「多訊號 up-rate」「空訊號 up-rate」與分離度、命中率、EV
- 若成立：close>VWAP 的走多機率明顯 > close<VWAP；分離度顯著為正、EV>0
- 預期越早時點（VWAP 樣本少、噪音大）可能較弱；9:30/9:45 VWAP 較穩或較強

## Invalidation Condition
符合以下任一即視為不成立：
1. 方向分離度相對 IID 洗牌 null 無顯著提升（實務門檻：淨提升 ≤ ~2pp 或 p>0.1）
2. 順訊號 30 分鐘報酬 EV ≤ 0（未計成本前就無 edge）
3. 效果只在池化出現，但**逐年 / regime（盤前可知波動 tertile）** 任一切分翻號或消失
   （比照 H134 教訓：拒絕以「當日事後波動」分組製造的 look-ahead 假象）

## Notes
- 資料 ohlcv_1m（TX），日盤 08:45–13:45。VWAP 用 1 分 bar typical×volume 累積、每日重置。
- price(T) 與 outcome 定義同 H134：signal 取 T−1min 那根 1 分 bar close，outcome 取 T+H−1min close，
  H=30（主）、15（敏感度）。VWAP(T) = 累積到 signal 那根。
- **虛無分佈守門**：早盤有方向漂移，頭條用 drift-immune 分離度 + 2000 次 IID 洗牌 null。
- **regime 守門**：波動 regime 必用「盤前可知（前一日波動）」分組，禁用當日事後波動（H134 的 look-ahead 陷阱）。
- 與 H134 對照：若 VWAP 有 edge 而 MA 沒有，代表 edge 來自「當日均價/成交量分佈」而非「趨勢延伸」。
- 若命中，衍生方向：VWAP 站上/跌破可作 EstHL/Reversal 的盤中方向濾網。
