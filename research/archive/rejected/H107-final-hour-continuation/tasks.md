# Tasks: 尾盤趨勢延續（Final-Hour Continuation）

## Phase 1: Distribution Research（零策略，早盤 vs 尾盤對比）

### 資料準備 + 切點校準（資料驅動）
- [x] date×minute pivot；ATR(前10日range, shift) 正規化
- [x] 30 分區塊動能矩陣 → 續行 corr 全日 <0.05，無集中於尾盤
- [x] 驗 last 30/45/60 三切點 → 一致地無尾盤續行

### 操作化 1：方向動能續行（錨點 t）
- [x] corr(進場前, t→收) 早盤 ~0.01 / 尾盤 ~0.04（經濟為零）；同向率全程 ~50%
- [x] forward 以 ATR 正規化（剩餘 ATR 均：尾盤 0.16 vs 早盤 0.46，已反映時間衰減）
- [x] 趨勢強度條件化：強趨勢進尾盤續行率仍 ~50%、剩餘 +0.02 ATR → 趨勢日也不續行

### 操作化 2：突破續行（錨點 t）
- [x] 破前30分區間 → 延伸率 vs 回補；**早盤 09:15 +5.8% 最強、尾盤 12:45 −8.3% fade**
- [x] 尾盤 vs 早盤對比 + baseline 漂移對照 → 與 Angell 方向相反

### 守門對照（防偽訊號）
- [x] 尾盤續行**未高於早盤**（反而低/相反）→ 無 time-of-day 續行效應
- [x] 正規化後尾盤無超額續行（純收斂段）
- [x] 視覺化：results/h107_distribution.png（續行 corr + 突破淨續行 vs 錨點，尾盤段標黃）

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 樣本數是否足夠？（每錨點 ~1300 日；突破事件每切點 ≥ 100）
- 尾盤續行是否**顯著高於早盤** + 超 baseline/洗牌？切點是否穩健（30/45/60 一致）？
- 兩種操作化是否一致？是否有 data snooping（切點、Δ、ATR 視窗）？
- 是否只在趨勢日成立（需條件化揭露）？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest（GATE 通過才做）

- [ ] 定義「尾盤突破續行進場 / 早盤不追」規則（切點、突破定義、出場）
- [ ] 設定手續費、滑價；in-sample / out-of-sample / walk-forward
- [ ] 與 H030 ORB（開盤）對照：尾盤版是否提供互補、低相關 edge
- [ ] 參數敏感度（切點、突破區間長度、出場）；含連敗/DD（[[feedback_filter_eval_includes_streaks]]）
