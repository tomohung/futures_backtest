# Archive: H107 — 尾盤趨勢延續（Final-Hour Continuation）

## Status
Rejected（尾盤無續行 edge，方向與 Angell 相反；Phase 1 即否）

## Summary
源自 backlog GA-09（Angell *Trading the Final Hour*「don't fade the final hour」）。零策略測台指日盤
尾盤的方向動能續行與突破續行，並用早盤 vs 尾盤對比 + ATR 正規化。結果：尾盤續行不高於早盤、突破
續行最強在開盤而尾盤反而 fade、趨勢日條件化也無續行 → Angell 尾盤論在台指不成立且方向相反，
GATE 直接 Archive。

## Key Evidence（N=1305 交易日，2021–2026）
- 方向動能續行：corr(進場前, t→收) 全日 <0.05（尾盤 ~0.04 經濟為零），同向率全程 ~50%。
- 突破續行（破前30分區間 → 收盤延伸率 − baseline）：早盤 09:15 **+5.8%**、09:45 +3.4%；午盤 11:45 −6.7%、尾盤 12:45 **−8.3% fade**、13:00/13:15 ≈0。
- 趨勢日條件化：強趨勢進尾盤(12:45, prevabs 0.92 ATR)續行率仍 53%、順勢剩餘 +0.02 ATR。

## Why Rejected
尾盤續行未顯著高於早盤（反而低/相反），突破續行 edge 在**開盤**（與 H030 ORB / H027 一致）。正中
proposal 無效條件「尾盤續行不顯著高於早盤」。非統計幻覺，而是真實結構位置相反——台指強開盤 auction
+ 5 小時短盤，無美股尾盤機構再平衡。

## Derived Hypotheses
- **台指續行結構在開盤非尾盤（已確立）**：突破續行 09:15 最強、午後遞減至尾盤 fade。強化 H030/H027
  開盤 edge 定位，**不需另立尾盤策略**。
- **午盤(10:15–12:45)fade 區**：突破淨續行 −5~−8% → 午盤偏假突破/回補，可連 GA-11（掃停損反轉）午盤版，
  但須 IID/baseline guard（[[feedback_excursion_needs_forward_tautology_guard]]）。
- **meta（H104–H107）**：Angell 四個量化觀點（缺口、早期套牢、連虧、尾盤）在台指全數 rejected——
  心法類是統計幻覺、結構類(尾盤)是位置相反。Angell 美股 floor 結論不可照搬台指電子盤。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md（GATE：Archive Rejected）
- 腳本：explore.py；圖 results/h107_distribution.png
