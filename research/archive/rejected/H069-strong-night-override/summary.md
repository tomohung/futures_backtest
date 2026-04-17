# Archive: Strong Night Vol Override on Weak Weekdays

## Status
Rejected

## Summary
測試強夜盤（norm >= 1.0~1.5）能否逆轉弱勢星期。EstHL 週四 IS/OOS 嚴重不一致（IS PF=8.39, OOS PF=0.80），rejected。Reversal 週五 norm >= 1.30 方向正確（跨年 5/6, PF=2.34），但 OOS 樣本僅 6 筆，inconclusive。EstHL 週五和 Reversal 週一確認無救。

## Key Evidence
- EstHL Thu: IS PF 高達 8.39 但 OOS 全崩（PF < 1.0），2025 年全虧
- Reversal Fri >= 1.30: PF=2.34, 移除最佳後 1.93, 跨年 5/6，但 IS=1.56 偏弱、OOS N=6
- Reversal Mon: 夜盤越強越差（PF 0.74 → 0.36），結構性無法逆轉

## Why Rejected
強夜盤無法穩定逆轉弱勢星期。EstHL Thu IS/OOS 不一致，Reversal Fri 樣本不足且 IS 偏弱，Reversal Mon 方向完全相反。不值得增加規則複雜度。

## Derived Hypotheses
- 未來可重新評估 Reversal Fri × norm >= 1.30（累積至 OOS N >= 15 時）

## Links
- Proposal：proposal.md
- Results：results/distribution.md
- Explore script：explore.py
