# Archive: H087 加入廣度指標補強 H085 composite

## Status
**Rejected** — 廣度指標雖過「trough 命中率 ≥60% + max |r| <0.6 vs H084 4 軸」非冗餘 GATE，
但加進 H085 composite 後 forward-return 顯著下降。

## Date Closed
2026-05-12

## Summary

H084 確認 4 個非冗餘 fear 軸（VIX_pct、z 125MA、margin drop 60d、econ_score），
H085 把它們合成 comp_z 找 panic 抄底點。H087 想驗證能否從 stock_day/market_breadth
衍生**第 5 個非冗餘軸**進一步提升 H085。

Phase 0 完成 ETL backfill 2010-2026（含修正 TWSE API canned-data 污染 24 個日期）+
建 7 個廣度指標。Phase 1 發現 4 個指標通過非冗餘 GATE（adv/dec、new lows 52w、high-low diff、
new highs 52w），但 Phase 1.3 把通過的指標加進 H085 comp_z 後 **forward-return 每加一軸都下降**。

→ **H084 4 軸 composite 已 sufficient，廣度指標不增加 panic detection 價值。**

## Key Evidence

### Phase 0：ETL backfill 完成
- market_breadth TWSE=3989 / TPEX=3990
- stock_day 6,511,875 列，2010-2026 連續
- 副成果：修正 TWSE API canned-data 污染（11 個 echoed + 12 個 force-refresh + 1 永久壞掉
  quarantine + 2 公休日 markered）

### Phase 1.1+1.2：4 個指標通過非冗餘 GATE

對 21 個 Tier B/C trough 事件（16 個有廣度資料）：

| 指標 | Hit rate | max \|r\| vs H084 4 軸 | GATE |
|---|---:|---|:---:|
| new lows 52w | 88% | 0.40 vs z 125MA | ✓ |
| high-low diff | 88% | 0.55 vs z 125MA | ✓ |
| adv/dec | 81% | 0.17 vs margin drop 60d | ✓ |
| new highs 52w | 75% | 0.59 vs z 125MA (邊緣) | ✓ |
| adv-dec cum | 38% | — | ✗ (hit rate) |
| top20 concen | 38% | — | ✗ (hit rate) |
| value/stock | 25% | — | ✗ (hit rate) |

### Phase 1.3：加進 H085 composite 後 forward-return 全面下降

| Composite | 軸數 | +120d median | +250d median | +250d win |
|---|---:|---:|---:|---:|
| **comp_z_4** (H085 原版) | 4 | **+14.91%** | **+32.74%** | **75%** |
| comp_z_4 + adv/dec | 5 | +14.40% | +27.71% | 67% |
| ++ new lows 52w | 6 | +8.56% | +25.13% | 60% |
| +++ high-low diff | 7 | +8.22% | +24.50% | 57% |

每加一個廣度軸，**所有 horizon 的 forward-return 都下降**，cluster 從 9 暴增到 48。

## Why Rejected

1. **Hit rate ≠ 預測力**：廣度在 trough 達極值（事後驗算 88%），但向前看時極值會延伸到 trough
   前後幾週甚至假底，dilute H085 訊號
2. **H085 4 軸已優化**：高訊噪比的窄訊號，加任何指標都是訊號稀釋
3. **廣度極值是延伸性而非事件性**：與 VIX/margin 一次性 spike 不同

## Derived Hypotheses

- **H089**（已 rejected）：把廣度當「Tier C 專用獨立 trigger」而非 H085 擴展 → 也失敗
- **H090**（已 rejected）：漲停熱絡作為動量延續訊號 → 也失敗

H087 + H089 + H090 三個失敗形成**結構性結論**：
> 廣度/漲停指標對下跌防守（H079 confirmed）有效，
> 對上漲擇時無 edge，對 H085 panic specialist 無補強價值。

## Impact on Other Strategies

**不影響 S004-fg-composite（H085）confirmed 狀態**。反而強化了 H085 4 軸 composite 已優化的結論。

## Files

- `proposal.md` — 原始假設
- `tasks.md` — Phase 0+1 任務追蹤
- `results.md` — Phase 1.1+1.2+1.3 完整結果分析
- `build_breadth_indicators.py` — Phase 0.2 建 7 個廣度指標
- `percentile_correlation_with_breadth.py` — Phase 1.1+1.2 hit rate + correlation
- `extend_composite.py` — Phase 1.3 加廣度到 H085 composite
- `explore_quick_redundancy.py` — 冗餘性快速驗證
- `results/breadth_indicators.csv` — 7 指標 × 3990 日
- `results/percentile_table_with_breadth.csv` — 21 events × 16 指標百分位
- `results/hit_rates_with_breadth.csv` — 命中率
- `results/correlation_matrix_with_breadth.csv` — Pearson 矩陣
- `results/composite_comparison.csv` — comp_z_4 → 4p3 forward-return
