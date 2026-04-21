# Proposal: NVF Aggregate Signal Decay Verification

## ID
H073

## Derived From
- H066（confirmed, 2026-04-17）：EstHL NVF HIGH PF=2.44 vs LOW 1.33（**+83.6%**），跨年 6/6
- H067（confirmed, 2026-04-17）：Reversal NVF HIGH PF=1.58 vs LOW 0.96（**+64.3%**），WF 5/5
- H072（in progress, 2026-04-21）：本研究下 EstHL aggregate diff 變 **+19.5%**，Reversal 變 **+29.5%**——僅 4 天就衰減 2-4×

## Trading Intuition
H066/H067 的 confirm decision 建立在 aggregate HIGH/LOW PF 差距上（83% / 64%）。H072 用相同邏輯（night_range/SMA20、threshold 0.85、no weekday filter）卻只看到 19.5% / 29.5% 的差距。

四天內樣本只多了幾筆交易（不到 5%），不可能造成 3-4 倍的訊號衰減。最可能的原因有三：

1. **方法學差異**：H066 用 median split（threshold = median ≈ 0.897），H072 用固定 0.85
2. **calculation pipeline 差異**：night_norm 演算法、SMA 對齊、回測參數其中一處差異
3. **真實 regime drift**：訊號真的在持續衰減（但 4 天內衰減 4× 機率極低）

不論真因為何，這個結果都需要解決，否則 H072 的「sub-cell drift」結論本身就建立在不穩固的 baseline 上，後續任何 NVF 相關研究都會不可信。

## Hypothesis
**H072 觀察到的 NVF aggregate 訊號衰減（從 H066/H067 的 +83%/+64% 到 +19.5%/+29.5%）並非真實 regime drift，而是方法學差異（median split vs 固定 threshold 0.85）造成的數值差異。**

具體預測：
- 用 median split（threshold = 當前 median，估計 ~0.85-0.90）重做 H072 aggregate，數字應接近 H066/H067 confirm 時的水準（差距 < 20% 落差）
- 用 H066 當時的精確資料窗口（截至 H066 confirm 日 2026-04-17 為止）重做 aggregate，數字應幾乎完全重現
- Expanding window 看 aggregate diff 從 H066 confirm 日往後每加 1 週的變化，應呈現平緩趨勢，不會有 step change

## Expected Distribution
- Median split 重做後，EstHL aggregate diff 應 ≥ 60%（接近 H066 的 83%）
- 截至 2026-04-17 的 cutoff 重做，數字應近乎完全重現 H066/H067
- Expanding window 每週新增的 aggregate diff 變化應 < 5 個百分點
- 若以上三項皆符合，**H066/H067 的 aggregate baseline 仍為健康**，H072 的 sub-cell drift 結論可信

## Invalidation Condition
若以下任一情況成立，假說（方法學差異論）被反駁：
- 用 H066 當時的 median split + 截至 2026-04-17 cutoff，數字仍與 H066 不一致（差距 > 20%）→ **資料 pipeline 有 bug，必須先修復**
- Expanding window 顯示 aggregate diff 在 2026-04-17 後 4 天內真的下降 > 30 個百分點 → **真實 regime drift**，H066/H067 結論可能已失效，整個 NVF 邏輯需重審
- Median split 重做後，aggregate diff 仍 < 40%（明顯低於 H066 的 83%）→ **方法學差異不足以解釋全部衰減**，仍有部分真實 drift

## Notes

### 範圍
- **只關注 aggregate（不細切 weekday）**——本研究只解決 baseline 數字一致性
- 三個策略都跑（EstHL / Reversal / Exhaustion），但 EstHL 與 Reversal 是主要對象（對應 H066 / H067）

### 方法重做
- 完全重現 H066/H067 的方法：
  - night_range = night_session_high − night_session_low
  - SMA20 normalisation（與本研究相同）
  - **median split**（threshold = night_norm 的 median）取代固定 0.85
  - 注意：H066 也報告固定 0.85，但 main result 是 median split 的 +83%

### Expanding Window
- 從 2026-04-17（H066 confirm 日）開始
- 每加 1 週重算 aggregate HIGH/LOW PF 與 diff
- 截至 2026-04-21 共 4 個資料點（窗口太短，主要看趨勢方向）

### IS / OOS 切割（補充）
- IS = H066 confirm 前的全資料（即 ~2026-04-17 cutoff）
- OOS = 2026-04-18 ~ 2026-04-21（4 天）
- 這個 OOS 樣本量很小（每策略 < 10 筆），但能**直接量化** H066 confirm 後的真實 OOS 表現

### 不重做的部分
- H072 的 sub-cell 分析、threshold sweep、Exhaustion control——這些都建立在 baseline 數字上，等 H073 確認 baseline 後若需要會在 H072 distribution.md 加 caveat
- 任何策略改動建議——本研究純粹是方法學除錯

### Phase 2 方向
若 H073 確認衰減純為方法學差異 → H072 的 sub-cell 結論直接成立，回 H072 GATE
若 H073 發現真有 drift → 開 H075「NVF baseline 設計重審」（如改用 EMA / rolling percentile / adaptive threshold）
