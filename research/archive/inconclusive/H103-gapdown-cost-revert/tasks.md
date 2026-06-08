# Tasks: 跳空跌破成本 → 折價回補做多（H103）

## Phase 1: Distribution Research（進出場機制探索）

條件樣本（open < 兩成本、up_clear_norm ≥ L4）已由 H102 確認 N≈111、方向 +17~26pp。
本階段聚焦**進出場機制**的分佈，產出 GATE。

- [ ] 沿用 H102 條件挑出樣本（可直接讀 `../H102-clear-runway-breakout/results/h102_daily.csv`）
- [ ] 進場時點分佈：開盤即進 vs 等首根止穩 vs 首次回測 → 各自的後續 MFE/MAE
- [ ] 回補達成率：進場後觸及「最近上方成本價」的比率 + 觸及所需時間分佈
- [ ] MFE / MAE 分佈（以 ema20 正規化）→ 估盈虧比上限
- [ ] up_clear_norm 分層 × 回補達成率（驗單調性是否延續）
- [ ] 反向風險：進場後最大不利擺動、跌破當日低/再破底的比率
- [ ] 旁路：與 NVF 的交集（高能量日是否本就 NVF pass）

---
### GATE
**問題：分佈是否支持進入回測？**
- 回補達成率明顯 > 往下續跌率？盈虧比看起來為正？
- up_clear_norm 與達成率單調？
- 反向風險（MAE / 破底率）可被合理停損涵蓋？
- 樣本 N≈111 夠不夠切 in/out-of-sample？

**決定：** [ ] 繼續 Phase 2　[ ] Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest（需先過 GATE）

- [x] 定義進出場：開盤即多、**目標=固定 0.7×ema20**（非成本）、停損 0.5×ema20
- [x] 回測參數（成本 3 點 round-trip）
- [x] in-sample vs baseline（開盤多→收盤、控制組 <L4）
- [x] out-of-sample 驗證（OOS 2024–26 正但衰減）
- [x] 門檻（0.8/L4/1.1/L5）+ 目標停損 + 成本 敏感度（全正、穩健）
- [x] 連敗長度 / drawdown（連敗 5、MDD 3.6%，可接受）
- [ ] 與 NVF / 既有策略組合的相容性（未做，可待前推階段）

→ 結果見 results/backtest.md，**Verdict = Inconclusive（傾向正面）**，backtest.py 已存。
