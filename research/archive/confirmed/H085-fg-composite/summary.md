# Archive: TW Fear & Greed Composite — Tier B 急速 panic 進場

## Status
**Confirmed**（限定 `comp_z` 變體 + V1 倉位管理；`comp_pct` 變體被 reject）

## Date Closed
2026-05-11

## Summary

由 H084 的 4 個非冗餘 fear 指標（VIX_pct、z 125MA、margin_drop_60d、econ_score）
以 5 年 rolling IQR 標準化加總成 `comp_z`，當 `comp_z ≥ 3.97` 時收盤買入 0050（含息），
持有 250 個交易日（≈1 年）後出場。

倉位管理採 V1：每觸發再進場間隔 ≥ 5 個交易日、同時最多 5 倉。

## Key Evidence

### 全期間 (2018-09 ~ 2026-04, 7.6 yr)
- **15 trades, 100% 勝率**
- Sharpe **2.10**（vs DCA 250d 1.0、Buy-and-Hold 1.0）
- MaxDD **−20.8%**（vs B&H ≈ −34%）
- 終值 **5.80×**（per-$ basis, vs B&H ≈ 5.5×）
- 中位數 trade return +26.3%、平均 +55%、最差 +10.5%、最佳 +124%

### IS / OOS 一致性
- IS (2018-09 ~ 2022-12): 10 trades, Sharpe 1.83, MaxDD −16.6%
- OOS (2023-01 ~ 2026-04): 2 trades*, Sharpe 3.65, MaxDD −10.8%
  *資料截止 2026-04-30 限制；理論 OOS 可達 5 trades

### 4 個 fear 事件全勝
- 2018 中美貿易戰 (5 trades, +10.5% ~ +26.3%)
- 2020 COVID (5 trades, +64.7% ~ +102.3%)
- 2022 升息熊 (3 trades, +16.3% ~ +21.3%)
- 2025 川普關稅 (2 trades visible, +122% ~ +124%)

## Strategy Positioning（重要）

H085 = **Tier B 急速 panic specialist**，不是通用「逢低買」工具：

| 涵蓋 | 不涵蓋 |
|---|---|
| Tier B 大型回檔（COVID 式、關稅式急殺） | **Tier A 結構熊主底**（緩跌型，2022-10 沒命中） |
| 含 panic VIX 急飆事件 | **大多數 Tier C 標準回檔**（2021-05 / 2024-08 / 2026-03 都沒命中）|
| 觸發要求「全市場齊聚 panic」 | Tier C-sub 急殺（VIX 飆但其他指標未動） |

歷史 8 個 H084 事件中命中 4 個（50%）。Tier C 進場留待 H088 衍生研究。

## Verdict 限定條件

✅ **僅 `comp_z` 變體（IQR 標準化）**
❌ Rejected: `comp_pct` 變體（rolling percentile rank 對歷史極值敏感、OOS 觸發失靈）

✅ 持有 ≥ 120d、推薦 250d
✅ V1 倉位管理（cooldown 5d, max_open 5）
✅ Threshold = 3.97（IS top 10% fitted）

## Limitations

1. **OOS 樣本只 1 個 cluster**（2025 關稅）— 真實穩健性需更多 fear 事件
2. **2022-10 Tier A 主底沒命中** — 緩跌型結構熊（VIX 沒急飆）不在覆蓋範圍
3. **觸發頻率低** — 平均約 3-4 年一次重大 fear 事件
4. **未測 0050 以外標的**
5. **資料窗短**（VIX_pct 從 2017-08 起算，pre-2018 無法驗證）

## Derived Hypotheses

- **H088（已 spawn proposal）** — Tier C 標準回檔進場訊號
- H089（候選）— Composite slope as trigger
- H091（候選）— Mixed-frequency vote
- H092（候選, Phase 2 衍生）— Position size scaling by score

## Files

- `proposal.md` — 原始假設文件
- `tasks.md` — Phase 1 + Phase 2 + Phase 2.5 任務追蹤
- `explore.py` — Phase 1 distribution 分析
- `backtest.py` — Phase 2 walk-forward 回測（包含 comp_pct/comp_z grid sweep）
- `backtest_v2.py` — Phase 2.5 倉位管理變體（B0 / V1 / V2 比較）
- `spec.md` — 策略執行規格
- `results/` — distribution.md / backtest.md / 圖表 / CSV
