# Backtest Results: Morning Dip Reversal

## Date
2026-04-12

## Strategy Versions Tested

### v1: Dip detection + rebound ratio
- 偵測早盤 dip（前波高點回落 > 0.3%），用第一次反彈比例區分 single/double dip
- 停損/停利用百分比
- **結果：IS 2021~2024 EV=-13.7, PF=0.96（負期望值）**
- rebound_ratio_threshold 從 0.4~0.7 幾乎不影響結果（交易筆數只差 12 筆），濾網無效

### v2: BB/KD 超賣 + MA5 確認
- 改用 reversal 策略的進場模式：BB(15,2σ) 觸及下軌 or KD(9,3)<20 → latch → 站上 1m 5MA 進場
- 時間窗口：9:15~9:45（W1 only）
- **BB only IS：572 筆, WR 39.3%, PF 0.93, EV -21.6**
- **KD only IS：784 筆, WR 40.6%, PF 0.99, EV -4.2**
- BB/KD 幾乎每天都觸發 latch，沒有真正過濾壞交易

### v3: BB + MA5 + 日線 SMA 趨勢濾網
- 加入日線 SMA，只在前一日收盤 > SMA 時做多
- SMA 掃描 5/10/20/40/60/120 天

| SMA | IS 筆數 | IS EV | OOS EV |
|-----|---------|-------|--------|
| 無 | 572 | -21.6 | +30.1 |
| 10d | 313 | -27.1 | +84.8 |
| 20d | 331 | -36.3 | +103.0 |
| 40d | 325 | -15.5 | +120.2 |
| 60d | 332 | -40.5 | +93.5 |

**IS 全部為負，OOS 正是因為 2026 年高波動撐起（3 個月 +10,290 點）。**

## Parameter Sensitivity (IS 2021~2024)

所有參數組合的 IS 期望值都在 -40 ~ +20 之間，沒有穩定正期望的參數區域。

唯一微正的零星組合：
- sl=0.15%, tp=0.6%: EV +3.5（但 WR 僅 23%）
- tp=1.0%: EV +15~20（但 PF 僅 1.05）

## Verdict
**Rejected**

## Why Rejected
1. **In-sample 無正期望值**：所有版本（v1/v2/v3）在 2021~2024 都是負或打平
2. **濾網無效**：rebound ratio、BB/KD、SMA 都無法有效篩出高品質交易
3. **交易太頻繁**：BB/KD 幾乎每天觸發，沒有選擇性
4. **IS/OOS 不一致**：IS 虧、OOS 賺的反差代表 2025~2026 市場特性不同，非策略有 edge
5. **Phase 1 的統計優勢無法轉化**：morning dip 現象存在，但用機械式規則抓不住

## Derived Hypotheses
（無，此方向已充分測試）
