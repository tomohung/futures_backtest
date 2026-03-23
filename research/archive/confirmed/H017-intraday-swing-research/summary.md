# Archive: H017 — 日內波段交易研究（波動預測與時段分析）

## Status
Confirmed

## Summary
系統性研究日內波動特性的 7 個核心問題（波動集中時段、高低點分佈、剩餘波幅、MAE、目標價到達後反向、停損再進場、加碼），目標是為新策略提供數據基礎。研究計畫完整但屬於探索性質，產出的分析腳本 `src/analysis/intraday_swing_research.py` 已完成，結果被後續的 H018 early-session-direction 研究消化。

## Key Evidence
- 開盤 30 分鐘吃掉全日 48.6% 波幅，到 09:45 已達 65.4%
- 上漲日 85.8% 低點先出現，下跌日 90.7% 高點先出現
- 無方向濾網時 MFE/MAE = 1.0，沒有交易優勢
- 停損後再進場回升率僅 25%
- 波幅消耗 100% 後反轉率 49%（接近隨機）
- 新高事件加碼邊際遞減，第 1-3 次最有價值

## Why Confirmed
純數據探索（Q1-Q7）成功產出可量化的日內波動特性，核心發現已被後續研究（H018 early-session-direction）吸收並轉化為具體方向測試。關鍵洞察（開盤 30 分鐘佔 48.6% 波幅、高低點先後順序）為策略設計提供了堅實的數據基礎。

## Derived Hypotheses
- H018 early-session-direction（方向 A/B/C 探索）
- OR x Fib 1.618 作為最佳 TP 目標的發現
- OR 段量比作為篩選因子的潛力

## Links
- Proposal: specs/strategies/2026-03-15-intraday-swing-research.md
