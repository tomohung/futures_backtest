# Archive: vol_ratio vs DCI 當「還有沒有空間」調節器

## Status
Rejected

## Summary
測 SatZone 的 vol_ratio（量比）能否取代 journal_checklist 的 DCI 軸,當「碰 L3 後還有沒有空間到 L4」的調節器。結果 vol_ratio 對 P(L4|L3) 的分辨力 **IS/OOS 符號翻轉、不可用**;dci_long(=ext_long) 也 OOS 非單調;唯「碰觸時點」穩。

## Key Evidence
- vol_ratio 分帶 P(L4|L3)：IS −26%（縮量反而續攻多）→ OOS +41%,**符號翻轉**。
- 根因 = **OOS≡高波 regime**（44/44,ema20 260→658）;vol_ratio 方向隨 regime 變（低波 −18%/高波平）。
- dci_long(=ext_long) OOS 非單調;時點 IS+38/OOS+64 雙單調完勝。
- vol_ratio 中位≈1.02 對齊 L4,但 cont=1/0 幾乎一樣 → 零分辨力。

## Why Rejected
無方向的 vol_ratio 分不出「突破續攻」vs「climax 耗竭」兩種高量 → 符號不穩、regime-dependent、輸時點（無效條件 #2/#3 觸發）。「放量=還有空間」直覺連 IS 都是反的。

## Derived Hypotheses
- **H116（已 rejected）**：定向版（累積淨多空力道,使用者 bull_bear_force_volume 指標）修好了符號,但多 regime 仍不穩。
- **方法論（記憶）**：[[project_oos_equals_highvol_regime]] — OOS≡單一高波 regime,所有 IS/OOS 結論 confounded。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md（含 vol_ratio 否決 + regime 診斷 + 多空力道量 §5）
</content>
