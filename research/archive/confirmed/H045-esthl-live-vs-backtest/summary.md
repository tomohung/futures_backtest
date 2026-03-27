# Archive: EstHL 實盤 vs 回測比對

## Status
Confirmed

## Summary
比對 EstHL 策略 17 個月實盤記錄（76 筆 esthl + 21 筆 costline）與回測結果。確認策略方向邏輯完全正確（配對交易方向一致率 100%），進場無顯著滑價（中位 0 點），損益差異主因為出場時機。實盤大幅偏離 spec（Thu/Fri 交易、做空），但經分析確認原 spec 限制仍然合理。

## Key Evidence
- 配對交易方向一致率：100%（N=35 vs 預設 spec, N=55 vs 全開）
- 進場滑價中位數：0 點
- 實盤整體績效：96 筆，勝率 59.4%，PF 3.91，+6189 點
- Thu/Fri 做多回測：勝率 44%，靠少數大賺撐 → skip Thu/Fri 合理
- Thu/Fri 做空全歷史回測：57 筆，勝率 35%，PF 0.80 → 負期望值
- Mon-Wed 做空：6 筆 PF 0.84 → long-only 正確
- 漏接交易（回測有信號實盤未做）：23 筆中 15 筆虧損

## Why Confirmed
策略實作忠實反映回測邏輯，無系統性偏差需修正。方向判斷、進場價格完全一致，損益差異可歸因於出場時機差異（非結構性問題）。Spec 限制（skip Thu/Fri, long-only）經實盤數據再次驗證合理。

## Derived Hypotheses
- HXXX：EstHL Costline 策略 — 早盤 VWAP 下整理後突破 VWAP 進場，實盤 21 筆 71.4% 勝率 +1483 點
- HXXX：EstHL Mon-Wed 濾網檢視 — 9 筆被 OR%/VWAP 濾網擋掉但實盤獲利 +465 點

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Compare script：compare.py
- Thu/Fri short charts：results/thu_fri_short_charts.png
