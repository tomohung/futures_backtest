# Tasks: Tuesday Volatility Paradox

## Phase 1: Distribution Research

### Task 1: 重新驗證 weekday × strategy 績效
- [x] 載入 EstHL、Reversal、Exhaustion 三策略的歷史交易（2021–2026）
- [x] 按星期幾切片，計算 PF / avg P&L / 勝率 / 樣本數
- [x] 對比週二 vs 全週中位數 → Tue 在 Reversal/Exhaustion 是最佳，EstHL 中段
- [x] 跨年穩定性 → 2024 三策略都偏弱，可能是 recency bias 來源

### Task 2: 雙向甩動假說檢驗
- [x] efficiency ratio：Tue 0.0749 vs others 0.0641（+16.8%，更趨勢非更甩動）
- [x] H/L 出現時間 std：Tue 與其他天接近，無顯著分散
- [x] 假說 **反駁**：Tue 是大振幅+明確方向

### Task 3: 進場後反轉率
- [x] MAE/MFE 計算
- [x] EstHL Tue +20.2%、Reversal Tue −40.1%、Exhaustion Tue −25.8%
- [x] 只有 EstHL 顯示 Tue 反轉壓力較高，但 PF 仍 1.74 > 1

### Task 4: 趨勢濾網交叉
- [x] TrendMA 已取得
- [x] 三策略切片 → EstHL 是 long_only、Exhaustion 是逆勢，TrendMA 切片不適用
- [x] Reversal Tue with-trend N=89 PF=1.82，與其他天相比不算特別差

### Task 5: 夜盤波動濾網交叉
- [x] NVF=0.85 套用後
- [x] EstHL Tue：base 1.74 → NVF 1.38（**反向作用**，唯一案例）
- [x] Tue 弱勢無法被夜盤濾網解釋，反而被放大

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 三策略中至少兩個的週二 PF 落於該策略所有日子的後 40%？
- 至少一個假說（雙向甩動 / 反轉率 / 趨勢逆向）有顯著證據（差距 > 15%）？
- 週二樣本數 ≥ 200？
- 是否被既有 H066/H067 夜盤濾網完全解釋？（若是則直接 archive）

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

**Phase 1 結果（2026-04-21）**：
- 三策略 Tue PF 落於後 40%：**0/3**（Reversal/Exhaustion 是 5/5 最佳，EstHL 是 3/5 中段）
- 雙向甩動假說：**反駁**（Tue efficiency +17%）
- MAE/MFE：只有 EstHL Tue +20%，Reversal/Exhaustion 反而 −25~40%
- Tue 樣本：EstHL 61 / Reversal 97 / Exhaustion 21（合計 179，Exhaustion 偏小）
- NVF 不能解釋 Tue 弱勢

詳見 `results/distribution.md`。等使用者裁示 GATE。

---

## Phase 2: Backtest

（Phase 1 通過 GATE 後再規劃，可能方向：）

- [ ] 根據 Phase 1 找到的特徵設計週二進場濾網（例如：週二需 ER > X 才進場）
- [ ] In-sample / out-of-sample 切割
- [ ] Walk-forward 驗證
- [ ] 與「直接 skip 週二」做對比，看濾網是否優於完全跳過
