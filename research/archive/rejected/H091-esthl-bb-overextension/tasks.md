# Tasks: EstHL BB Over-extension Filter

## Phase 1: Distribution Research

### Pool A — Filtered S001 entries
- [x] 重放 2021–2026 期間所有 S001 EstHL 實際進場（VWAP / 30m MA20 / OR-width / skip Thu/Fri；NVF 未在 code 中實作）
- [x] 對每筆 entry，取 entry 當日「日盤第一根 30m bar (08:45-09:15)」的 BB%B(20, open, 2σ)
- [x] 標記是否 hit fixed SL（PnL ≤ −0.95 × EmaHL × 0.25）
- [x] 分桶統計：`(-∞,0]` / `(0,0.5]` / `(0.5,1]` / `(1,+∞)`
- [x] 計算每桶的 N、SL hit rate、平均 P&L

### Pool B — Raw ORB long breakout
- [x] 重放 2021–2026 期間所有 ORB long breakout 訊號（1m close > OR High，不過 S001 濾網）
- [x] 同樣抓 entry 時 30m BB%B，模擬 fixed SL 出場（scan 1m Low ≤ SL price）
- [x] 同樣分桶統計

### 跨年度穩定性
- [x] 拆 6 個年度（2021–2026 YTD），每年看 BB>1 桶 vs 整體 SL hit rate
- [x] 計算「方向一致年數」：Pool A 3 favorable（含邊際）/ 2 against / 1 neutral；Pool B 3/3 平手

### 視覺化
- [x] BB%B 分佈直方圖（`results/bbpct_hist.png`）
- [x] 各桶 SL hit rate 柱狀圖（`results/sl_rate_bars.png`）
- [x] 年度熱圖（`results/yearly_heatmap.png`）

### 產出
- [x] `results/distribution.md`
- [x] `explore.py`

---
### GATE
**問題：分佈結果是否支持進入回測？**

- [x] Pool A 中 BB%B > 1 桶樣本數 ≥ 20 筆（**N=61** ✅）
- [ ] Pool A BB%B > 1 桶 SL hit rate − 全樣本 SL hit rate ≥ 10pp（**實測 +0.2pp** ❌）
- [ ] 跨年度方向一致 ≥ 3 / 5 年（**Pool A 邊際 / Pool B 平手** ❌）
- [ ] Pool B 結果與 Pool A 方向一致（**Pool B 反向 −5.5pp** ❌）

**4 條 GATE 中僅 1 條通過。**

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑（**待使用者決定**）

---

## Phase 2: Backtest（GATE PASS 後啟動）

- [ ] 在 `src/strategies/orb.py` 加入 `skip_bb_above` 旗標（True 時 BB30_Above 為 True 就 skip entry）
- [ ] In-sample 回測：2020–2023，對比 baseline 的 PF / Sharpe / WR / Max DD / Worst streak
- [ ] Out-of-sample 驗證：2024–2025
- [ ] Walk-forward：每年滾動，看年度穩定性
- [ ] 敏感度：測試 BB%B 門檻 0.9 / 1.0 / 1.1，看 PF 變化曲線是否平滑
- [ ] 副作用檢查：被擋掉的交易實際 P&L 分佈（是否誤殺好交易）

### 產出
- [ ] `results/backtest.md`（含對比表、權益曲線、敏感度圖）
- [ ] `backtest.py`（回測腳本）

### Verdict
- [ ] PF 提升 ≥ 10%（或 Worst streak 收斂 ≥ 20%）→ Confirmed
- [ ] 效果在 OOS 不存在 → Inconclusive
- [ ] OOS 反向惡化 → Rejected
