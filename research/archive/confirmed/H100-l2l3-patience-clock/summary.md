# Archive: L2→L3 放棄時鐘（強 DCI 放寬閘的上限）

## Status
Confirmed（分佈層級，OOS 一致；無 Phase 2 P&L 回測——因屬「閘的時間校準」而非策略 edge，
結論直接回補 H095 規則）

## Summary
衍生自 H099/H095。回答「H095『強→放寬 10:45 閘』沒有上限時間,那上限是幾點」。
Phase 1（L2-reacher 母體 N=183）以**條件存活**衡量「碰 L2 守初始SL、等到 T 仍未 L3 →
之後仍到 L3 的機率」。結論：**即使強 DCI,放寬閘也有上限 T*≈11:00–11:30,不該延到 12:20+。**

## Key Evidence
- 母體 N=183（強 119 / 中 49 / 弱 15）；**強帶各 T 存活 N 全程 ≥19**（過了 H099 的稀疏失敗點）。
- 強帶 P(到L3 | 存活等待@T)：10:00 **62%** → 10:45 **36%(斷崖)** → 11:00 30% → 11:30 **25%**
  → 12:00 22% → 12:20 **24%** → 12:45 21%（無條件 P(到L3|碰L2)=75%）。
- 帶間：強 36–62% ≫ 中 11–16% ≫ 弱 ~0% → 「強→放寬閘」有實據,但強帶亦有界。
- T*（事前規則）：跌破⅓ 於 11:00、跌破無條件半值(37.5%) 於 10:45 → **T*≈11:00–11:30**。
- OOS：train≤2024 / test≥2025 同向衰減；近兩年強帶稍韌（12:20=33%）→ T* 取區間。

## Why Confirmed
- 三項 GATE 皆過：母體足、強帶存活全程 ≥20 附近、單調衰減 + 強>中>弱 + OOS 同向、T 網格事前登記。
- 屬「閘時間校準」（descriptive distributional claim），非需 P&L 回測的策略 edge,
  且已用 train/test 驗證 → 直接回補 H095，未跑 Phase 2。

## Applied To（已回補）
- `H095/journal_checklist.md`：10:45 閘「強」格加放寬閘上限 ~11:00–11:30 + 條件機率表。
- `H095/exit_scenarios.md` §3 + v5.2 版本註記。

## Derived Hypotheses
- **H100a｜10:45 斷崖**：全帶在 10:45 掉最多 → 佐證 10:45 主閘選得對（已併入結論,不另開）。
- **空方對稱版**：殺盤更集中早盤,空方放棄時鐘可能早於 11:00；待 H095 空方 Phase 2。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- 圖：results/patience_clock.png
- 探索腳本：explore.py
