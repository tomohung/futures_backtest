# Tasks: 盤前多空計分表有效性審計 + 早盤方向 edge 重探

## 共用評估 harness（兩 phase 共用，先建）

- [x] 母體：2021–2026 全歷史日盤（N=1263，扣換倉日 + 缺夜盤日）
- [x] 三時段窗口：`08:45–09:30`、`09:00–10:30`、`08:45–11:30`
- [x] outcome 1 — 方向命中率 vs base rate（含 same-mix 虛無 + vs 多數）
- [x] outcome 2 — 機械交易 P&L（窗口起點進、終點出、投票方向、成本 3 點/邊）→ PF / 勝率 / mean
- [x] 三道關卡：逐年拆 + regime 拆（VIX 中位）+ 方向與 P&L 並列
- [x] 每個訊號回傳統一結構（附樣本數），供比較

## Phase 1: Distribution Research（審計現有計分表）

- [x] 重建四個現有訊號的 causal 盤前讀數（比照 key_prices.py 邏輯，逐日）
- [x] 對 4 訊號 + 合計投票各跑 harness（3 窗口 × 2 outcome × 逐年/regime）
- [x] 關鍵比較：合計投票是否勝過最佳單一成分？→ **否，三窗口全未勝**
- [x] 視覺化：逐年 P&L heatmap（results/h133_yearly_heatmap.png）
- 結論見 results/distribution.md（GATE：H133-a 不成立 → 砍列）

---
### GATE（Phase 1 → Phase 2 / 審計結論）
**問題：現行計分表有沒有任何一列（或合計投票）值得留？**

- 樣本數是否足夠？（全歷史 ~1240 日，逐年每年 ~200 日）
- 合計投票或任一訊號：至少一窗口 **方向 lift > 0 且 P&L 為正**、逐年 **≥4/6 年一致**、且合計 > 最佳單一成分？
- 是否有 data snooping 疑慮？（多窗口 × 多訊號 → 逐年一致性即為 snooping guard）

**決定：** [ ] Phase 2 探索替代　[ ] 直接 Archive（審計結論=砍列/改基準）　[ ] 修改假設後重跑

> 註：即使 H133-a 全否，「砍哪幾列 / 改基準」仍是有效產出，直接回饋 key_prices.py。

---

## Phase 2: 替代訊號探索（盤前 + 開盤後確認）

- [x] 盤前動能候選（explore_macd.py / explore_momentum.py）：MACD 位準/動能/交叉、RSI/ROC/EMA20/隔夜動能 → **全無跨 regime edge**，高 RSI 續強是 2024-26 regime 假象
- [x] 開盤後候選（explore_postopen.py）：開盤段方向 + OR 量比≥1.0 + 跳週四五 → **lift 單調遞增，最佳 net +11.3 PF1.24 4/6，複刻 H018**
- [x] 每個候選跑同一 harness
- [x] Phase 2 GATE：開盤後 OR方向+量比+跳TF 過 4/6，但係複驗既有 H018/ORBLong（非新 edge）；盤前候選全不過

---
### GATE（Phase 2 → Backtest）
**問題：有沒有替代訊號的 P&L edge 逐年 ≥4/6 年成立、且優於現有成分？**

**決定：** [ ] 進 Backtest（開 derived 假設做濾網/策略）　[ ] Archive

---

## Phase 3: Backtest（僅在有候選晉級時）

- [ ] 定義進出場規則（盤前投票 + 開盤確認閘的組合）
- [ ] 設定回測參數（手續費、滑價）
- [ ] in-sample 回測 + out-of-sample 驗證
- [ ] Walk-forward（逐年比 IS/OOS 更可信，因 OOS≡高波 regime）
- [ ] 參數敏感度分析
