# Distribution Research Results: 序數 vs 前置延伸 — L2 拉回續攻 edge 的真正 driver

## Date
2026-06-24

## Conditions Tested
重用 H126 detect_day（causal）進場集合，對每筆新增 causal 前置延伸特徵，拆解「序數 vs 前置延伸」：
- `prior_swing_L` = 進場前(< i)同向最大「已實現擺動」/ EMA20（anchor-free；long=max(high−先前低)、short=max(先前高−low)）
- `prior_run_open_L` = open-anchored 同向已走幅度 / EMA20（備援）
- 方法：單變量分桶 + 雙向分層（序數 × prior_swing）+ 決定性 cell + 輕量 logistic horse race
- 分層限 edge 窗 **entry∈[09:30,11:30]**（H126 結論），N=1086

腳本：`explore.py`　明細：`results/entries_prior.csv`　圖：`results/ordinal_vs_prior.png`

## Sample
- 總進場 N=2052；edge 窗 09:30–11:30 N=1086（1st≈966 / 2nd+≈120）
- **結構事實**：`prior_swing_L` 恆 ≥ ~L2（<L2 桶 N=0）——detect_day 需先有 ≥L2 擺動確立趨勢才會有任何進場。

## Key Findings

### 1. 控制前置延伸後，序數效應「完全 survive」（核心）
雙向分層（edge 窗，L3/L4/L5 reach %）：

| prior_swing | 1st | 2nd+ |
|---|---|---|
| < L3 | 58.6 / 24.6 / 10.8（N=917）| **64.9 / 40.4 / 19.3**（N=57）|
| ≥ L3 | 57.1 / 20.4 / 12.2（N=49）| **65.1 / 39.7 / 27.0**（N=63）|

→ **不論前置延伸 <L3 或 ≥L3，2nd+ 的 L4 都 ~40%、約 1.6–2× 於同層 1st。序數效應不被前置延伸吸收。**

### 2. 反向控制：1st 不管延伸多深，都拿不到 edge（直接反證 H127）
1st 內按 prior_swing 分桶（L4/L5 reach %）：
- L2–L3（N=917）：24.6 / 10.8
- L3–1.0（N=25）：16.0 / 4.0
- ≥1.0（N=24）：25.0 / 20.8

→ **1st 的 L4 始終卡 ~25%，前置延伸增大並未帶來 L4 edge。** 若「前置延伸」是 driver，1st-已延伸應追上 2nd+，但沒有。

### 3. 「極端延伸桶」的高 reach 是 2nd+ 撐的，非獨立 driver
單變量看 `prior_swing≥1.0`（N=53）reach 跳到 68/45/34%，似乎前置延伸有效——但拆序數：
- `prior≥1.0 & 1st`（N=24）：58 / **25** / 21%
- `prior≥1.0 & 2nd+`（N=29）：76 / **62** / 45%

→ 高 reach **全由該桶 55% 的 2nd+ 成員貢獻**；同桶 1st 仍只有 25% L4。前置延伸非獨立 driver。
（附帶：2nd+ 中 prior≥1.0 是最強子集 L4 62%，屬「序數內」的加成、N=29 偏薄，留作 Phase 2 sizing 線索。）

### 4. 2nd+ 內，前置延伸幾乎不影響
`2nd+ & prior<L3`（40.4% L4）≈ `2nd+ & prior≥L3`（39.7% L4）；僅最深 L5 略增（19→27%）。
→ 第二次「這件事」本身帶資訊，第一段 leg 走多深幾乎無關。

### 5. logistic horse race（連續特徵的唯一保留意見）
標準化係數：reach_L4 → is_2nd +0.255 / prior_swing +0.238 / entry_min −0.466；
reach_L5 → is_2nd +0.332 / prior_swing +0.383 / entry_min −0.815。
- 連續 prior_swing 係數與 is_2nd 同量級——但這是極端桶(≥1.0，多為 2nd+)被線性項吸收所致；
  分層[1–4]已證 prior 在固定序數內幾無主效果。**entry_min 係數最大（負）**：時間仍是最強的負向因子
  （與 H126 ≥11:30 死區一致），edge 窗內越晚越差。

## Vs. Expected
**與假設預期相反 → H127 不成立（= proposal 的 Invalidation #1 命中）**：
- 預期「控制 prior 後序數消失」→ 實際**序數完全 survive**；
- 預期「1st-已延伸追上 2nd+」→ 實際**1st 不論延伸多深都拿不到 L4 edge**。
- 結論反而**強化 H126**：2nd+ 是乾淨、因果的續攻訊號，不是「前置延伸/趨勢成熟」的代理，也不是時間或趨勢日 selection 的假象。

## Gate Decision
[ ] 進入 Phase 2（H127 自身無 Phase 2 — 本假設為 driver 歸因）
[x] Archive（**Rejected**：前置延伸非 driver；序數本身才是）
[ ] 修改假設

**對下一步的意涵**：H126 Phase 2 進場條件 **直接用離散「2nd+ 同向 L2 拉回」即可**，
無需加前置延伸門檻（已證無增量、且會誤收 1st-已延伸的無效樣本）。保留 entry∈[09:30,11:30] 時間閘
（最強因子）。可選 sizing 線索：2nd+ 且 prior_swing≥1.0 的深 reach 子集（N 薄，Phase 2 再驗）。

## Derived Hypotheses
- **H128（沿用 H126 Notes）**：2nd+ 的 MAE 偏大 → 測「更寬停損 + L4/L5 目標」是否比沿用 l2_pullback 緊停損更適配續攻。
- **H129（候選）**：序數「資訊」是否隨次數遞增（3rd > 2nd）？H126 看到 3 次 N=32 reach 略高於 2 次；
  以「同向 reclaim 次數」為連續 dose 測 dose-response（N 薄，需合併早桶謹慎）。
- entry_min 為最強負向因子：可細究「2nd+ 訊號的有效時間半衰期」（10:00 vs 11:00 進場的 reach 衰減曲線）。
