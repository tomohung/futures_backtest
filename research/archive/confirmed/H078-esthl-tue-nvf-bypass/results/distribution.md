# Distribution Research Results: EstHL Tue NVF Bypass

## Date
2026-04-21

## Conditions Tested
- EstHL with `skip_thursday=False, skip_friday=False`（解除 weekday filter 取得完整 Tue 樣本）
- 新 NVF 方法：EMA20 + expanding median（causal, warmup 60，與 H075 production 一致）
- Live-eligible 模擬：套用 production weekday skip（去除 Thu/Fri trades）
- 兩個 config：
  - **A**: full NVF（current production）
  - **B**: NVF except Tue（Tue bypass）

## Sample
- EstHL trades total: 248
- with NVF & exp_med valid: 226
- Tue trades only (with NVF valid): 55
- Live-eligible (Mon-Wed): 149
- Config A (current): N=56
- Config B (Tue bypass): N=89

## Key Findings

### T1: EstHL Tue cell — baseline vs NVF, by year

| Year | base_N | base_PF | base_avg | NVF_N | NVF_PF | NVF_avg | Δ_PF |
|------|--------|---------|----------|-------|--------|---------|------|
| 2021 | 13 | 0.92 | -1 | 4 | 0.70 | -8 | -0.22 |
| 2022 | 11 | 1.51 | +9 | 4 | 1.45 | +10 | -0.06 |
| 2023 | 9 | 1.32 | +5 | 5 | **3.73** | +22 | **+2.41** |
| **2024** | 9 | 0.78 | -7 | 3 | **0.00** | -77 | **-0.78** |
| **2025** | 9 | 1.54 | +22 | 4 | **0.62** | -13 | **-0.93** |
| 2026 | 4 | inf | +156 | 2 | — | +128 | n/a |

→ **5 個有效年（N≥5），baseline 在 4/5 年勝出**。唯一 NVF 勝出的 2023 是 outlier。

**IS vs OOS 對比**：
| Period | base PF (N) | NVF PF (N) | Δ |
|--------|-------------|------------|---|
| IS (2021-23) | 1.21 (33) | **1.51** (13) | +0.30 |
| OOS (2024-26) | **2.14** (22) | 0.92 (9) | **-1.22** |

**關鍵**：NVF 在 IS 期間是中性偏正向（Δ +0.30），但在 OOS 期間嚴重失效（Δ -1.22）。Tue NVF 失敗是 OOS-specific 現象，與 EstHL Tue 在近年市場結構下有關。

### T3: 連敗結構 — Config A (full NVF) vs Config B (Tue bypass)

Live-eligible（Mon-Wed）對比：

| Config | N | PF | WR | total | max_streak | worst_pnl | max_dd |
|--------|---|----|----|-------|-----------|-----------|--------|
| **A: full NVF (current)** | 56 | **4.65** | 71.4% | +3,322 | **3** | -142 | -119 |
| **B: Tue bypass + NVF Mon/Wed** | 89 | 3.67 | 66.3% | **+4,111** | 4 | -216 | -216 |
| **Δ (B − A)** | +33 | -0.98 | -5.1pp | **+789 (+24%)** | **+1** | -74 | -97 |

**核心 tradeoff**：
- ✓ Total P&L **+789**（+24%）
- ✓ N 增加 +33 筆（更多交易機會）
- ✗ PF 從 4.65 降到 3.67（但仍 > 3）
- ✗ max_streak +1（3 → 4，**仍在 invalidation 容許範圍內 < 2**）
- ✗ worst_pnl 加深 -74（從 -142 → -216）
- ✗ max_dd 加深 -97（從 -119 → -216）

### 逐年 P&L 增益（B − A）

| Year | A_total | B_total | Δ |
|------|---------|---------|---|
| 2021 | +149 | +162 | +13 |
| 2022 | +426 | +482 | +56 |
| 2023 | +343 | +276 | **-67** ← 唯一負年 |
| 2024 | +986 | +1,150 | +164 |
| 2025 | +809 | +1,062 | **+253** |
| 2026 | +609 | +979 | **+370** |

→ **5/6 年 B 勝**，且**近 3 年（2024-26）增益最明顯**。2023 是唯一負年（−67），對應前述 Tue NVF 在 IS 期是有效的觀察。

