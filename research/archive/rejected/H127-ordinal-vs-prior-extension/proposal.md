# Proposal: 序數 vs 前置延伸 — L2 拉回續攻 edge 的真正 driver

## ID
H127

## Derived From
H126-second-l2-pullback 的 distribution 階段（Derived Hypotheses）。

## Trading Intuition
H126 發現「同向第 2 次（含以上）L2 拉回續攻」在 09:30–11:30 的深目標（L4/L5）reach 約為同時段第一次的
2 倍，且同時段三方對照（C vs B）指向「序數本身」帶 edge。但**序數與「進場時當日已實現的同向延伸」近乎
共線**：第 2 次 setup 之所以是第 2 次，正因為當日已先有一段同向 leg（通常已達 ~L3）走完並回檔——
亦即「第幾次」可能只是「趨勢已成熟 / 已實現一段同向延伸」的代理。

連 H126 最乾淨的 C-vs-B 都分不開：B（多次日的第一次）按定義**沒有前置同向延伸**，C（第二次）**有**前置
延伸——所以 C≫B 既能解讀成「序數效應」、也能解讀成「前置延伸效應」。H127 要把這兩者拆開。

## Hypothesis
L2 拉回續攻的深目標（L4/L5）續航 edge，真正 driver 是「**進場當下、當日已實現的同向延伸幅度
（trend maturity，causal 量測）**」，而非「**第幾次（序數）**」本身。
具體可測陳述：以「進場前同向已走幅度 `prior_run_L`（× EMA20）」為連續預測子，
**控制 `prior_run_L`（與進場時間）後，序數（1st vs 2nd+）對 forward L4/L5 reach 的增量預測力消失或大幅縮小**；
反之 `prior_run_L` 在控制序數後仍顯著。

## Expected Distribution
- `prior_run_L` 與 forward L4/L5 reach 單調正相關（前置延伸越大、續航越遠）。
- 在相同 `prior_run_L` 分層內，1st 與 2nd+ 的 reach 差異**收斂到不顯著**（序數被前置延伸吸收）。
- 反向分層（相同序數內，`prior_run_L` 仍能分出 reach 高低）→ 前置延伸是主 driver。
- 若成立：Phase 2 進場條件應改用連續的「前置延伸門檻」（涵蓋部分**第一次但已有前置延伸**的日子，
  例如開高走高無乾淨第一次拉回、首個 reclaim 已在延伸後），而非僅用「第 2 次」這個離散旗標。

## Invalidation Condition
任一成立即視為 H127 不成立（→ 回到 H126：序數本身才是乾淨訊號，對 Phase 2 反而是好消息）：
1. 控制 `prior_run_L`（同分層）後，2nd+ 相對 1st **仍有顯著增量** reach（序數帶獨立於前置延伸的資訊）。
2. `prior_run_L` 在控制序數後**無單調預測力**（前置延伸不是 driver）。
3. 兩者皆顯著且互不涵蓋 → 不可分（confound 無法以此資料拆開），記為 Inconclusive，Phase 2 兩條件併用。

## Notes
- **純描述 / 無交易**：本假設只做 excursion 層級的 driver 歸因，不定義進出場（沿用 H126 的 detect_day 進場）。
- **`prior_run_L` 定義（causal）**：對每筆進場 bar i、交易方向 dir，
  `prior_run_L = (進場前同向最佳行程) / EMA20`。多單 = `(max high[session_start..i-1] − session_open) / ema20`；
  空單 = `(session_open − min low[session_start..i-1]) / ema20`。open-anchored（與 chart-ui 延伸力一致）。
  另備一版「以關卡計：進場前是否已有任一同向 phase 達 ≥L2 / ≥L3」做穩健性對照。
- **方法**：(a) 單變量：reach vs `prior_run_L` 分桶；(b) 雙向分層（序數 × prior_run 分桶）看哪個survive；
  (c) 簡單 logistic（reach_L4 ~ ordinal + prior_run_L + entry_min）比較係數/邊際，三方互證。
- **記憶連結**：`feedback_excursion_needs_forward_tautology_guard`（H126 已示範時間 confound 會翻轉結論）、
  `feedback_isolate_phenomenon_and_test_each_cell`（每個分層 cell 都實測，不推論帶過）。
- 重用 H126 `entries.csv` 的進場集合，新增 `prior_run_L` 欄位即可（同一 detect_day 真相源）。
