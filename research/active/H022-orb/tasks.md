# Tasks: Opening Range Breakout 基礎策略

## Phase 1: Distribution Research

- [x] 定義 ORB 策略規則（開盤區間、突破進場、停損停利、追蹤停損）
- [x] 實作 `ORBStrategy` class（`src/strategies/orb.py`）
- [x] 實作 `runner.py` 資料載入 + 執行器
- [x] 全參數掃描 1,088 組（2023-2025）
- [x] 分析 Pareto 前緣與勝率/盈虧比取捨

---
### GATE
**問題：分佈結果是否支持進入回測？**
**決定：** 裸 ORB edge 不足（勝率 44.9%、PF 1.02），結構性限制而非參數問題。需要加入過濾器改善（→ H023）。已完成探索，進入下一階段迭代。

---

## Phase 2: Backtest

- [x] 基準版回測（2023-2025）：勝率 44.9%、PF 1.02、期望值 +1.0 pts/筆
- [x] 確認策略需要過濾器而非參數最佳化
- [x] 衍生出 H023（過濾器）、H024（Phase 2 全參數）等後續假設
