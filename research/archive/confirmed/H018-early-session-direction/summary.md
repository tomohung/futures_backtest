# Archive: H018 — 早盤方向偵測與波幅預測策略探索

## Status
Confirmed

## Summary
基於 H017 的日內波動研究結果，探索三個策略方向：A) 早盤方向偵測、B) 波幅預測（OR x Fib）、C) 單次機會策略（影線比）。方向 A 和 C 被明確排除，方向 B 的 Fib 策略找到有效組合但未優於現有 ORBLong，整體研究提供了有價值的參數發現但未產出新的獨立策略。

## Key Evidence
**方向 A（已排除）**：方向預測 r=0.30-0.44 但損益相關性 = 0。60m 窗口方向最準但損益反而為負。回拉進場（含 Fibonacci 回撤 0.236-0.786）全部虧損（PF 0.75-0.90）。

**方向 B（主要發現）**：
- OR x Fib 1.618 是最佳單段 TP：PF 1.41, total +7,365, MAE 最低（62）
- SL = OR x 0.5-0.618 為最佳停損範圍
- OR 段量比 >= 1.0 + 跳週四五：148 筆, 勝率 55.4%, PF 2.04, 唯一連 2022 都獲利（+271）
- 兩段式出場未優於單段（TP2 觸及率僅 1.6%）

**與 ORBLong 比較**：ORBLong PF 2.07 / 勝率 58.2% 仍優於 Fib 策略最佳組合 PF 2.04 / 勝率 55.4%。ORBLong 改 TP 1.618 幾乎無差異（+5,613 -> +5,659）。

**方向 C（已排除）**：影線比 PF 1.05, Sharpe 0.25。

## Why Confirmed
明確排除了方向 A（方向預測）和 C（影線比），方向 B 產出可量化的關鍵發現：OR x Fib 1.618 為最佳 TP（MAE 最低）、OR 段量比和跳週四五已回饋至 ORBLong 參數。研究結論清晰，為後續策略設計提供了堅實基礎。

## Derived Hypotheses
- OR 段量比 >= 0.7 可整合到 ORBLong（09:30 已知，無 lookahead）
- 跳週四五應一致套用到 ORBLong
- 做空策略：倒 V 型態在 45m 窗口做空有 +2,755 正期望值（待探索）
- Fib 策略與 ORBLong 重疊度分析
- **H034-fib-profit-lock**：Fib 1.618 觸及後用選擇權鎖利，保留 tail exposure

## Links
- Proposal: specs/strategies/2026-03-15-early-session-direction.md
