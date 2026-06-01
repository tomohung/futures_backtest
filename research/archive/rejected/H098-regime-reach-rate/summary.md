# Archive: Regime 對 L1-L4 觸及率的影響與轉換偵測

## Status
Rejected（主假設多方支不成立；空方支與 H095 §5 重複，無新增 edge；延伸支證據弱）

## Summary
問：H095/H097 的全期 pooled L1-L4 階梯係數，是否其實隨多/空/盤整 regime 漂移？
用 causal 日線**價格**分類器（MA±std 等）把 TX 日盤分桶，比較上/下方 open-anchor 觸及率。
結論：**價格型 regime 分類器對 reach 的鑑別力強烈不對稱——只在空方成立，多方≈盤整**；
作為「能改良 H095 階梯」的新假設，整體 reject。

## Key Evidence
- N=1281 日（2020-12 ~ 2026-05），桶 多487/盤564/空230（皆 ≥100）。
- **空方確認**：空頭日下方 L3 觸及 34%[29,41] vs 盤整 23%[20,27]（CI 分離）；L4 20% vs 12%。
  不對稱度 L3 −6% / L4 −7%。三個 causal 分類器（MA±std / MA-slope / %-dev）方向一致（−6%~−12%）。
- **多方否決**：多頭上方 L3 23%[20,27] vs 盤整 24%[21,28]（CI 重疊）；不對稱度 ≈ +1%。
  多頭看起來跟盤整一樣，無往上延伸傾向。
- **轉換偵測（延伸支）證據弱**：不對稱度僅在 flip 前 1 日尖峰（轉多 +0.42/轉空 −0.49），
  且為機械性（決定性收盤本身即是該不對稱日），無穩定多日前兆。

## Why Rejected
1. 多方支與預期相反（無鑑別力）→ proposal Invalidation #1 在多方觸發。
2. 空方支雖成立，但只是用價格分類器重現 H095 §5（廣度→空方鑑別力 ~2x）的已知結論，
   無新增 edge；且改良只惠及單邊（空頭日下方階梯）。
3. 延伸支（不對稱度當獨立轉換訊號）領先僅 ~1 日且機械性，不可獨立操作。

## 旁證（重要對照，非本假設範圍）
歸檔同時做的 DCI 改版檢查（`H095/dci_newmetric_check.py`）顯示：**廣度型** dci_long 對上方 L3
reach 單調 6%→65%、point-biserial +0.39——**多方 regime 訊號要靠廣度，不是 TX 自身價格趨勢**。
這正好解釋為何本假設（價格分類器）多方支失敗，與 H095 §5 一致，故 reject 成立不矛盾。

## Derived Hypotheses
- **H099（暫）open-anchor 階梯係數重擬**：現行 0.385/0.497/0.711/0.977 是 max-excursion 擬的；
  若採 open-anchor 觸及，open-anchor pooled L1 僅 54%（非名目 90%），應重擬係數對齊達到率。
- **H100（暫）空頭日下方係數放大量化**：空頭日下方 L3 觸及 34% vs 全期 25%，量化「空頭日
  下方係數該乘多少」回到目標達到率（若要單邊回灌 H095 出場仍可從這切入）。
- **廣度型多方 regime**：多方 reach 用廣度（DCI/dci_long）而非價格分類，鑑別力才出得來
  （見旁證；屬 H095 dci_spec 範疇）。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md（含 touch_rates.png / asymmetry.png / event_study.png / rate_table.csv）
- 旁證腳本：`research/active/H095-reach-ladder-exit/dci_newmetric_check.py`
