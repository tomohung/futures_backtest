# Archive: 盤前多空計分表有效性審計 + 早盤方向 edge 重探

## Status
Rejected（審計 + 方法論為主要產出；無新可交易 edge）

## Summary
審計 `key_prices.py` 現行「方向加分（多空計分）」表（1H MACD / 30m 20MA / 週幾勝率 / 夜盤位置四訊號 + 合計投票），
並重探早盤方向替代訊號。全歷史 N=1263（2021–2026），統一 harness：方向命中率 vs base rate（含 same-mix 虛無）
+ 機械交易 P&L（三窗口、成本 3 點/邊）、逐年 + VIX regime 拆。結論：**盤前資訊對早盤方向無跨 regime edge**；
合計投票比最佳單一成分更差（合併純稀釋）；唯一活的早盤方向 edge 在開盤後（OR方向+量比+跳週四五），但係複刻既有
confirmed H018（早已餵進 ORBLong），非新 edge。

## Key Evidence
- **四訊號審計**：1H MACD net −7.7~−11.8（0/6 全窗口）；夜盤位置 lift −0.045（反預測，0-1/6）；週幾滾動勝率雜訊（全靠 2026）；30m 20MA 唯一略正 net +4.8/PF1.11/4/6 但 lift vs 多數≈0（drift-capture）。
- **合計投票**：三窗口全負（net −3.5~−9.6），**從不勝過最佳單一成分** → H133-a 核心新角度證伪。
- **盤前動能全滅**：MACD 位準/動能/交叉、RSI/ROC/EMA20/隔夜動能皆無 edge。「hist≥0且遞增」確認版 P(漲|多)=0.49<base（動能衝進開盤→早盤 mean-revert，呼應 H056）。
- **黃金交叉幻覺**：原「當根」N=45 的 0.652 係小樣本雜訊；改「近 K 根內交叉」（N=194~832）後 net −18.8/−3.7/−14.2，全負。
- **反向 / 逆勢皆不成立**：反轉「hist≥0且遞增」net 打平或全靠 2026；RSI 超買做空連毛利都負（RSI>80 net −53）→ 日線 RSI 極端**續勢不回檔**。
- **開盤後 OR**：方向+量比≥1.0+跳週四五，OR30 交易 09:15-11:30 net +11.3/PF1.24/4/6，hit 0.554 ≈ H018 的 55.4%（複刻）。

## Why Rejected
Proposal 的無效條件成立：合計投票 lift≤0、P&L 不過成本、逐年 <4/6、不勝過最佳單一成分（H133-a）；
所有盤前替代候選（動能/逆勢/反向/超買超賣）P&L edge 逐年 <4/6（H133-b）。唯一過 4/6 的開盤後 OR 訊號
係複刻既有 confirmed H018/ORBLong，非新可交易 edge。故無新策略產出，判 Rejected。
審計結論（砍列建議）與方法論教訓為主要價值。

## Methodological Takeaways（主要產出，供未來研究）
1. **早盤 mean-reversion 只在隔夜/跳空那條**（夜盤位置、隔夜動能反預測；H104），**非多日 RSI**（多日 RSI 極端反而續勢）。
2. **「動能越確認 → 早盤越回檔」** 跨 MACD/RSI/ROC/EMA20 robust；盤前判方向 H056/H018 結論全面複驗。
3. **反轉一個 net-negative 訊號 ≠ edge**：虧損常大半是成本（反向要再付一次），剩餘往往是單年（2026）撐盤 → 經典 overfit 陷阱。
4. **高 RSI「續強」是 2024-26 多頭 regime 假象**，逐年翻號 → 再次驗證 pooled 須過逐年關（elec-fin / oos_equals_highvol_regime）。
5. **提高早盤勝率的真實槓桿在開盤後**（等 09:15、OR量比≥1、跳週四五、順開盤方向）—— 已由現行 ORBLong 捕獲。

## Code Impact
- `key_prices.py` 計分表**未修改**（使用者選擇暫不動 code）。審計建議：MACD/夜盤位置/週幾三列可刪、投票結論可移除、20MA 降觀察。日後如要整理可依 distribution.md「Gate Decision」表。

## Derived Hypotheses
- 無新立號假設（早盤盤前方向已判耗盡；開盤後 edge 已由 ORBLong/H018 覆蓋）。
- 觀察：夜盤位置/隔夜動能的反預測（早盤 fade）與 H103（跳空下方遠做多，Inconclusive）同族，H104 已證結構不可交易，優先度低。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md（Phase 1 審計 + MACD/動能/交叉/反向逆勢子研究 + Phase 2 開盤後）
- 圖：results/h133_yearly_heatmap.png
- 逐日/結果：results/h133_daily.csv、h133_results.json
- 腳本：explore.py（harness）、explore_macd.py、explore_macd_cross.py、explore_momentum.py、explore_fade.py、explore_postopen.py
