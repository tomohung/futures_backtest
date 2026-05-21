# Archive: 早盤弱勢 → 大長黑

## Status
**Rejected**（作為可交易策略；Phase-1 機率觀察本身成立，但無可交易 edge）

## Summary
H093 的反向對稱研究：早盤一路殺、10:30 守在早盤區間低位（pos≤0.25）→ 當日大長黑。
Phase 1 機率宣稱成立且跨年穩健（大長黑率 20.6%，lift 2.86x），但 Phase 2 做空
（10:30 進、13:45 出）扣成本後打平到負（全期 PF 0.97、勝率 < 50%、逐年不一致），
故作為可交易策略 rejected。

## Key Evidence
- 樣本：TX 日盤 N=1289（2020-12 ~ 2026-05），adj_close。
- Phase 1：base rate 大長黑 7.22%；觸發 pos≤0.25（N=310）大長黑率 20.6%（lift 2.86x），尾端低（收紅 16.8%、反彈 3.2%），逐年皆有機率 edge。
- Phase 2（net 3 點，做空）：pos≤0.25 全期 gross +2.9%（PF 1.05）→ net −2.0%（PF 0.97），勝率 45.8%。
- IS 普遍負（PF 0.88–0.99）、OOS 微正（PF 1.13–1.32）→ IS/OOS 背離。
- 逐年不一致：2022 −2.0%(PF 0.87)、2024 −5.1%(PF 0.64)、靠 2023/2025 撐。
- 對照「無腦放空 10:30→13:45」net −1.1%（PF 1.00）→ 過濾在可交易段無加值。

## Why Rejected
**核心癥結（本研究最有價值的結論）**：早盤一路殺才會 10:30 守低位 → 殺盤大多在 **10:30 之前**已完成。做空進場在 10:30，可吃的 close_1030→close_1345 平均僅約 1.8 點 gross，被 3 點成本吃光；且收低位後 10:30 常技術性反彈（勝率 < 50%）。

→ **與 H093 多單側完全同源**：兩個 confirmed 的「機率現象」，可交易 edge 都活在 pre-10:30，10:30 進場吃不到。「10:30 進、13:45 出」這個進場框架本身無法捕捉 Phase 1 看到的 edge（雙向皆然）。

備註：嚴格按 proposal 的假設陳述（「大長黑機率顯著高於 base」），Phase 1 並未被否證；此處 Rejected 指的是「可交易偏空策略」層次。分類為 rejected（而非如 H093 的 confirmed）是因為它只是複驗 H093 已知癥結、無新增可交易價值。

## Derived Hypotheses
- **early 進場框架**：H093/H094 的可交易 edge 都在 pre-10:30。值得研究「開盤後 N 分鐘內即時判斷方向、early 進場」的當沖框架（挑戰：即時判斷而不 lookahead）。
- **隔日效應**：早盤守低位/守高位是否預測「隔日」開盤或日報酬？跨日 move 不受 intraday 進場時機限制，可繞開本癥結。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md
- 腳本：explore.py / backtest.py
