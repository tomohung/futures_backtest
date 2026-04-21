# Proposal: NVF Method Upgrade (Production)

## ID
H075

## Derived From
- H066（confirmed, 2026-04-17）：EstHL NVF EMA+median = +83.6%
- H067（confirmed, 2026-04-17）：Reversal NVF SMA+median = +64.3%
- H072（in progress, 2026-04-21）：發現實盤 SMA+0.85 = +19.5%/+29.5%，找出 sub-cell drift
- H073（confirmed, 2026-04-21）：證實 H066/H067 baseline 健康，「衰減」是方法學差異；**實盤用了比 H066 評估弱 4× 的 NVF 版本**

跳過 H074（Reversal Tue 加碼）— 那是策略增強類，跟 NVF 升級無關，先擱置。

## Trading Intuition
H073 揭露 production `src/analysis/key_prices.py` 用 SMA20 + 0.85 fixed threshold，但 H066 評估時用 EMA20 + median split，後者 aggregate diff +73.6%，前者只有 +19.5%——**實盤一直使用比評估值弱 4× 的 NVF 版本**。

升級實盤 NVF 方法（換成 EMA + expanding median）可能直接把 NVF 的有效性拉回 H066 評估水準，且**無須改變策略邏輯**。連敗保護也可能改善（因為 expanding median 自動適應 vol regime；H073 觀察到 2026 Q1 raw range 翻倍，固定 0.85 已被新常態拉低）。

## Hypothesis
**將實盤 NVF 從 SMA20 + 0.85 fixed 升級為 EMA20 + expanding median，能在 EstHL 與 Reversal 上同時改善 PF、連敗結構、與長期穩定性，且無實作障礙。**

具體預測：
- EstHL aggregate PF 改善（NVF HIGH 組 PF 從 2.10 提升到接近 2.44）
- Reversal aggregate PF 改善（NVF HIGH 組 PF 從 1.39 提升到 1.6+）
- 連敗結構不惡化（max consecutive losses 持平或改善）
- Walk-forward 5+ 年穩定（每年 NVF 增益方向一致）

## Expected Distribution
Phase 1 預期觀察到：
1. Expanding median trajectory 平滑（不是 step function），即便 2026 Q1 vol 暴漲也只小幅上漂
2. EMA + expanding median 在 walk-forward 每年 PF 都贏 SMA + 0.85（至少 5/6 年）
3. 高 vol regime（如 2024–2026）NVF 增益更明顯（因為 SMA + 0.85 失效特別嚴重）
4. **連敗 max length 不增加**

## Invalidation Condition
若以下任一情況成立，archive：
- Expanding median trajectory 在某個年度跳升 > 0.15（不穩定，無法當 live threshold）
- EMA + expanding median 的 walk-forward 增益 ≤ 50% 年份（不一致）
- 換方法後**最大連敗長度增加 ≥ 2 筆**（破壞心理保護價值）
- 實作上 expanding median 需要的歷史資料超過 production pipeline 可承受

## Notes

### 範圍
- 主要對象：EstHL（H066）、Reversal（H067）兩個有 live 部署的策略
- Exhaustion 不納入（非 live + H072 確認 NVF 對其反向）

### 候選方法
1. **EMA20 + expanding median**（首選，最忠於 H066）
2. **SMA20 + expanding median**（保留 SMA 求直覺，只升級 threshold）
3. **EMA20 + fixed 0.93**（接近長期 median，但不會自適應 vol regime）
4. **SMA20 + fixed 0.85**（current production，當作 baseline）

### 評估指標（按優先排序）
1. **連敗結構**：max / avg consecutive losses, worst streak P&L
2. **Walk-forward PF 一致性**：每年 PF 是否都正向、是否方向一致
3. **Aggregate PF**
4. **Sharpe**
5. **NVF HIGH 組樣本數**（避免方法太嚴格導致樣本不足）

### Phase 1 任務
1. **Median trajectory 分析**（user 在對話中要求）：畫每天的 expanding median，看 2026 Q1 vol 暴漲下漂多少
2. 4 種方法 × 兩策略 × walk-forward
3. 連敗結構對比
4. 在 2026 Q1 vol regime shift 時段下，4 種方法的 NVF 通過率與 PF 對比

### Phase 2（GATE 通過後）
- 在 `src/analysis/key_prices.py` 修改 NVF 計算
- backtest 驗證實盤碼端對端結果與 research 一致
- 更新 H066/H067 archive summary（注記方法升級）
- 更新 strategies/live/ spec 說明新 NVF 規則

### 注意事項
- **不要為了改善 PF 而傷害連敗保護**（user 多次強調，已記入 memory）
- expanding median 必須是 causal（用過去資料，不能 look-ahead）
- 若需要熱身期（warmup），明確界定起算日（例如 2021-04-01 之後才可用）

### 與 H072 的關係
H072 GATE 暫停在 EstHL Tue patch。H075 結果可能改變 sub-cell 失效圖：若新 NVF 方法本來就避開了 EstHL Tue 的失效，那 H072 的 patch 可能不需要；反之則仍需。H075 完成後回 H072 重新評估 cell matrix。
