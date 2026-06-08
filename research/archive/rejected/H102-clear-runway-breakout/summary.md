# Archive: 淨空開盤裸突破（Clear-Runway Breakout）

## Status
Rejected（原「裸突破」框架證偽；但 productive — 衍生出 H103 主線）

> **後續修正（H103 Phase 1, 2026-06-08）**：本文多處把衍生訊號命名為「mean-reversion
> 回補成本／目標=成本價」——**此 label 有誤**。H103 證實主訊號組的成本離開盤中位
> 1.30×ema20 之遠，進場做多真正「漲回成本」的僅 ~10%。**測量數字（+17~26pp 方向 edge，
> 以固定 reach L3 量）全部正確且站得住**，但機制應為「**方向性向上漂移 ~L2/L3 幅度**」而非
> 「彈回成本」。H103 改用固定目標後仍為正期望（E +0.10~0.15×ema20、控制組為負），訊號成立。
> 下文「回補成本」字樣請以此修正理解。

## Summary
測試「當開盤離昨/前日成本(VWAP)夠遠、某方向無近端 S/R 擋路時，單純做 OR 裸突破
（拿掉 EstHL 濾網）是否成立」。結論：**原方向假設不成立**——以成本為基準的「淨空」
這條軸主要決定當日**振幅能量**而非**方向**，下方淨空做空、夾中間、gap-up 做空皆無
方向 edge，且 OR 裸突破反咬率高（56–68%）。但探索收斂出唯一穩健訊號（mean-reversion
做多），已轉立 H103。

## Key Evidence（N=1312，2021-01-05 ~ 2026-06-05）
- **gap 軸 = 能量非方向**：跳空上方(N=599) up/dn L3 = 44%/43%（雙弱、低能量）；
  跳空下方(N=400) = 63%/59%（雙強、高能量），方向偏性微弱。
- **finite clearance 方向 edge 只在上方**：上 >L5 同向−反向 +14pp；下方 finite 全 −1~−3pp（無 edge）。
- **OR 裸突破反咬**：同向淨空 56–59% vs 非淨空 61–68%（淨空只降 5–9pp，絕對仍高）。
- **完整 3×2 grid 揪出 confound**：原「上 finite >L5 +14pp」其實主要來自**跳空下方做多**
  （上clear L4–L5 N=47 +26pp、>L5 N=64 +17pp），而非「夾中間」。

## Why Rejected
1. 假設核心「沒 S/R 就往那邊突破」——以成本定義的淨空不帶可靠**方向**資訊（只帶能量）。
2. 對稱性不成立：下方淨空做空、gap-up 做空無 edge（市場 gap 行為本身不對稱）。
3. 進場機制（OR 裸突破）反咬率高，reach 達標高 ≠ 進場點獲利。
→ 原框架不可交易；但唯一存活的訊號是**反向框架（mean-reversion 做多）**，故另立 H103 而非續測。

## Derived Hypotheses
- **H103-gapdown-cost-revert**（active，主線）：open 跌破兩成本之下 + up_clear_norm≥L4
  → 折價回補成本做多（mean-reversion，非突破，只做多）。N≈111，方向 +17~26pp。
- **H10X-gap-energy**（觀察）：gap 大小 ≈ 當日振幅能量前瞻估計（跳空上=窄幅、跳空下=寬幅），
  可當其他策略「今日波動」濾網，與 NVF 並比。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md（含完整 3×2 grid 補充分析）
- Explore script：explore.py
- Data：results/h102_daily.csv
