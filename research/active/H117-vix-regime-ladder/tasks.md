# Tasks: VIX regime 當 ladder 出場/sizing 期望調節器

## Phase 1: Distribution Research（部分已完成）

- [x] VIX regime 因果偵測器（昨日 VIX vs MA20 升壓/降壓;20日變化方向;水位帶）→ `src/analysis/vix_regime.py`。
- [x] VIX lag 1 疊 ladder 達成頻率（N=1296）：升壓深 reach ~2×（多L4 30/L5 16 vs 降壓 19/7）。
- [x] ★ 因果檢定：方向偏移（多−空L4）lag 後消失（+0~3%）→ 確認 magnitude 真、direction 假象。
- [x] 偵測器比較：VIX>MA20 / 20日變化 / 10日變化 / EMA交叉 / 純水位 → 前兩者最佳。
- [ ] 補：達成頻率 by regime **再細分到續攻轉換** P(L4|L3)、P(L5|L4) 是否也 regime-變（出場決策更直接）。
- [ ] 補：升壓段深 reach 的**回吐/路徑品質**（達 L4 後是否更多 whipsaw,影響可實現 EV）。
- [ ] 視覺化：升/降壓段達成率疊圖 + regime 軌跡。

---
### GATE
**問題：regime 達成頻率差異是否足以支撐 regime-conditioned 出場?**

- 樣本：N=1296、多 regime（含 2022 熊）、因果驗證 → ✅ 充足且穩。
- 方向：升壓深 reach ~2× 因果守住 → ✅（但僅 magnitude;direction 已證假象,排除）。
- snooping：偵測器/門檻先在前段定、勿依後段挑。

**決定：** [ ] 繼續 Phase 2　[ ] 補完 Phase 1 轉換/路徑再決定

---

## Phase 2: Backtest（regime-conditioned 出場規則）

- [ ] 規則：升壓→Dow-trail 抱 L4/L5、餘量留多；降壓→L3 靜態收、不追深。
- [ ] 接事件型 bracket（沿用 H114 框架）或 S001 ladder 出場。
- [ ] 基準對撞：(i) regime-agnostic 固定出場、(ii) SatZone-only（vol_ratio 是否已含 regime → VIX 冗餘?）。
- [ ] IS/OOS（時序切 + 跨 regime）損益%、Sharpe、**連敗/maxDD**。
- [ ] 控制「絕對波動水位」後 VIX regime 是否仍有增量（Invalidation #3）。
- [ ] 若贏：併入 journal_checklist（regime 一行:升壓博尾/降壓早收）+ vix_regime.py 已在 morning_briefing 報。
</content>
