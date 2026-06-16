# Archive: L1 拉回續攻 — 確立門檻從 L2 放寬到 L1

## Status
Rejected（2026-06-15，Phase 1 GATE 不通過）

## Summary
H120/S005 退役後，causal 診斷出其結構性死因是「進場已在錨點上方 ~L2、目標 L3 太近、停損偏寬
→ 目標比停損近 → 小賺大賠負偏態」。H121 試圖把確立/進場門檻從 L2 降到 L1，讓進場更早、
RR 幾何改善（L1→L3 的 RR≈1.12 vs L2→L3 的 0.58）。實測：幾何改善是真的（負偏態收斂），
但 L1 的趨勢確立度太弱、續攻機率大跌，把幾何紅利吃光，net edge 不升反降。

## Key Evidence
- **Fork 忠實**：explore.py 以 est=L2 跑出與 H120 原始 detect_causal 完全一致（keys 全同、diff 0.000000），證明只動了確立門檻、無 `em` 前視復發。
- **L1 主場景（causal，部署濾網）**：N=2448、勝率 51.6%、EV 1.1pt、Sharpe **0.006**、avgR −0.01、maxDD −18.2%、skew **+0.04**。
- **vs H120 baseline（L2）**：勝率 62.2%、Sharpe **0.041**、avgR 0.02、skew **−0.40**。
- **幾何 vs 折損**：負偏態 −0.40→+0.04（幾何改善為真）；但無條件續攻率 P(摸 L3|確立) 57.7%→**37.2%**（折損），淨吃掉報酬。
- **門檻掃描 L1→L2 單調**：est_c 越低，Sharpe/勝率/avgR 越差，L1 是最差點，無中間最佳。

## Why Rejected
觸發 proposal 預先登記的 Invalidation Condition：
1. causal L1 版 Sharpe 0.006 **≤ 0.10**（與 baseline 0.04 無實質差異、且更低）。
2. avgR 未上升（0.02→−0.01）—— 幾何改善被續攻折損吃光（唯 skew 收斂，不足以救）。
3. 門檻掃描單調指向「越接近 L2 越好」，無可救的中間參數。
核心：移動確立門檻只改了「進場深度」這一個旋鈕，RR 與續攻機率是同一枚硬幣兩面，
往任一邊移都是零和。要翻案得改**目標/停損結構**，非只移門檻。

## Derived Hypotheses
- （潛在，未開）若要利用「站回訊號在淺確立 L1 時資訊量更高（條件增量 +14.4pp vs L2 +4.5pp）」
  這個附帶觀察，需搭配**不同的目標/停損結構**（如更近目標或 R 倍數出場）重新設計，而非沿用 L3 靜態目標。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Engine：explore.py（fork 自 H120 validate_causal.py，參數化確立門檻）
- 來源：H120-l2-pullback-continuation（archive/rejected）、S005（strategies/retired）
