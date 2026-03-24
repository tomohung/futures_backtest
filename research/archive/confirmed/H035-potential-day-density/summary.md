# Archive: 滾動潛力日密度作為市場 regime 指標

## Status
Confirmed

## Summary
滾動 20 日潛力日（range_pct >= 1.0%）密度可以有效反映市場波動 regime。密度具有明顯的慣性（高低密度會持續數週至數月），已整合進 morning_briefing 作為每日觀測工具。

## Key Evidence
- 全期平均密度 50.7%，標準差 23.1%，波動幅度大（0% ~ 100%），有實用的區分能力
- 密度有 regime 慣性：一旦進入高密度（>60%）或低密度（<30%）會持續數週至數月（GARCH 效應）
- 2026/3 月密度 91.2% 與用戶觀察到的好績效完全吻合
- 不存在穩定的月份季節性 — 同月份跨年差異極大（如 1 月從 11% 到 83%），regime 切換是事件驅動而非日曆驅動
- 1,244 筆有效資料（2021-2026）

## Why Confirmed
密度指標成功達成觀測工具的目標：能量化波動 regime、具備慣性預測價值、已整合進每日簡報。雖然排除了月份季節性假設，但這本身也是有價值的結論。

## Derived Hypotheses
（暫無）

## Links
- Proposal：research/active/H035-potential-day-density/proposal.md
- Distribution：research/active/H035-potential-day-density/results/distribution.md
- 探索腳本：research/active/H035-potential-day-density/explore_density.py
- 整合位置：src/analysis/daily_range.py（第三 subplot + 終端 regime 判讀）
