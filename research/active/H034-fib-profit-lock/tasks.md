# Tasks: Fib 1.618 觸及後選擇權鎖利

## Phase 1: Distribution Research

- [ ] 統計 Fib 1.618 觸及率（確認 H018 的近 6 成數字）
- [ ] 觸及後至收盤的走勢分佈（續漲/回落/橫盤比例、幅度）
- [ ] 觸及後續漲至 Fib 2.0 / 2.618 的比例
- [ ] 觸及時刻的 TXO ATM put 價格統計（用 ticks_options）
- [ ] 權利金成本 vs 尾段額外獲利的損益分析
- [ ] 產出 distribution.md + GATE 決定

---
### GATE
**問題：分佈結果是否支持進入回測？**
**決定：** [TODO]

---

## Phase 2: Backtest

- [ ] 模擬三種出場方式比較（直接平倉 / 買 put / 買 put spread）
- [ ] IS/OOS 驗證
- [ ] 流動性檢查（觸及時刻的 TXO 買賣價差）
