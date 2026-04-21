# Tasks: NVF Stability Audit by Weekday × Strategy × Period

## Phase 1: Distribution Research

### Task 1: 重建 NVF baseline & 健康總覽
- [x] 跑完三策略
- [x] 計算 night_norm
- [x] **重大發現：aggregate 訊號從 H066/H067 的 +83%/+64% 衰減到 +19.5%/+29.5%**
- [x] Exhaustion aggregate NVF Δ = −12.5%（負向）

### Task 2: Cell 矩陣（strategy × weekday × year）
- [x] Cell 矩陣完成
- [x] 19 個反向 cell（EstHL 5、Reversal 10、Exhaustion 4）
- [x] heatmap 視覺化 → h072_t2_heatmap.png

### Task 3: Rolling 2-year window
- [x] 5 視窗計算
- [x] **EstHL Tue 單調惡化** +0.76 → +0.22 → -0.46 → -1.04 → -1.65
- [x] EstHL Fri 5/5 視窗都負/零
- [x] 視覺化 → h072_t3_rolling.png

### Task 4: IS vs OOS
- [x] 4 個 drift cell：EstHL Mon, **EstHL Tue (嚴重)**, Reversal Wed, Exhaustion Thu
- [x] EstHL Tue：IS Δ +0.68 → OOS Δ -1.24

### Task 5: NVF 門檻 sweep
- [x] 9 個 suspect cell sweep
- [x] **EstHL Tue OOS：所有 threshold 都負，越高越糟，無解**
- [x] EstHL Fri 2024-26 無解
- [x] EstHL Mon OOS 在 1.15 救回（小 N）
- [x] Reversal Mon/Fri 2024-26 全可用
- [x] 視覺化 → h072_t5_threshold_sweep.png

### Task 6: Exhaustion control 對照
- [x] EstHL Mon, Tue 確認是 STRATEGY 問題（Exhaustion 同 cell NVF Δ 反向為正）
- [x] Reversal Wed 是 MARKET 問題（雙方都負，但 N 小）

---
### GATE
**問題：分佈結果是否支持進入 Phase 2？**

- 是否找到 ≥ 1 個反向 cell（ΔPF < 0, N ≥ 5）？
- 是否找到 ≥ 1 個 drift cell（IS 正向、OOS 反向）？
- 反向 cell 是否在門檻 sweep 後可救（換 threshold 變正向）？
- 失效模式是否一致（Exhaustion control 是否驗證為市場結構或策略特性）？

**判斷分支：**
- 0 反向 cell → Archive Rejected（H066/H067 健康，當前實作 OK）
- 1–3 反向 cell + 可被高門檻救 → Phase 2 設計 cell-specific patch
- > 3 反向 cell 或結構性 drift → Phase 2 重新審視 NVF 邏輯

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

**Phase 1 結果（2026-04-21）**：
- 19 個反向 cell + 4 個 drift cell + EstHL Tue 單調惡化
- threshold sweep 顯示 EstHL Tue/Fri/Exhaustion Thu 不可救
- Exhaustion control 確認 EstHL Tue 是策略特性問題
- NVF aggregate 訊號衰減 2-4×

詳見 `results/distribution.md`。等 GATE 裁示。

---

## Phase 2: Backtest（GATE 通過後規劃）

可能方向：
- [ ] 若 narrow patch：對特定 cell 加 skip 或調整 threshold，walk-forward 驗證
- [ ] 若 NVF 重設計：實作新邏輯（如 NVF + 時間因子、NVF + 其他 regime 指標）
- [ ] In-sample / out-of-sample 切割
- [ ] 與「不動」對照組對比，確認改動有 net 增益
