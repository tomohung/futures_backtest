# Backtest Results: VIX regime 當 ladder 出場期望調節器

## Date
2026-06-10

## Parameters
- 事件型 bracket：碰 L3 進場做多(p_L3),target 依規則、stop 共用 −0.266×EMA20、皆未到→收盤平。損益% = 點數/p_L3×100。
- regime = 昨日 VIX vs MA20（因果 lag,merge_asof backward 不含當日）。
- 規則 target offset（×EMA20;d_L4=0.266 d_L5=0.514）：regime(升壓→d_L5抱尾/降壓→d_L4早收)、fixed_L4、fixed_L5、satzone(=EstRange_SatUpper)。
- 全 TX 史;IS=2021-02~2024-12、OOS=2025-01~2026-06。腳本 `backtest.py`、`h117_transition_path.py`、`explore.py`。

## Results

### 1. 各規則 IS/OOS（損益% 平均 / Sharpe / maxDD）
| 規則 | IS 平均% | IS Sharpe | OOS 平均% | OOS Sharpe | OOS maxDD |
|---|---|---|---|---|---|
| regime 條件 | +0.015 | 0.04 | +0.007 | 0.02 | −4.58 |
| 固定 L4 | +0.016 | 0.06 | −0.005 | −0.02 | −3.86 |
| **固定 L5** | +0.017 | 0.05 | **+0.015** | **0.04** | −5.30 |
| SatZone | +0.010 | 0.04 | −0.004 | −0.01 | −4.55 |
- **regime-conditioned 出場不贏**：IS ≈ 固定;OOS 輸給「一律抱 L5」(+0.015)。高波日增量控制 regime 也無增益 → **Invalidation #1 觸發**。

### 2. ★ 為何抱尾兩 regime 皆 EV 微幅最佳（賠付不對稱,降壓三桶拆解）
| 降壓桶 | 佔比 | takeL4 | holdL5 | 差 |
|---|---|---|---|---|
| 到 L5 | 16% | +0.226 | +0.459 | +0.233 |
| 到 L4 未到 L5 | 28% | +0.177 | +0.097 | −0.081 |
| L3 失敗 | 56% | −0.136 | −0.145 | −0.009 |
- 「到 L4 未到 L5」(28%) 比「到 L5」(16%) 多,但**抱尾在中獎日多賺 +0.233（整階）、未中只少賺 −0.081（非全賠,那天仍 +0.097）** → 不對稱讓抱尾即使降壓低觸及率仍 EV 微勝。呼應 [[feedback_trail_giveback_is_scaleout_cost]]。

### 3. ★★ 出場風格 × regime（含風險指標,反直覺核心發現）
| regime | 策略 | 平均% | 勝率 | Sharpe | maxDD |
|---|---|---|---|---|---|
| 升壓 | holdL5 | 0.014 | 44% | 0.03 | **−9.08** |
| 升壓 | 半半blend | 0.012 | 45% | 0.03 | −6.48 |
| 升壓 | takeL4 | 0.010 | 52% | 0.03 | −4.36 |
| 降壓 | holdL5 | 0.020 | 48% | **0.06** | −3.61 |
| 降壓 | 半半blend | 0.016 | 50% | **0.06** | **−2.90** |
| 降壓 | takeL4 | 0.011 | 53% | 0.04 | −3.10 |
- **抱滿尾的回撤風險在升壓(maxDD −9.08)不在降壓(−3.61),差快 3 倍**;升壓抱尾 Sharpe 無增益(高 mean 被高變異吃掉),降壓抱尾/blend Sharpe 最佳。
- → **反直覺：該收斂出場/控回撤的是升壓(高波吐回兇),降壓反而可放手抱**。半半 blend 兩 regime 都最穩(Sharpe 並列最佳、maxDD 最小)→ 驗證 checklist 現行「L4 trim 一半 + 餘量 trail」。

### 4. 觸及率 / 轉換鏈 by regime × 多空（Phase 1,因果）
- 觸及率 升壓~2×降壓(深階放大:L5 2.3×、L1 1.07×);L1/L2 regime 不敏感。
- 轉換鏈 P(下|本) regime 差沿鏈放大,L4→L5 最大(多 升51/降36、空 升59/降52)。
- **空方深尾肥於多方**(全體 L4→L5 空56% vs 多46%),降壓尤甚(多36% vs 空52%)→ 驗證並銳化 checklist 多空不對稱。
- 多空觸及率因果上近對稱(早期假象已 lag 除);唯 L5 略偏空(肥左尾)。

## Walk-Forward Summary
IS(2021-24)/OOS(2025-26,跨升降壓)。regime-conditioned target 切換 IS≈固定、OOS 輸固定L5。但出場「風格×regime 的回撤」維度有真結論:升壓抱尾回撤兇、降壓溫和。

## Parameter Sensitivity
- target(L4/L5)：抱尾 EV 微幅最佳兩 regime,但升壓回撤代價大。
- 半半 blend：對 target 選擇最穩健（兩 regime Sharpe 最佳/並列、maxDD 最小）。
- stop/手續費未細掃;edge 絕對值薄(±0.01-0.02%/筆),扣成本多蒸發 → 非獨立 P&L edge。

## Verdict（待裁決）
**[x] Inconclusive — regime 作「期望 + 回撤紀律 context」成立,作「機械 target 切換規則」否決。**
- ❌ regime-conditioned target 切換 OOS 不贏固定 L5（Invalidation #1）。
- ✅ regime 真貢獻(描述性,因果穩):(a) 觸及率~2×(期望校準)、(b) **回撤反直覺(升壓控、降壓放)**、(c) 多空深尾不對稱(空肥,降壓尤甚)。
- 落地：已寫入 morning briefing VIX regime 區塊(含回撤動作提醒);checklist 半半 blend 獲驗證,regime 微調 trim 比例(升壓多 trim)。
- 不晉升 live 機械策略;作為看盤 context + checklist trim 比例的 regime 微調。

## Derived Hypotheses
- **觀察(memory)**：抱尾回撤風險在升壓非降壓(反直覺)→ 出場收斂該在高波,不是低波。
- **checklist 真正待修非 regime 而是 DCI 軸**(OOS 不穩,見 H111);regime 與時點(H114)才是站得住的 context 軸。
- 空方深尾(L4→L5)肥且降壓更肥 → 空方降壓仍可抱尾(52%),與多方降壓(36%該多trim)分流。
</content>
