# Tasks: 連虧後收手（Losing-Streak Persistence）

## Phase 1: Distribution Research（條件期望 vs IID 虛無）

### 資料準備
- [x] 重跑 EstHL（S001）、Reversal（S002）→ 全期 trade log（EstHL N=170、Reversal N=508）
- [x] 確認 1 筆/日、計連虧序列；無條件基準 EstHL +0.159%/59%、Reversal +0.020%/45%

### 條件期望（描述性）
- [x] `E[下一筆|前 k 連虧]`、勝率，k=1..4（各策略 + 合併池）→ 各策略未顯著偏離基準
- [x] 對稱檢查：連贏 k 後下一筆（EstHL 緩降、Reversal 平）

### IID guard（賭徒謬誤防呆，judgement 依據）★核心
- [x] lag-1 自相關（損益+勝負）+ runs test → 兩策略皆 ≈0（無自相關）
- [x] 洗牌虛無 N=5000：連虧 k 後條件期望 p(真≤虛無) 各策略全 >0.10
- [x] 損益序列（非僅勝負）自相關 → ≈0

### 反例 / 守門
- [x] Pooled 唯一 p<0.05（k=2）排查：非單調 + 仍正值 + 組合假象已排除（Reversal 占比無偏移）→ 多重比較雜訊
- [x] 視覺化：results/h106_distribution.png（連虧 k × 條件期望 疊 IID 5–95% 信賴帶）

---
### GATE
**問題：分佈結果是否支持進入回測？**

- k≥3 的樣本數是否足夠（最低門檻：每策略 k=3 連虧事件 ≥ 20）？
- 條件期望是否單調下降，且**顯著落在 IID 洗牌分佈之外**（硬門檻）？
- win/loss 自相關是否顯著為正？多策略是否一致？
- 是否有 data snooping（k 門檻、策略選擇）？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest（GATE 通過才做）

- [ ] 定義「連虧 k 日 → 暫停/降碼」規則（門檻 k、暫停長度 / 降碼比例）
- [ ] 套回 EstHL/Reversal：加規則前後對比（期望、PF、**連敗長度、MaxDD**——依 `[[feedback_filter_eval_includes_streaks]]`）
- [ ] in-sample / out-of-sample / walk-forward
- [ ] 參數敏感度（k、暫停/降碼參數）
- [ ] 若期望不變但 DD 改善 → 導向 sizing 規則而非停手（依 `[[feedback_regime_modulate_not_block]]`）
