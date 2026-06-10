# Tasks: VIX regime 當 ladder 出場/sizing 期望調節器

## Phase 1: Distribution Research（部分已完成）

- [x] VIX regime 因果偵測器（昨日 VIX vs MA20 升壓/降壓;20日變化方向;水位帶）→ `src/analysis/vix_regime.py`。
- [x] VIX lag 1 疊 ladder 達成頻率（N=1296）：升壓深 reach ~2×（多L4 30/L5 16 vs 降壓 19/7）。
- [x] ★ 因果檢定：方向偏移（多−空L4）lag 後消失（+0~3%）→ 確認 magnitude 真、direction 假象。
- [x] 偵測器比較：VIX>MA20 / 20日變化 / 10日變化 / EMA交叉 / 純水位 → 前兩者最佳。
- [x] 補：續攻轉換 P(L4|L3)/P(L5|L4) by regime（`h117_transition_path.py`）：L4→L5 升壓 52% vs 降壓 36%（+16pp）。
- [x] 補：碰 L3 後路徑 MAE/EMA20：續攻日 median 兩 regime 同(−0.12)→ 升壓 2× 沒被 whipsaw 吃掉、轉得成可實現 EV。
- [ ] 視覺化：升/降壓段達成率疊圖 + regime 軌跡（Phase 2 前可補）。

---
### GATE
**問題：regime 達成頻率差異是否足以支撐 regime-conditioned 出場?**

- 樣本：N=1296、多 regime（含 2022 熊）、因果驗證 → ✅ 充足且穩。
- 方向：升壓深 reach ~2× 因果守住 → ✅（但僅 magnitude;direction 已證假象,排除）。
- snooping：偵測器/門檻先在前段定、勿依後段挑。

**決定：** [ ] 繼續 Phase 2　[ ] 補完 Phase 1 轉換/路徑再決定

---

## Phase 2: Backtest（regime-conditioned 出場規則）

- [x] 事件型 bracket + regime target 切換(升壓 L5/降壓 L4) vs fixed_L4/L5 vs SatZone。
- [x] IS/OOS + 連敗/maxDD：regime 切換 OOS 輸固定 L5（Invalidation #1 觸發）。
- [x] 出場風格×regime 風險拆解：★反直覺——抱尾回撤兇在升壓(−9.08)非降壓(−3.61);blend 兩 regime 最穩。
- [x] 三桶 EV 拆解：抱尾兩 regime 微幅最佳(賠付不對稱),差別在變異非 EV。
- [x] 落地：morning briefing VIX regime 區塊已含回撤動作提醒;checklist 半半 blend 獲驗證。
- [x] Verdict：Confirmed（描述性 regime context,因果多 regime 驗證,已上線）+ 機械 target 切換否決（同 H114 結構）。
</content>