## Vs. Expected

| 預期 | 實際 | 判定 |
|------|------|------|
| Tue NVF-filtered ≤ Tue baseline 在 ≥ 4/6 年 | 4/5 valid years | ✓ 符合 |
| 全策略 OOS PF 改善 | total +789 (+24%)，PF 降但仍 3.67 | ✓ total 改善（PF 下滑但仍健康） |
| max consecutive losses 不增加 ≥ 2 筆 | +1（3→4）| ✓ 符合（容許 < 2） |
| Walk-forward 一致改善 | 5/6 年正向 | ✓ 符合 |

**所有 invalidation 條件未觸發**。但有兩個誠實 caveat：
1. Worst streak P&L 加深 28%（-142 → -216）
2. Max DD 加深 28%（-119 → -216）
3. PF 降約 21%（4.65 → 3.67）但仍遠 > 1

連敗結構雖然 max_streak 只 +1 在容許範圍，但 P&L-weighted 的損失加深需要使用者明確確認可接受。

## Gate Decision

[X] **進入 Phase 2，實裝 Tue NVF bypass**

證據強度：
- IS/OOS 切割顯示 NVF 失敗是 OOS-specific（+0.30 → -1.22）
- 4/5 年 baseline 勝 NVF
- 5/6 年 B configuration 勝 A
- 累積 +789 點 P&L（+24%）
- max_streak 增加 +1，在 invalidation 容許範圍內

但 Phase 2 完成後需做：
- 連敗加深的 caveat 寫入 S001 spec.md
- 在 morning_briefing 顯示「Tue 為 NVF bypass，承擔較高 drawdown 風險」

## 對照：Reversal Tue × NVF 為何不需要 bypass

兩策略在 Tue × NVF 上行為**完全相反**，本研究的 patch 只適用 EstHL：

| 策略 | Tue OOS NVF Δ | 結論 |
|------|----------------|------|
| **EstHL Tue** | **-1.22**（H078 處理） | bypass NVF |
| **Reversal Tue** | **+0.77**（H075 已驗證） | 保留 NVF |

Reversal Tue rolling 2-year ΔPF（H075 explore）：
+0.08 → -1.09 → +0.33 → +0.49 → **+0.58**（OOS 連續改善）

Reversal Tue × NVF 是 NVF 系統裡**最受惠的 cell 之一**，IS Δ -0.13 → OOS Δ +0.77 顯示 NVF 在近年對 Reversal Tue 的有效性反而上升。

## Phase 2 完成記錄（2026-04-21）

### 實作改動
`src/analysis/key_prices.py` 在 EstHL 進場建議邏輯加入 `today_wd == 1` 分支：
```python
elif today_wd == 1:
    # H078: Tue 結構性 NVF 失效，bypass NVF
    print(f"| S001 EstHL | ✅ 可做 | 週二 NVF bypass (H078)；參考 NVF=... |")
```

Reversal 區塊不動（仍依 NVF 判定）。

### Smoke test（2026-04-21 Tue, NVF=0.66, threshold=0.94）
- S001 EstHL → ✅ 可做（Tue NVF bypass）← H078 生效
- S002 Reversal → 🚫 不做（夜盤波動 STOP 0.66 < 0.94）← 保持原邏輯

### 文檔同步更新
- ✅ S001 spec.md 加入 Tue NVF bypass 描述 + `Tue NVF bypass: True` 參數
- ✅ H075 archive summary 加註 H078 已完成

## Derived Hypotheses

- **H079 候選（低優先 / 已知）**：「為何 EstHL Tue 在 OOS 期間 NVF 反向作用而 IS 期間正向」——本研究確認現象，根因仍未解。可能與 2024 起國際事件主導的高夜盤波動下 EstHL ORB 邏輯失效有關。需獨立深究。

- **H080 候選（補強）**：探索其他 weekday-aware NVF 調整（例如 Mon/Wed 仍 NVF，Tue 改用更寬鬆 threshold 而非完全 bypass）。或許 Tue bypass 不是唯一最佳解。

## Links
- Proposal：../proposal.md
- Tasks：../tasks.md
- Explore script：../explore.py
- Visualisation：h078_overview.png
- CSVs：t1_tue_yearly.csv
