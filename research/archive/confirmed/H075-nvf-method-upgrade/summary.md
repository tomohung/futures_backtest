# Archive: NVF Method Upgrade

## Status
Confirmed（Phase 2 已完成，production 程式碼已升級）

## Summary
H073 揭露實盤 NVF 用 SMA20 + 0.85 fixed，與 H066 評估時 EMA20 + median split 的方法不一致，導致實盤 NVF 效果只有評估值的 1/4。本研究驗證 EMA20 + expanding median 為最佳方法（HIGH PF +30%、Walk-forward 6/6 完美一致、max streak 9→7、worst streak P&L 改善 28.6%），並升級 `src/analysis/key_prices.py`。意外發現現行 production NVF 在 EstHL 上把 max_streak 從 baseline 6 推到 9（**比完全不過濾還糟**），新方法修正此問題。

## Key Evidence

### Aggregate diff（HIGH vs LOW PF）
| Method | EstHL | Reversal |
|--------|-------|----------|
| SMA + 0.85 (舊 prod) | +25.9% | +25.1% |
| **EMA + exp_med (新 prod)** | **+93.9%** | **+74.1%** |

### Walk-forward 年度一致性（HIGH PF > baseline）
| Method | EstHL | Reversal |
|--------|-------|----------|
| SMA + 0.85 | 5/6 | 3/6 |
| **EMA + exp_med** | **6/6** | 4/6 |

### 連敗結構（max_streak）
| Method | EstHL | Reversal |
|--------|-------|----------|
| NO_NVF baseline | 6 | 10 |
| SMA + 0.85 (舊) | **9** ⚠ | 7 |
| **EMA + exp_med (新)** | **7** | 7 |

舊 NVF 在 EstHL 比不用 NVF 還差（max_streak 6 → 9）。新 NVF 修正：9 → 7，且 worst streak P&L 從 -378 → -270（改善 28.6%）。

### Trajectory 穩定性
EMA expanding median 過去 4 年都在 0.92–0.94，月度變動 ±0.005。即便 2026 Q1 vol 暴漲（夜盤 raw range 翻倍），threshold 只動 +0.004。

### 對 H072 sub-cell 的影響
新方法**自動修復** Reversal Wed (-0.12 → +0.99) 與 Thu (-0.17 → +0.08) 的 OOS drift。但 **EstHL × Tue × NVF 是結構性失效**，無論用哪種方法 OOS Δ 都 ≈ -1.2，需另行 patch（H072 originally proposed）。

## Why Confirmed
1. PF / 連敗 / Walk-forward / 自適應性全面壓倒性勝出
2. Trajectory 穩定，無 step jump 風險
3. 實作簡單，0 風險（與 H066 真實評估方法一致）
4. **Phase 2 已實作並通過 smoke test**：production code 升級 + 顯示字串更新

## Production 升級內容
- `src/analysis/key_prices.py:_compute_night_vol_filter`：
  - EMA20 取代 SMA20
  - expanding median 取代 0.85 fixed
  - warmup < 60 nights fallback 到 0.93
  - 回傳欄位變更：`sma20` → `ema20`，新增 `threshold`, `method`
- 顯示字串同步更新（briefing 內 `SMA20 / 0.85` → `EMA20 / threshold`）

## Documentation Updates
- ✅ H066 archive summary 加註本升級
- ✅ H067 archive summary 加註本升級
- ✅ S001 spec 增加 NVF filter 描述 + 參數
- ✅ S002 spec 更新 NVF 方法描述 + 參數

## Derived Hypotheses
- **H078（confirmed, 2026-04-21）**：EstHL Tue NVF bypass patch — 5/6 年勝、total +24%、max_streak 僅 +1（容許範圍內）；但 worst streak 加深 28% 為已知 caveat。已實裝 production。詳見 `research/archive/confirmed/H078-esthl-tue-nvf-bypass/`。
- **H076 候選（低優先 audit）**：H066 summary.md 「EMA/SMA r=0.985 結果一致」說法被本研究進一步反駁——HIGH PF 差距 2.07 vs 2.68（+30%）。需做更廣的 H066 文檔/程式一致性 audit。
- **H077 候選（低優先 / 已 mooted）**：「為何 SMA + 0.85 把 max_streak 9 → baseline 6 推到 9」——升級後此問題消失，無需獨立研究。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Visualisations：results/h075_t1_trajectory.png, h075_t3_walkforward.png, h075_t4_streaks.png
- Explore script：explore.py
- Production code change：`src/analysis/key_prices.py:_compute_night_vol_filter`
