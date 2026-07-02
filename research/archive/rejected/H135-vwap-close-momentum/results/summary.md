# Archive: close vs 當日 VWAP 在 9:00/9:15/9:30/9:45 對後續 15/30 分鐘的預測力

## Status
Rejected（binary 版）；衍生出強力的條件化假設 DH-1（暫未開）

## Summary
測「close 在當日 VWAP 之上/之下 → 後 15/30 分同向」。binary sign 版**無 edge**：池化分離度近零、
逐年翻號、唯一顯著格為 2025 高波日的反向 fade。但**強度分層**後發現：續攻只在「遠離 VWAP +
VWAP 斜率同向」cell 成立（+6.5pp / p=0.009 / 5-6 年同號），且此結構為 VWAP 特有（5分120MA 無）。

## Key Evidence
- **binary（reject 依據）**：四時點分離度 ±2pp、p 全 >0.25；逐年 2022 +2.9 / 2025 −5.3 / 2026 +6.4pp
  翻號；盤前可知波動 tertile 全 null；唯一顯著=2025 高波 −10.5pp(30分)/−13.4pp(15分,p=0.004) 反向。
  樣本 N=5,328。
- **條件化（衍生 edge）**：near −0.7pp(p=0.82) / mid −4.7pp(p=0.054, fade) / far **+5.1pp(p=0.035)**；
  **far+aligned +6.5pp / 命中53.4% / p=0.009**、逐年 5/6 正（僅 2021 −0.2）、集中 9:15(+11.5pp,p=0.02)/9:30。
- **MA 對照（區辨關鍵）**：5分120MA 同分層 far+aligned 僅 +2.1pp/p=0.47、逐年 3 正 3 負 → 無結構。
  → edge 來自「當日盤中、開盤錨的趨勢強度」（VWAP/intraday-anchored 抓得到），非趨勢延伸本身、
  非 trailing 2 日均線。

## Why Rejected
本假設陳述的是 **binary** sign(close−VWAP) 方向預測：觸發無效條件 #1（分離度不顯著、p>0.25）
與 #3（逐年翻號、含顯著反向年）。條件化 edge 屬另一個更精確的假設，不算本 binary 假設成立。
條件化 edge 亦有保留：逐年單獨不顯著（每年 N~200-330）、池化 p 為搜尋過 cell（data-snooping）、EV 需扣成本。

## Derived Hypotheses
- **DH-1（主，暫未開）**：TX 早盤「遠離 VWAP + VWAP 同向」→ 後 30 分續攻，為 intraday-anchored 特有。
  正式驗證需：ex-ante 固定距離門檻、成本、OOS/walk-forward、對照「離 open 幅度」以確認 VWAP 增量。
- **DH-2**：中距 fade（mid −4.7~−7.7pp 顯著）→「近/中距 fade、遠距 momentum」雙態框架。
- **DH-3**：H134+H135 binary 皆 reject → 單一分水嶺 binary 方向訊號在 TX 早盤普遍無 edge，
  但強度分層後參考線類想法仍可能有條件 edge。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Scripts：explore.py（binary, horizon 參數化）、explore_conditional.py（VWAP 距離×斜率）、
  explore_ma_conditional.py（MA 對照）
