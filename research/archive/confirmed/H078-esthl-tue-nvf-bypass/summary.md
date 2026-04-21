# Archive: EstHL Tue NVF Bypass Patch

## Status
Confirmed（Phase 2 已完成，production 顯示邏輯已升級）

## Summary
H072+H075 雙重證實 EstHL × Tue × NVF 是結構性失效（OOS Δ -1.22，無論 SMA 或 EMA 方法）。本研究確認 Tue baseline 在 OOS 期間 PF 2.14 健康，套上 NVF 後降到 0.92。實裝 Tue NVF bypass 後，live-eligible（Mon-Wed）total P&L +24%（+789 點）、5/6 年正向、max_streak 僅 +1（容許範圍內）。caveat：worst streak P&L 加深 28%、max DD 加深 28%。Reversal Tue × NVF 行為相反（OOS Δ +0.77），不需 bypass。

## Key Evidence

### EstHL Tue baseline vs NVF（IS / OOS 切割）
| Period | base PF (N) | NVF PF (N) | Δ |
|--------|-------------|------------|---|
| IS (2021-23) | 1.21 (33) | **1.51** (13) | +0.30 |
| OOS (2024-26) | **2.14** (22) | 0.92 (9) | **-1.22** |

NVF 在 IS 期間實際上有效，OOS 才失敗 → 規則 drift 是真實的。

### 逐年 baseline > NVF
| Year | base_PF | NVF_PF | 勝者 |
|------|---------|--------|------|
| 2021 | 0.92 | 0.70 | base |
| 2022 | 1.51 | 1.45 | base |
| 2023 | 1.32 | **3.73** | NVF |
| 2024 | 0.78 | **0.00** | base |
| 2025 | 1.54 | **0.62** | base |

**4/5 valid years baseline 勝**

### Live-eligible（Mon-Wed）對比
| Config | N | PF | total | max_streak | worst_pnl | max_dd |
|--------|---|----|----|------------|-----------|--------|
| **A: full NVF (current)** | 56 | 4.65 | +3,322 | 3 | -142 | -119 |
| **B: Tue bypass** | 89 | 3.67 | **+4,111** | **4** | **-216** | **-216** |
| Δ | +33 | -0.98 | **+789 (+24%)** | +1 | -74 | -97 |

**5/6 年 B 勝**（唯 2023 -67），近 3 年（2024-26）合計 +787 點增益。

### 對照：Reversal Tue × NVF
| 策略 | OOS NVF Δ | 結論 |
|------|----------|------|
| EstHL Tue | -1.22 | bypass |
| Reversal Tue | **+0.77** | 保留 NVF |

兩策略對 Tue 高夜盤波動行為完全相反——本研究只動 EstHL。

## Why Confirmed
1. IS/OOS 切割暴露真實的時序性失效
2. 4/5 valid years baseline 勝 NVF
3. 5/6 年 B configuration 勝
4. max_streak +1 在 invalidation 容許範圍 (< 2)
5. **Phase 2 已實裝**：smoke test 在當日（2026-04-21 Tue）正確顯示 EstHL bypass + Reversal 維持 NVF gate

## Caveats（重要實盤警示）
- worst streak P&L 從 -142 加深到 -216（**+28% 加深**）
- max DD 從 -119 加深到 -216（**+28% 加深**）
- 接受 patch = 接受用「連敗 +1 + 損失加深 28%」換「total +24%」
- 已將此 trade-off 寫入 S001 spec.md

## Production 升級內容
- `src/analysis/key_prices.py` 加入 `today_wd == 1` 分支
- `strategies/live/S001-esthl/spec.md` 增加 Tue bypass 規則 + 參數表

## Documentation Updates
- ✅ S001 spec.md 加入 Tue NVF bypass 描述
- ✅ H075 archive summary 加註 H078 完成

## Derived Hypotheses
- **H079 候選（低優先 / 已知未解）**：「為何 EstHL Tue 在 OOS 期間 NVF 反向作用而 IS 期間正向」——本研究確認現象，根因仍未解。可能與 2024 起國際事件主導的高夜盤波動下 EstHL ORB 邏輯失效有關。
- **H080 候選（補強）**：探索其他 weekday-aware NVF 調整（如 Tue 改用更寬鬆 threshold 而非完全 bypass）。或許 bypass 不是唯一最佳解。
- **H074 候選（從 H071 留下，仍未動）**：Reversal Tue 加碼研究。本研究進一步確認 Reversal Tue 是 NVF 系統最受惠 cell，加碼方向證據更強。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Visualisation：results/h078_overview.png
- Explore script：explore.py
- Production code change：`src/analysis/key_prices.py` (today_wd == 1 branch)
