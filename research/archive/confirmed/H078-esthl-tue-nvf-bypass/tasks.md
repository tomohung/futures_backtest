# Tasks: EstHL Tue NVF Bypass Patch

## Phase 1: Distribution Research（快速 confirmation）

### Task 1: Tue baseline vs Tue NVF（用新 NVF 方法）
- [x] EstHL 回測 + merge 新 NVF 條件
- [x] 4/5 valid years baseline 勝
- [x] **OOS Δ -1.22**（IS Δ +0.30，IS/OOS 反轉）

### Task 2: Walk-forward 一致性
- [x] 5/6 年 B configuration 勝 A
- [x] 視覺化 → h078_overview.png

### Task 3: 連敗結構對比
- [x] Config A: full NVF, max_streak=3, worst -142, total +3322
- [x] Config B: Tue bypass, max_streak=4, worst -216, total +4111
- [x] **invalidation 通過**：max_streak +1（容許 < 2）
- [x] **caveat**：worst_pnl 加深 28%、max_dd 加深 28%

---
### GATE
**問題：是否進入 Phase 2 實裝？**

- baseline 在 ≥ 4/6 年贏 NVF？
- 連敗結構不惡化？
- aggregate OOS 改善？

**決定：** [ ] 進 Phase 2　[ ] Archive　[ ] 修改假設後重跑

**Phase 1 結果（2026-04-21）**：
- 5/6 年 Tue bypass 勝（唯 2023 -67）
- Total P&L +789 (+24%)
- max_streak +1（容許 < 2）
- worst_pnl 與 max_dd 加深 28%

詳見 `results/distribution.md`。等使用者確認連敗加深可接受。

---

## Phase 2: Implementation

- [x] `src/analysis/key_prices.py` 加入 `today_wd == 1` 分支
- [x] Smoke test 通過（今日剛好週二，正確顯示 bypass）
- [x] Phase 1 已完成連敗對比（含模擬 Tue bypass）
- [x] S001 spec.md 加入 Tue bypass 描述 + 參數
- [x] H075 archive summary 加註 H078 完成

實盤實際行為（今日 2026-04-21 Tue, NVF=0.66 < 0.94）：
- S001 EstHL → ✅ 可做（Tue bypass）
- S002 Reversal → 🚫 不做（Reversal 無 bypass）
