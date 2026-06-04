# Archive: Reversal 方向濾網替換（納入夜盤）

## Status
Rejected

## Summary
測試把 reversal 的方向濾網從現行「5m 120MA、只日盤斜率」(base) 換成三種納入夜盤的替代：
A=5m 240MA 連續斜率、B=1H MACD(12/26/9) 線 vs Signal、C=A∩B 同向。唯一變數為方向濾網，
其餘 reversal 邏輯不動。結果三情境全部劣於 base，方向濾網維持現狀。

## Key Evidence
全期 2020-12-31 ~ 2026-06-03（base n=508）：

| 變體 | 總損益% | Sharpe | PF | 勝率 | 最大連敗 | 最大回撤% |
|------|---------|--------|----|----|---------|-----------|
| **base** | **+9.98** | **0.058** | **1.18** | **45.3%** | 9 | **−4.39** |
| A | +4.63 | 0.029 | 1.08 | 43.6% | 11 | −4.43 |
| B | −9.06 | −0.070 | 0.84 | 37.2% | 12 | −12.15 |
| C | −5.52 | −0.054 | 0.87 | 39.0% | 9 | −8.32 |

- IS/OOS 與年度分段方向一致：base 在每個子區間都最佳（OOS PF 1.56 / Sharpe 0.151）。
- 樣本足夠（三情境 IS ≥ 80，C 的 OOS=89 ≥ 80），結論可靠。
- Phase 1：base vs A 方向歧異 20.4%、vs B 53.9%；C 同向 735/1308 日（56%）。

## Why Rejected
- **A（納夜盤+拉長 MA）**：與 base 僅 20% 方向歧異，但那 20% 淨虧，且最大連敗 9→11 變差。損益% 與 Sharpe 均劣於 base。
- **B（1H MACD）**：對「BB 超買超賣反轉」進場而言近乎反指標（勝率掉到 37%、回撤翻倍到 −12%），主動傷害績效。
- **C（雙濾網同向）**：只是繼承 B 的傷害，A 救不回。
- 反向印證 `runner.py:520` 設計註解「Use day-session only so overnight data doesn't distort direction」——納夜盤確實稀釋方向判斷品質。

## Derived Hypotheses
- **H101-d1**：B 窗內方向最穩（翻轉率 12%）卻是反指標 → 可探討「1H MACD 多頭時反而適合做空 BB 超買」，把 MACD 當**反向**確認或用於趨勢順勢策略族。
- **觀察**：base 獲利集中在 2023 之後（2021–2022 接近零），方向濾網非主要 alpha 來源；reversal 的 edge 更可能在 BB/SatZone/出場結構。

## Code Note
`src/strategies/reversal.py` 保留 `dir_mode` 參數（預設 "base" = live 行為不變），方向判定抽成 `_direction()` 方法，供本研究 backtest.py 重跑四變體。live 行為零變動。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md
- Scripts：explore.py, backtest.py
