# Archive: 5分K 120MA（均線值/扣抵）vs 收盤價 對後續 15/30 分鐘的預測力

## Status
Rejected

## Summary
測試在 9:00/9:15/9:30/9:45 觀察 close 相對 5分K 120MA（均線值法 or 扣抵法）的位置，
是否預測接下來 15/30 分鐘的方向。結論：訊號本身**沒有可交易的獨立方向 edge**；
唯一亮眼的「高波才有效」是 look-ahead 假象。

## Key Evidence
- 頭條指標用 drift-immune 的「多訊號 up-rate − 空訊號 up-rate」分離度 + 2000 次 IID 洗牌 null。
- **池化（30 分）**：扣抵法分離度 +1.4~+5.0pp，僅 9:30 勉強接近顯著（p=0.07），其餘 p>0.33；
  均線值法更弱。EV 僅數點（<成本）。
- **15 分 horizon 更弱**：9:30 扣抵從 +5.0pp/p=0.07 塌到 +2.3pp/p=0.46；均線值法 9:00 偏反向（−4.6pp）。
- **逐年不穩**：30 分 +0.1~+4.8pp（全 p>0.15、2023≈0）；15 分逐年翻號。過不了逐年關。
- **look-ahead 陷阱**：用「當日事後波動」分組，高波桶 30 分 +12.5pp/p<0.001、15 分 +6.5pp/p=0.005 —— 
  但改用「盤前可知的前一日波動」分組即塌（30 分 +2.4pp/p=0.327、15 分 +1.1pp/p=0.655），
  高波桶逐年每年 p 皆 >0.5。

## Why Rejected
觸發無效條件 #1（可交易資訊下分離度相對洗牌 null 無顯著提升）與 #3（唯一顯著效果為 look-ahead，
過不了逐年關）。訊號等於「今天回頭看是趨勢日 → 早盤動能延續」的同義反覆，9:00 當下不可交易。
樣本充足（每時點 N≈1,300，合計 5,316），非樣本數問題。

## Derived Hypotheses
- **DH-1**：動能延續只在趨勢日強烈。若用**盤前可知**的趨勢日 proxy（開盤跳空、前日 range、
  VIX regime、ladder reach 期望）先辨識趨勢日、再套動能方向，或許有條件 edge —— 但那是
  ex-ante regime 分類器的功勞、非本 MA 訊號。日後想做需另開新假設。
- **DH-2**：9:30 是四時點中唯一（30 分 horizon）接近顯著者（p=0.07）；若複查務必聚焦 9:30、
  用盤前可知的波動分組與逐年檢驗，避免重蹈 look-ahead。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Explore script：explore.py（horizon 參數化，`python explore.py 15|30`）
