# Archive: H019 — EstRange Credit Spread Profit Target 提早平倉

## Status
Inconclusive

## Summary
研究 credit spread 策略是否應加入 profit target 提早平倉機制，以降低尾部風險。透過分析 89 筆交易（2025-07 ~ 2026-03）的 credit capture 路徑，發現除了 Wed（DTE=0）外，其餘 weekday 的 theta 衰減太慢，profit target 幾乎不會觸發。最終決定不實作，維持現有固定 exit_time 方案。

## Key Evidence
- **Mon (DTE=2, n=27)**：120 分鐘後 mean captured 僅 13%, median 20%，theta 極慢
- **Tue (DTE=1, n=31)**：120 分鐘後 mean 31.9%, median 45.4%，少數大虧拉低 mean
- **Wed (DTE=0, n=12)**：唯一有加速的 weekday，30 分鐘 mean 52.5%，40 分鐘 69%。但樣本僅 12 筆，且現有 exit_time=10:30 已很早
- **Fri (DTE=0, n=19)**：std 爆炸 100%~400%，OTM 流動性差導致即時市價不可靠
- Minutes to reach 50% captured (mean)：只有 Wed 在 29 分鐘達到，其餘 weekday 都是 never

## Why Inconclusive
DTE>=1 的 captured% 太低、profit target 不會觸發；DTE=0 的 Wed 有潛力但樣本僅 12 筆；Fri 流動性問題導致價格雜訊太高。加上即時選擇權報價監控的系統複雜度大增，預期收益改善極小。結論是「已驗證不需要 profit target」，但因樣本不足無法完全排除 Wed 的可能性。

## Derived Hypotheses
- 無直接衍生假設（結論為維持現狀）

## Links
- Proposal: specs/strategies/2026-03-19-estrange-credit-spread-profit-target.md
