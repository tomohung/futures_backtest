# Tasks: EstHL 殘留靜日濾網（Residual Quiet-Day Filter over NVF）

## Phase 1: Distribution Research（盤前預測子 vs 殘留靜日，增量於 NVF）

### 資料準備（只用盤前可知）
- [x] EstHL trade log（殘留母體 N=170）；對齊當日 |day move| 作標記；VIX 自 vixtwn 用前一日值
- [x] 盤前預測子 panel：night_norm、前1/3日日盤range、OR寬度、|gap|、前日VIX（皆 08:58 前可知）

### 殘留靜日的可分離性（核心）
- [x] Q1 預測子對當日 |move| 預測力 → VIX 0.253(增量0.236)、OR 0.198、前日range 0.183、night 僅 0.121
- [x] Q2 各預測子 × EstHL PnL 分桶 → 最佳 gap spear 0.187，連最弱桶仍 +0.04%（無淨負桶）
- [x] Q3 增量檢定：去 night_norm 後 gap 增量 0.135（其餘 <0.08）
- [x] 誤殺檢查：濾低 gap 底25%+ 即砍淨正交易 + 6~9 個 Q3 贏家；雙低交集 N=41 仍 +0.038%

### 守門
- [x] baseline=既有 NVF；新濾網無增量正效果（只有底10% gap 小賺 +0.6%/5年=雜訊）
- [x] 視覺化：results/h109_distribution.png（預測子×EstHL期望 + night_norm vs 當日|move| 散度）

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 是否有盤前預測子在 night_norm 之上**增量**分離殘留靜日虧損？
- 濾掉的日子是否避開 Q3 贏家（淨期望升）？逐年是否一致？
- 樣本：EstHL N=170，分桶後每桶是否 ≥20？
- data snooping（預測子數、分桶、門檻）疑慮？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive（殘留靜日不可約）　[ ] 修改假設

---

## Phase 2: Backtest（GATE 通過才做）

- [ ] 把勝出預測子濾網加進 EstHL backtest（與既有 NVF 並存）
- [ ] 加濾網前後對比：期望、PF、Gini、**連敗/DD**（[[feedback_filter_eval_includes_streaks]]）
- [ ] in-sample / out-of-sample / walk-forward；參數敏感度（門檻）
- [ ] regime 思維：靜日「降強度（小倉）」vs「全停」對比（[[feedback_regime_modulate_not_block]]）
