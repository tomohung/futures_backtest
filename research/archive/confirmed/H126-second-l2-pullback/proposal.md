# Proposal: 同向第二次 L2 拉回續攻

## ID
H126

## Derived From
Origin（原創；觀察自 2026-06-24 盤面）。
結構上重用 H120-l2-pullback-continuation 的 causal 偵測元件（`src/chart_ui/services/l2_pullback.py`），
但條件不同：H120 賭「任一次 L2 拉回站回」的母體 edge（causal 後 rejected、近 break-even）；
H126 賭「**同方向序數**」——能否從該 break-even 母體中，用「同日同向第 2 次（含以上）」這個條件切出正 edge 子集。

## Trading Intuition
2026-06-24 空方盤：第一次 L2 拉回放空，因 DCI 未明確表態、保守瞄 L3 出場；隨後價格反彈（過當日成本線）
又跌破，**同方向再出現一次** L2 拉回，續攻到下方 L4/L5。

核心直覺：第一次拉回後若「拉回失敗、沒形成反向趨勢」，又出現**同向第二次** L2 拉回，代表趨勢未反轉、
再度蓄力轉強。因此第 2 次 setup 的續航/賠率可能優於第 1 次，且可瞄更遠的 L3/L4/L5，而非第一次的保守 L3。

> 關卡階梯（錨在當日 running 極值或 ≥L2 反轉波段 re-arm 錨）：L1=0.385、L2=0.497、L3=0.711、
> L4=0.977、L5=1.225，皆 ×EMA20(日盤振幅)。L2 拉回偵測 = `detect_day`（causal，站回 5MA 進場）。
> VWAP/當日成本線 **不是偵測條件**，僅為 6/24 的描述；於 Phase 1 降為附帶觀察欄位（見下）。

## Hypothesis
同一交易日、同方向出現第 2 次（含以上）causal L2 拉回續攻進場（`2nd+`）時，其進場後的續航
（碰 L3/L4/L5 的比率）與賠率，**顯著優於同日同向第 1 次（`1st`）**；且此差異**不是純 selection
artifact**（不是因為「有第二次」本身就已篩出趨勢日、而趨勢日本來就會延伸）。

## Expected Distribution
- 多數交易日同方向 L2 拉回 setup 僅 1 次；具 ≥2 次同向 setup 的日子是少數但可觀（待 Phase 1 給 N）。
- `2nd+` 進場後碰 L3/L4/L5 的比率高於 `1st`，MFE 分佈右偏更明顯、MAE（進場後逆行）不顯著更糟。
- 對照正確虛無分佈後（同為趨勢日但只取第一次 / 條件期望基準），`2nd+` 仍保有可辨識的增益。
- DCI 在 `2nd+` setup 的表態強度高於 `1st`（佐證「再度蓄力轉強」）。

## Invalidation Condition
任一成立即視為不支持，轉 Archive 或修改假設：
1. 具 ≥2 次同向 setup 的樣本數過少（< GATE 門檻，見 tasks.md），不足以下結論。
2. `2nd+` 碰 L3/L4/L5 比率與賠率，相對 `1st` **無顯著增益**，或增益在對照正確虛無分佈後消失
   （純 selection / 趨勢日延伸的 tautology）。
3. `2nd+` 的 MAE（進場後逆行幅度）顯著惡化，使賠率優勢被更深停損吃光。

## Notes
- **附帶觀察欄位（VWAP）**：Phase 1 對每筆 `2nd+` 進場記錄「該次 setup 前，價格是否曾站上當日成本線
  （VWAP）又跌破」做為旁證欄位，僅描述、不入偵測條件。系統目前無 VWAP，需於 explore 腳本新做一條
  盤中 VWAP（typical price × volume 累計）。
- **記憶連結**：
  - excursion/序列類研究必對比正確虛無分佈（前瞻條件期望 / IID 洗牌），否則描述性相關被誤當 edge。
  - 先看零策略原始現象（excursion），每個對稱情境（多/空、序數 k）都實測，不推論帶過。
  - OOS(2026-03~06)≡高波 regime，IS/OOS 結論與單次低波→高波切換 confounded，Phase 2 解讀需留意。
  - DCI 是延伸/趨勢訊號，配順勢族有效（EstHL corr+0.53）；故 DCI 可能是 `2nd+` 續攻的乾淨濾網。
- **核心風險**：母體（任一次 L2 拉回）causal 後近 break-even（H120 rejected）。本假設成立與否，完全
  取決於「同向序數」這個條件是否真能切出正 edge，而非沿用母體既有 edge。
