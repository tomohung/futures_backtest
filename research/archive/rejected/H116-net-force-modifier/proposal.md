# Proposal: 累積淨多空力道 當 ladder 續攻的早碰層二級修正

## ID
H116

## Derived From
H115（volratio-vs-dci-room）的 distribution 階段 → H115-d1。
背景：[[project_oos_equals_highvol_regime]]、H114（碰觸時點為 ladder 續攻主軸）。

## Trading Intuition
H115 證明無方向的 vol_ratio 當 room 軸會符號翻轉、不穩。改用使用者既有指標
`indicators/tradingview/bull_bear_force_volume.pine` 的概念——**累積淨多空力道**
（Σ(漲K量 − 跌K量) / Σ總量,當日從開盤累積,界 −1~1,天生抗 regime）——
方向就對了（買壓→續攻）且符號 regime-stable。

主軸仍是「碰觸時點」（早碰續攻、晚碰收手,H114）。本案問的是：**在早碰層之上,
碰 L3 當下的累積買賣壓能否再加分**——早碰 + 累積買壓強 → 續攻 L4 機率更高。

## Hypothesis
**碰 L3 當下「累積淨多空力道比例」對 P(L4|L3) 有正向、regime-stable 的分辨力
（買壓→續攻），且在「早碰層」對「碰觸時點」有獨立增量。** 滾動版（近 N 根）無效,只用累積版。

## Expected Distribution（Phase 1 已驗,列為基線）
- 累積淨力分帶 P(L4|L3)：IS +34% ↗ / OOS +42%;低波 +27%、高波 +3~9%（**兩 regime 同向為正**,不像 vol_ratio 翻）。
- 控時點增量（早碰層）：IS +9% / OOS +26%（corr(淨力,時點)=−0.43,非純代理）;晚碰層不守。
- 滾動版（近 20 根）：IS +6% / OOS −2% → 噪音,排除。

## Invalidation Condition
1. 補入異質 regime（低波 OOS / 2022 結構熊）後,累積淨力的早碰層增量 **符號翻轉或塌 <~10%** → 跟 vol_ratio 一樣不穩。
2. Phase 2 規則化後,「時點 + 淨力修正」**OOS 績效不優於純時點規則**（[[feedback_filter_eval_includes_streaks]]：連敗/DD 也要看）。
3. 增量在控時點後消失（純時點代理）。

## Notes
- **因果鐵律**：淨力比例於 t_k 當下即可得（TX 1分K open/close/volume 累積,causal）。
- **★ Phase 2 regime-blocked**：現有 OOS(2026-03~06) ≡ 單一高波 regime（[[project_oos_equals_highvol_regime]]）,
  早碰層 cell 僅 n10~13。**不在同一份 44 天 OOS 上做 Phase 2 回測**（會 snooping）。
  Phase 2 待 **異質 regime 資料補足**（pre-2025-06 / 2022 熊）後再啟。
- 若日後 Confirmed：併進 H114 的時點出場規則,當早碰層 sizing 修正;使用者既有指標即可看盤套用。
- Phase 1 腳本：`../H115-volratio-vs-dci-room/h115_force.py`（已完成,結果見 H115 distribution.md §5）。
</content>
