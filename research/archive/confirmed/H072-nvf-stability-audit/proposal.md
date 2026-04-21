# Proposal: NVF Stability Audit by Weekday × Strategy × Period

## ID
H072

## Derived From
- H066（confirmed, 2026-04-17）：NVF 對 EstHL HIGH PF 2.44 vs LOW 1.33（+83%），跨年 6/6 一致。決策依據是**整體**訊號強，未深入 weekday × year sub-cell。
- H067（confirmed, 2026-04-17）：NVF 對 Reversal HIGH PF 1.58 vs LOW 0.96，Walk-forward 5/5。同樣是整體訊號。
- H071（rejected, 2026-04-21）：發現 EstHL × Tue × NVF 在 2024 PF=0.00、2025 PF=0.29，且 H066 Phase 1 的 weekday × NVF 表其實已露出 Tue HIGH PF=1.75（其他天 HIGH ≥ 2.28），但當時未被當作決策依據。

## Trading Intuition
H066/H067 的 NVF 決策建立在「整體高低組差異 +83%、跨年 6/6」之上，但這種 aggregate 訊號可能掩蓋了某些 sub-cell 的失效。H071 偶然揭露 EstHL × Tue × 2024–2025 是反向作用 cell（NVF 把 PF 從 1.74 推到 1.38），且這個失效在 H066 Phase 1 就有徵兆但未被注意。

如果 NVF 在某些 cell 結構性失效或反向，現行實盤可能持續執行虧損訊號。需系統性重審，避免日後又從另一個 sub-cell 「驚覺」失效。

## Hypothesis
NVF（night_norm ≥ 0.85）在 (strategy × weekday × period) 切片下，**並非每個 cell 都呈現一致的正向增益**。具體預測：
- 至少存在 1 個 cell 顯示 NVF 反向作用（ΔPF = NVF − baseline < 0）且樣本 ≥ 5 筆
- 至少存在 1 個 cell 在近期（2024–2026）顯示 NVF 失效或反向，但在早期（2021–2023）有效——代表 regime drift
- NVF 門檻穩定性可能因 cell 而異（某些 cell 在 0.85 失效但在 0.95/1.0 仍可用）

## Expected Distribution
Phase 1 預期觀察到：
- (strategy × weekday × period) cell 矩陣裡，**約 20–40% 的 cell** 顯示 NVF 反向或無效
- EstHL × Tue × 2024–2026 確認反向（H071 已發現，需用更乾淨的方法重驗證）
- 至少 1 個其他 cell（可能是 EstHL × Wed/Thu × 近期、或 Reversal × 某天 × 近期）也呈現失效模式
- 門檻 sweep 後，發現某些 cell 適合更高的 NVF 閾值（0.95+）

## Invalidation Condition
若 Phase 1 出現以下任一情況，archive：
- 所有 cell 的 NVF ΔPF 都 ≥ 0（NVF 無反向作用，當前實作健康）
- EstHL × Tue × 2024–2025 的反向是 H071 計算錯誤（用獨立路徑無法重現）
- 反向 cell 的樣本均 < 5 筆（噪音而非結構）
- 反向 cells 在跨 period 都不一致（無 regime drift 跡象，純隨機）

## Notes

### 範圍
- **三策略**：EstHL、Reversal（兩個都用 NVF）+ Exhaustion（control，未使用 NVF）
  - Exhaustion control 的目的：若它在某些 cell 也呈現「夜盤高波動 → 績效差」的模式，代表這是市場結構而非策略特性
- **5 個 weekday**：解掉所有 weekday filter，公平比較

### 時間切片
1. **By year**：2021、2022、2023、2024、2025、2026（每年）
2. **Rolling 2-year**：2021–22、2022–23、…、2025–26（5 個視窗，避免年初/年末切割）
3. **IS vs OOS**：IS 2021–2023、OOS 2024–2026（直接檢驗 H066/H067 confirm 後的 regime drift）

### NVF 門檻
- 預設 0.85（production 值）
- Sweep：0.70 / 0.85 / 1.00 / 1.15
- 對每個反向 cell，檢查是否在更高門檻（0.95、1.00、1.15）下仍可用

### 樣本要求
- 個別 cell ≥ 5 筆才採信
- 若某 cell 在所有 period 都不到 5 筆，標記「inconclusive due to N」

### 不重做的部分
- H066/H067 的 aggregate 結論（HIGH > LOW、跨年 6/6）在本研究**不重新質疑**
- 本研究**只**處理 sub-cell 穩定性

### Phase 2 方向（若 GATE 通過）
依失效 cell 的多寡與類型決定：
- **少量 cell 失效**：實盤加 cell-specific skip（例如「Tue 跳過 NVF 條件」或「Tue 改用 NVF ≥ 1.0」）
- **大量 cell 失效**：重新設計 NVF 邏輯（時間衰減、與其他 regime 指標結合）
- **僅 EstHL × Tue 失效**：narrow patch，只動 EstHL 的 Tue 處理

### 與既有研究的關係
- 不撤回 H066/H067 的 confirmed 狀態，只是補齊 sub-cell 健康度
- 若 H072 結論顯示 NVF 在某些 cell 失效，會建議在 S001/S002 spec 加上對應 caveat
