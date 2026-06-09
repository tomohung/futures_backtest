# Tasks: dci_long × 盤中關卡觸及 × 各時間點 — 多方關係地圖

## Phase 1: Distribution Research（核心：把條件地圖量到底）

時間點 T = {09:01,09:05,09:10,09:15,09:20,09:25,09:30}；關卡 L1–L5；dci_long = W-20~50 value-weighted tanh。

- [x] 算每個 t 的 dci_long(t)（W-20/W-50/H-20 三 universe）
- [x] 算 TX open-anchor 各時點/全日擺幅 + L1–L5 達成 + 連續擺幅 exc=up_full/EMA20
- [x] **核心地圖**：各 t × L_k，P(forward 達 L_k | 五分位) + base rate
- [x] **單調性檢定**：L4 @09:30 乾淨單調 Q1-5=11/19/22/33/50%，base 27%
- [x] **時點成熟曲線**：L4 Q5−base 09:01 +5%→09:15 +17%→09:30 +23%；t*≈09:15
- [x] **forward vs 全日對照**：L4 僅差 2pp（乾淨）、L3 差 14pp（較髒）
- [x] **關卡深度**：L1/L2 負(已達)、L3+13%/L4+17%/L5+13% → 深關卡鑑別、L4 最強
- [x] **H 對照**：H-20 與 W-20 重疊 corr=+0.938、鑑別力等同 → H 對多方冗餘
- [~] 熱圖視覺化：數據已足以 GATE，圖待 Phase 2 需要時補

---
### GATE
**問題：是否存在可用的「dci_long → 關卡達成」條件結構？**

- 至少某些 (t, L_k) 格：強分位 forward 達成率**顯著高於** base rate（且五分位單調），樣本足夠（每分位 ≥ 25 日）。
- forward-guard 後關係仍在（非純套套邏輯）。
- 能定出成熟時點 t* 與「鑑別力夠的關卡層」（預期 L4/L5）。
- data snooping：dci_long 公式沿用 H095（同窗校過）→ 同窗描述，正式 OOS 待資料擴充。

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2:（條件結構成立後）穩定性與下游接口
> 本案 strategy-agnostic，Phase 2 不是回測損益，而是把地圖變成可用結構 + 穩健性。

- [x] 穩定性：2025-H2 vs 2026 lift 一致(+18%/+17%)，base 漂移但條件 lift 穩；月別噪音(小樣本)
- [x] 定義可用門檻：W-50@09:30 ≥+0.110(q0.80) → L4 46% vs base 27%；lift q0.70~0.90 plateau +17~20%
- [~] OOS：無法做（DCI 單窗）；分段一致性為目前最強穩定證據，正式 OOS 待資料擴充
- [x] 下游接口：dci_long(W-50,09:30)≥+0.110 → forward L4 ≈46%(base 27%)，供順勢族引用

### Verdict（backtest.md）：建議 Confirmed（描述性，OOS-pending）— 條件結構穩定可用、跨段一致；正式 OOS 待資料。

---

## 後續（不在本假設範圍）
- **dci_short**：空方廣度（z(寬權值thrust)+z(家數)）× 下行關卡，待本多方假設定案後另立新假設。

## 產出腳本（保留於本目錄）
- `explore.py`（Phase 1 地圖）；可大量重用 H095 的 stock_features/wmean_tanh 與 H110 的 checkpoint 計算。
