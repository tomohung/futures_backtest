# Proposal: 同 leg 多次拉回進場（被濾掉的淺拉回不佔名額）

## ID
H124

## Derived From
H120（l2-pullback-continuation）的 backtest 階段 — 實盤觀察衍生

## Trading Intuition
2026-06-11 盤中觀察：08:45→09:16 是一條完整的上升 leg，其中 09:05–09:07 出現一個又深又強的拉回（約 379 點），09:08–09:11 收盤站回 5MA 續攻直達 L3——這是教科書級的 L2→L3 拉回續攻。但主圖上 H120 沒有畫出這筆訊號，反而只在後面的 Leg2(09:43 空)、Leg3(10:45 多) 各畫一筆。

診斷後發現：H120 的設計是「**每條 leg 只取第一個拉回站回 5MA，進場後 break**」。在 Leg1 裡，這個「唯一進場名額」在更早的 08:58 就被一個**淺拉回**（depth_frac 0.16）佔走，而該淺拉回又恰好被 `MIN_DEPTH_FRAC=0.25` 濾網丟棄 → 結果整條 Leg1 一個訊號都沒有。等到 09:08 那個 depth_frac 0.79 的強拉回出現時，state machine 早已 break，根本沒被評估。

關鍵矛盾：被「淺拉回濾網」濾掉的那筆，**邏輯上等於沒進場**，卻仍然消耗了該 leg 的進場名額。

## Hypothesis
若「被 MIN_DEPTH_FRAC 濾掉的淺拉回不佔用該 leg 的進場名額」（即：找到第一個拉回站回 5MA 後，若其 depth_frac 不足而被丟棄，則繼續在同一條 leg 內尋找下一個拉回站回 5MA），則能補捉到目前漏掉的「同 leg 內更深的後續拉回續攻」訊號，且這些補捉到的訊號之**期望值（avgR / 勝率）不劣於現行訊號**，使整體 PF / 期望 R 淨提升（或至少持平而增加交易機會）。

對照組與實驗組：
- **A（現行 baseline）**：每 leg 取第一個拉回站回 5MA，break；之後再套 MIN_DEPTH_FRAC 濾網（淺的直接消失）。
- **B（filtered 不佔名額）**：第一個拉回若 depth_frac < MIN_DEPTH_FRAC 被丟棄，則 reset state 繼續找同 leg 下一個拉回；第一個「合格」的拉回才 break。**每 leg 仍最多一筆合格進場。**
- **C（同 leg 全取）**：同 leg 內所有合格拉回都進場（可能多筆），檢驗「多筆」是否反而引入雜訊。

## Expected Distribution
- B 相對 A 會**新增一批**「同 leg 第二/第三次拉回」的進場。預期這批新增訊號的 depth_frac 偏高（因為前面已有一次淺拉回），avgR 應 ≥ baseline。
- 若新增訊號 avgR 明顯為正且勝率不掉 → 支持 B。
- C 預期會引入較多淺/晚的雜訊筆，PF 可能不如 B。

## Invalidation Condition
- 全窗（含 OOS）下，B 新增訊號樣本數 < 30 → Inconclusive（單一案例過擬合，不足以下結論）。
- B 新增訊號 avgR ≤ 0 或勝率顯著低於 baseline → Rejected（漏掉的那些本來就該漏）。
- B 整體 PF / 期望 R 未優於 A（或變差）→ Rejected，維持現行 break 設計。
- 改善僅來自 2026-06-11 那一天、其餘日期無貢獻 → Rejected（data snooping）。

## ⚠️ 必須 CAUSAL（H120 前視偏誤教訓）
H120/S005 已於 2026-06-15 因**前視偏誤作廢**：原 `detect_day` 用 ZigZag leg 終點 `em`（反轉後才知的未來資訊）當進場搜尋上界，系統性濾掉失敗站回 → 灌高勝率/EV。**chart-ui `h120.py` 的 `detect_day` 即此非 causal 版本，僅保留作行情參考，不可作為 H124 的驗證基礎。** 用它跑出的任何「改善」都不可信（重蹈覆轍）。

H124 必須在**完全 causal 的 streaming 偵測**上做（基準＝`research/archive/rejected/H120-l2-pullback-continuation/validate_causal.py` 的 `detect_causal`）。該版進場相位 = [翻上事件, 下一翻下事件)，不碰未來 em。

### 在 causal 框架下，H124 仍然成立
`detect_causal` 對每個相位記錄**第一個站回 5MA**（不論深淺）即 `done=True`，深度濾網（depth≥0.25）是**事後**才套（validate_causal.py:306）。所以一個淺的第一站回仍會「燒掉」整個相位的進場名額 → 後面更深的拉回站回拿不到訊號。這正是 2026-06-11 現象的 causal 對應。

- **A（causal baseline）**：第一個站回(任意深度)→done；事後濾 depth≥0.25（淺的直接消失，相位啞掉）。
- **B（causal，淺站回不燒名額）**：站回若 depth<0.25 → 不記錄、reset 子狀態(sub=extend, peak=現值) 繼續在同相位找下一個站回；第一個 depth≥0.25 的站回才記錄並 done。每相位仍最多一筆合格進場。
- **C（causal，同相位全取）**：同相位所有 depth≥0.25 站回都進（可能多筆），檢驗多筆是否引入雜訊。

## Notes
- 真相源（若 Confirmed 才動）：`src/chart_ui/services/h120.py`（行情參考層）。但 H124 的去留以 **causal 回測**為準，不以 chart 視覺為準。
- 診斷腳本：`research/active/H120-l2-pullback-continuation/diag_0611.py`（leg-bounded，含前視偏誤，僅用於解釋 9:11 視覺現象，**不可作為 edge 證據**）。
- 樣本數結論必附；純結構改動不新增參數，OOS 須跑。
- confound：OOS≡高波 regime（memory `oos_equals_highvol_regime`），方向性 P&L 結論須謹慎；「extra 筆 avgR vs 重疊筆」這種 within-sample 對照較穩。
