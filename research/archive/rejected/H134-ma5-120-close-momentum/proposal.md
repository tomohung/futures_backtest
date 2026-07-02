# Proposal: 5分K 120MA（均線值/扣抵）vs 收盤價 對後續 30 分鐘的預測力

## ID
H134

## Derived From
Origin（原創）；操作上與 key_prices 盤前「30分K 20MA 扣抵法方向加分」（commit fe0d442 / 6aa3ed4）同源。
本假設改用 **5分K 120MA**（涵蓋同樣 600 分鐘窗口，但每 5 分鐘更新，檢查時點更即時），
把該方向分驗證成盤中實際的 30 分鐘預測力。

## Trading Intuition
在早盤固定時點（9:00 / 9:15 / 9:30 / 9:45）觀察指數相對 5分K 120MA 的位置：
- 若收盤價在 120MA 之上（或扣抵法顯示均線上彎）→ 多方動能，預期接下來 30 分鐘續漲
- 反之在 120MA 之下（或均線下彎）→ 空方動能，預期接下來 30 分鐘續跌

例：9:00 指數在均線之上（做多偏向），9:30 收紅 K（上漲）；反之亦然。

## Hypothesis
在 9:00 / 9:15 / 9:30 / 9:45 四個檢查時點，以 5分K 120MA（對齊 08:45 的 5 分 bucket、
日盤 08:45–13:45、120MA over 已完成的 5 分 bar）為基準，
訊號方向（close vs 120MA 值，或 close vs 扣抵值）能預測**接下來 30 分鐘**的價格方向，
方向命中率顯著高於基準漂移（base rate），且順著訊號方向的 30 分鐘報酬具有正 EV（點數/%）。

兩組訊號定義並列比較：
- **均線值法**：close(T) 在 120MA 值之上/之下
- **扣抵法**：close(T) vs 扣抵值（120 根前那根 bar 的 close）→ 判均線上彎/下彎

兩組 outcome 並列量測：
- **方向命中率**：sign(price(T+30) − price(T)) 是否與訊號方向一致
- **報酬分佈**：順訊號方向持有 30 分鐘的帶符號報酬（點數 / %），看 EV 與分佈形狀

## Expected Distribution
- 四個時點 × 兩種訊號定義，各自的方向命中率
- 若假設成立：命中率應明顯 > base rate（考慮早盤本身的方向漂移後仍有 edge），順向報酬 EV > 0
- 預期扣抵法（領先均線值）在越早時點（9:00/9:15）越可能有 edge；越晚時點趨勢可能已耗盡

## Invalidation Condition
符合以下任一即視為不成立：
1. 方向命中率相對正確虛無分佈（base rate / 前瞻條件期望 / IID 洗牌）沒有顯著提升（實務門檻：淨提升 ≤ ~2pp，或 CI 涵蓋 0）
2. 順訊號方向的 30 分鐘報酬 EV ≤ 0（未計成本前就無 edge）
3. 效果只在池化（pooled）時出現，但**逐年 / 子期間 / regime** 任一切分翻號或消失
   （比照 elec_fin 方法論：池化 t 須過逐年/子期間/regime 三關）

## Notes
- 全部時間為台灣時區，日盤 08:45–13:45，5 分 bar 對齊 08:45。資料來源 ohlcv_1m（TX）。
- 120 根 5 分 bar = 600 分鐘 ≈ 2 個日盤，與 30分K 20MA 同窗長但更即時。
- 扣抵值 = 120 窗口中最舊那根 bar 的 close（下一根 MA 將扣掉它）；close > 扣抵 → 均線將上彎。
- 檢查時點的 120MA/扣抵只用「已完成」的 5 分 bar；price(T) = T 當下（收 T 那根 5 分 bar 的 close）。
- **虛無分佈守門**（feedback_excursion_needs_forward_tautology_guard）：早盤本身有方向漂移，
  必須對比 base rate 與 IID 洗牌，否則描述性相關會被誤當 edge。
- **regime 混淆守門**（project_oos_equals_highvol_regime）：OOS(2026-03~06)≡高波 regime，
  IS/OOS 結論恐與單次低波→高波切換 confounded；命中率須跨 regime 檢視。
- 若命中，衍生方向：可否成為 EstHL/Reversal 的盤中方向濾網，或 key_prices 方向分的實證背書。
