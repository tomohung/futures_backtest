# Archive: H104 — 雙基準跳空（Dual-Baseline Gap）

## Status
Rejected（可交易假設無 edge；方法論結論為主要產出）

## Summary
源自 backlog DH-09（GA-01/02 台指化前置）。台指日盤開盤前隔一整段夜盤，故「開盤跳空」有兩個基準：
**A=對夜盤 05:00 收**、**B=對昨日盤收**。Phase 1 證實兩基準顯著不同；Phase 2 把夜盤錨的 fade /
momentum 做成可交易規則，OOS 全數崩潰 → Rejected。真正產出是「TX gap 必須指明基準」的方法論結論，
與一條已落地觀察的薄濾網。

## Key Evidence
**Phase 1（純現象，N=1239 no-rollover, 2021–2026）**
- 兩基準有別：corr(A,B)=0.557、**37% 方向相反**、**70% 落入不同強度桶**、夜盤段位移 median 83pts。
- 05:00 整點收 vs 夜盤實際末筆：**等價**（corr 1.0000）→ 用 05:00。
- 缺口回補（% of 開盤價，跨年穩定 62–78%）：小缺口(<0.15%)回補 84–97%、大缺口(>0.5%)僅 36–45%；
  結構在**大小不在方向**（上/下跳回補 72% vs 74%）。
- 方向性：五分位皆不顯著；極端尾端僅基準 A gap-down 偏續跌（P 56%、−0.11%），非 GA-01 對稱反轉。

**Phase 2（08:45 進場、路徑出場、成本 3 點、IS 21–23 / OOS 24–26）**
- T1 H103 複刻（baseline）：PF 1.66 / IS 2.55 / OOS 1.15，重現 H103 ✅。
- T2 夜盤 fade：全面負 PF 0.54–0.60、MDD 20–49%。
- T3 夜盤 momentum（修正版假設·極端 gap-down 做空）：IS 1.87 → **OOS 0.98** 崩潰。
- T4 夜盤跳空當 H103 濾網：「open>夜盤收」子集 OOS PF 3.62 vs 0.81，但 N=28（OOS 11）過薄。
- DH-16 三角度釘死：1R 停損 PF 0.55、抱收盤 0.96、時間出場掃描上限 0.97（毛利 1.14、成本翻負）。

## Why Rejected
夜盤相對跳空**不是可交易的獨立 edge**：fade（觸價≠成交、1R 反咬）與 momentum（IS 漂亮 OOS 崩）
雙雙不過成本線，正中 proposal 無效條件「OOS 期望值崩潰」。Phase 1 的回補/續跌現象為真，但根因
「小缺口目標扛不住交易成本、大缺口不回補」使任何出場都救不了。

## Derived Hypotheses
- **夜盤回升濾網（T4）→ 已走 option C，未立號**：「open > 夜盤 05:00 收」精煉 H103 多單（OOS PF 3.62,
  N=28 薄）。改掛 `src/analysis/h103_alert.py` 觀察欄位（夜盤 05:00 收參考線 + T4 解讀），前推累積後再定。
- **方法論結論（已確立）**：TX gap 研究**必須指明基準**——對昨收基準被夜盤位移污染（median 83pts），
  **疑為 H033（gap-day-study, rejected）失敗主因**。任何重做 gap 研究者先讀此結論，勿再用裸昨收基準。
- **DH-16 fade（Rejected）**：中等夜盤缺口 fade，回補勝率 87% 為真但結構性不可交易，不再追。

## Links
- Proposal：proposal.md（含 Revised Hypothesis）
- Distribution：results/distribution.md（GATE：修改假設→Phase 2；含回補率 %、跨年、與 H103 關係）
- Backtest：results/backtest.md（Verdict：Rejected）
- 腳本：explore.py、backtest.py；daily 表 results/h104_daily.csv、圖 results/h104_distribution.png
- 落地觀察：src/analysis/h103_alert.py（T4 觀察欄位）
