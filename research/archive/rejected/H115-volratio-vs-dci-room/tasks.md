# Tasks: vol_ratio vs DCI 當「還有沒有空間」調節器

## Phase 1: Distribution Research

- [x] **事件 + 三調節器抽取**：碰 L3 日 t_k 取 vol_ratio / dci_long(=ext_long W10@t_k+09:15) / 時點。
- [x] **結果標記**：cont = t_k 後續攻 L4（forward）。
- [x] **核心對撞**：vol_ratio IS −26%→OOS +41%（符號翻轉,否決）;dci_long OOS 非單調;**時點 IS+38/OOS+64 雙單調完勝**。
- [x] **增量檢定**：vol_ratio 控時點後增量也翻轉（無增量）。
- [x] **vol_ratio↔關卡對齊**：中位≈1.02 對齊 L4,但 cont=1/0 的 vol_ratio 幾乎一樣 → 零分辨力。
- [x] **regime 診斷**：OOS≡高波(44/44,ema20 260→658);vol_ratio 翻轉是 regime 交互。
- [x] **衍生 H115-d1**：定向量（累積淨多空力道,使用者指標）修好符號,二級修正可用（早碰層 IS+9/OOS+26）。

---
### GATE
**問題：vol_ratio 是否 OOS 上贏 dci_long、且非純時點代理？**

- 樣本：L3→L4 事件 IS ≥30 / OOS ≥15（沿用 H114：IS 105 / OOS 44 足）；L4→L5 探索性不判定。
- 方向：vol_ratio 分帶 **OOS gap > dci_long OOS gap** 且方向 IS/OOS 一致（單調）。
- 增量：控制時點後 vol_ratio 仍存活（否則結論為「換成時點」而非量）。
- data snooping：分帶切點先在 IS 定、OOS 只驗;不依 OOS 表現挑切點。

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest（收割積極度規則,對撞現行 DCI 軸）

- [ ] 把 vol_ratio 分帶接成「目標積極度」規則（放量→Dow-trail 過 L3 多抱、縮量→L3 靜態鎖）。
- [ ] 事件型 bracket（沿用 H114 框架）或接 S001 ladder 出場。
- [ ] 基準對撞：(i) 現行 DCI 分帶軸、(ii) 時點分帶（H114 A）、(iii) always-hold。
- [ ] IS/OOS 損益%、Sharpe、**連敗長度 + max drawdown**（[[feedback_filter_eval_includes_streaks]]）。
- [ ] 切點/分帶敏感度（IS 定、OOS 驗）。
- [ ] 若贏：產出修改 S001 journal_checklist 的 spec diff（DCI 軸 → vol_ratio 軸）。
</content>
