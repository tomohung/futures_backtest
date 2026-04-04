# Archive: XQ 發財橘子純價量策略候選清單

## Status
Rejected

## Summary
系統性掃描 XQ 發財橘子部落格 62 個純價量策略/指標候選，評估其在台指期 5mK 日盤當沖的適用性。34 個候選已測試，4 個建了獨立假說（H052~H055），全部 Rejected。量價類（C 類 7 個）、動能震盪類（B 類 7 個）、趨勢跟隨類（A 類 5 個）在台指期上均無 edge。唯一亮點為「大跌後次日做多」（PF=2.04），但 edge 來自隔夜 gap，盤中無法使用。

## Key Evidence
- 34/62 候選已評估，29 個淘汰，5 個有初步亮點但深入驗證後全部失敗
- C 類量價指標（C1~C6, C10）：7 個全部 PF≈1.0，量價分析在台指期無效
- B 類動能震盪（B1~B3, B5~B7, B11）：7 個全部 PF<1.05
- A 類趨勢跟隨（A1~A5）：5 個全部 PF<1.24
- F 類 K 線型態：只有「大跌後做多」有 edge（PF=2.04, N=45），但與 H055 STARC 相同問題（隔夜 gap）
- 衍生假說：H052 開盤動量 Rejected、H053 CHOP 濾網 Rejected、H054 VSA Rejected、H055 STARC Rejected

## Why Rejected
- 34 個候選充分取樣後，沒有任何一個成功轉為 live 策略
- 這些策略原為台股個股設計，台指期被機構和程式交易主導，傳統技術指標的行為偏差已被套利消除
- 邊際效益遞減，繼續掃描剩餘 28 個候選的預期價值極低

## Derived Hypotheses
- ~~H052 開盤動量~~ → Rejected
- ~~H053 CHOP 濾網~~ → Rejected
- ~~H054 VSA 無供應~~ → Rejected
- ~~H055 STARC 下軌~~ → Rejected
- H0XX：大跌後做多（前日跌>1.5% 次日做多 PF=2.04 N=45）— 需確認盤中可用性，避免重蹈 H055 覆轍

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Explore Scripts：explore.py, explore_batch2.py, explore_batch4.py, explore_batch5_full_scan.py
- 候選清單：xq-eddie-strategy-candidates.md
