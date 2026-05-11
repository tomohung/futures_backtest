# Proposal: Tier C 標準回檔進場訊號

## ID
H088

## Derived From
H085-fg-composite (Confirmed) 觀察到的覆蓋盲點

## Trading Intuition

H085 confirmed 後檢視 H084 framework 中 8 個 2018+ 事件，發現：

| 命中 | 沒命中 |
|---|---|
| 2018 貿易戰 (49 trig) | 2021-05-17 Tier C |
| 2020 COVID (43 trig) | **2022-10-25 Tier A 主底**（緩跌型）|
| 2022-07 sub (13 trig) | 2024-08-05 Tier C-sub |
| 2025 川普關稅 (22 trig) | **2026-03-31 Tier C**（最近一次）|

**H085 = Tier B 急速 panic specialist**，不覆蓋：
- Tier C 標準回檔（10-20% drawdown，較緩）
- Tier A 緩跌型結構熊（VIX 沒急飆）

H088 要驗證：能否設計一組訊號，**專門抓 Tier C 標準回檔**，與 H085 互補。

頻率上，Tier C 在 2018+ 約 4-5 個事件 in 8 yr ≈ **每年 0.5-1 次**，遠高於 H085 的 3-4 年 1 次。

## Hypothesis

> 對 Tier C 標準回檔（H084 zigzag 標記為 tier=C），可用「z 125MA ≤ −1.5 AND econ_score 未藍燈」
> 為主訊號（強調技術超賣、排除結構熊），輔以時間或反彈條件出場（不必固定持有 1 年），
> 在 0050 上的 IS+OOS 表現可達 Sharpe ≥ 1.2、勝率 ≥ 65%、平均報酬 > 同期 DCA + 2%。

## Expected Distribution

Phase 1 預期觀察：
- z 125MA ≤ −1.5 觸發日數約 200-400 天 in 8 yr（比 comp_z ≥ 3.97 多很多）
- 觸發日聚集在 2018/2020/2022/2024/2025/2026 各事件
- forward-return 分佈：+60D / +120D / +250D 均 > baseline，但幅度可能較 H085 小
- 排除「parent_tier=A」（結構熊內部）後，剩餘樣本 forward-return 應顯著為正
- 若用 econ_score 是否藍燈作為 regime gate，可區分「健康回檔」 vs 「結構熊回檔」

## Invalidation Condition

下列任一成立 → reject：

1. 排除結構熊後，Tier C 觸發日 forward 120d 中位數**不顯著高於** baseline（差距 < 1%）
2. 樣本數 ≥ 30 但勝率 < 55%
3. 與 H085 高度重疊（Jaccard 重疊度 > 60%）→ 沒帶來新覆蓋
4. 對 2026-03 那次 Tier C 仍未觸發（最近的 ground truth 沒抓到）

## Notes

### 候選訊號設計（Phase 1 要測）

1. **單因子**：
   - z 125MA ≤ −1.5
   - z 125MA ≤ −2.0
   - dist 250MA ≤ −5%
2. **過濾**：
   - 加 `econ_score ≥ 17`（排除藍燈/結構熊）
   - 加 `parent_tier ≠ A`（排除 H084 標記為結構熊內部）
3. **complementary 訊號**：
   - margin_drop_60d ≤ −5% 但 comp_z < 3.97（比 H085 低標）

### 與 H085 的協同

- H085 = 大魚（Tier B，3-4 年 1 次，250d hold，每筆 +60% 中位數）
- H088 預期 = 小魚（Tier C，每年 ~1 次，60-120d hold，每筆 +5-10% 中位數）
- 若兩者重疊度低（H085 訊號日不在 H088 訊號日內）→ 可同時 live 互補
- 若高度重疊 → H088 沒新覆蓋價值

### Phase 1 GATE

通過條件（皆需）：
- [ ] Tier C 觸發日 forward 120d 中位數 ≥ baseline + 1%
- [ ] 樣本 N ≥ 30
- [ ] 與 H085 重疊度 < 50%
- [ ] 至少在 2024-08 / 2026-03 兩次 Tier C 之中命中 1 次

### Phase 2 候選

- 出場規則：固定 60d / 120d hold vs 條件出場（z 125MA 回到 0 / SMA60 站上）
- IS/OOS split: 同 H085 (2018-09~2022-12 / 2023-01~2026-04)
- 倉位管理：仿 V1（cooldown + max=5）
