# Backtest Results: 同向第二次 L2 拉回續攻

## Date
2026-06-24

## Parameters
- 偵測：**causal** `services/l2_pullback.detect_day`（與 explore 同源，無前視；H120 zigzag_legs 版有前視，不沿用）
- 進場：同方向序數 ≥2（2nd+）、站回 5MA reclaim、**entry∈[09:30,11:30]**
- 停損：`stop = pb_ext − alpha×(pb_ext − anchor)`；**alpha=1.0**（=錨點，IS 最佳，見敏感度）
- 目標：L3 / L4 / L5 / trail（達 L3 後 trail_frac×L3d 追蹤）
- 成本：每筆 round-trip **3pt**；績效用損益%（CLAUDE.md），Sharpe = mean(損益%)/sd(損益%) 每筆基準
- IS < 2025-01-01；OOS ≥ 2025-01-01
- 樣本：2nd+∈[09:30,11:30] **N=120**（IS 80 / OOS 40）；對照 1st∈窗 N=966

## Results

### 核心：序數從 break-even 母體切出正 EV 子集（09:30–11:30, alpha=1.0, cost=3）
| 組別 | target | N | win% | EVpt | tot% | Sharpe | maxDD% | maxLossStreak | avgR |
|---|---|---|---|---|---|---|---|---|---|
| **2nd+** | L3 | 120 | 65.0 | 9.9 | **5.1** | 0.109 | **−3.2** | **3** | 0.06 |
| 1st（對照）| L3 | 966 | 63.9 | 0.7 | 0.5 | 0.001 | −10.9 | 9 | 0.01 |
| **2nd+** | L4 | 120 | 52.5 | 23.4 | **11.2** | 0.164 | **−3.1** | 7 | 0.17 |
| 1st（對照）| L4 | 966 | 50.5 | 0.3 | −1.0 | −0.002 | −16.4 | 10 | 0.02 |

→ 1st（=H120 母體）淨值 ~0、Sharpe ~0、maxDD −11~−16%；**2nd+ 同窗同規則 tot 5–11%、Sharpe 0.11–0.16、
maxDD 僅 −3%、連敗 3–7**。序數條件確實切出正 EV 子集，且**回撤/連敗大幅改善**（符合 feedback_filter_eval_includes_streaks）。

### 目標模式（IS 2nd+, alpha=1.0）— 第二次能否瞄更遠
| target | win% | EVpt | tot% | Sharpe | avgR |
|---|---|---|---|---|---|
| L3 | 66.2 | 10.3 | 4.6 | 0.174 | 0.09 |
| L4 | 52.5 | 14.7 | 6.8 | 0.167 | 0.17 |
| L5 | 48.8 | 13.3 | 5.9 | 0.127 | 0.15 |
| **trail 0.5** | 50.0 | 25.5 | **11.7** | **0.231** | 0.24 |
| trail 1.0 | 48.8 | 32.4 | 14.7 | 0.213 | 0.33 |

→ 「瞄更遠」論點成立：L4/trail 的 EV、avgR 為 L3 的 2–3×。trail 0.5 IS Sharpe 最佳。

### ★ IS vs OOS（每個 target 都報 OOS，避免單一選擇誤判）
| target | IS Sharpe | IS tot% | OOS Sharpe | OOS EVpt | OOS tot% |
|---|---|---|---|---|---|
| L3 | 0.174 | 4.6 | **0.028** | 9.2 | 0.6 |
| L4 | 0.167 | 6.8 | **0.164** | 40.7 | 4.4 |
| L5 | 0.127 | 5.9 | **0.202** | 55.2 | 6.2 |
| trail 0.5 | **0.231** | 11.7 | 0.154 | 49.6 | 4.6 |
| trail 1.0 | 0.213 | 14.7 | 0.174 | 47.9 | 5.4 |

→ **只有最保守的 L3 在 OOS 崩掉（Sharpe 0.028）；所有「瞄更遠」目標（L4/L5/trail）OOS Sharpe 0.15–0.20、
與 IS 一致或更強。** 假設的核心（2nd+ 可瞄更遠續攻）OOS 站得住。
⚠ 但 OOS≡高波 regime（memory `project_oos_equals_highvol_regime`），深目標 OOS 偏強部分與「高波利於深 reach」confounded。

## Walk-Forward Summary
逐年（2nd+∈[09:30,11:30], alpha=1.0, cost=3）：
- **target=L4：2021–2026 每一年 EV 皆正**（+32/+10.8/+14.1/+9.6/+15.1/+54.5pt），無虧損年。
- **target=trail 0.5：每年亦皆正**（+82/+3.6/+9.6/+23.9/+14.2/+68.6pt）。
- 對比：L3 目標下 2025 為 −15.5pt（唯一虧損年）→ 2025 的弱僅出現在保守 L3，深目標不受影響。
- 每年 N 僅 14–28，逐年 Sharpe 噪音大，但**方向一致為正**是穩健訊號。

## Parameter Sensitivity
- **停損 alpha**：Sharpe 隨 alpha 單調上升，**alpha=1.0（錨點，最寬）最佳**（win 66%, maxLossStreak 3）；
  alpha=0（緊停）win 36%、連敗 7。→ 2nd+ 續攻需要寬停損容忍 re-test（呼應 H128 直覺）。穩健、非單點尖峰。
- **成本**：target=L4 在 cost=0→6pt，tot 8.2%→5.4%、Sharpe 0.20→0.13，**6pt 仍穩健正**。
- **cutoff**：09:30–11:30（Sharpe 0.164）> 09:30–12:00（0.117）> 全日（0.047）。**11:30 cutoff 確認**；
  延伸到 08:45 無增益（<09:30 幾乎無 2nd+）。

## Verdict
[x] Confirmed（含 caveats，2026-06-24 使用者裁決）　[ ] Rejected　[ ] Inconclusive
> 證據傾向 **Confirmed（含 caveats）**：
> - 核心假設成立：2nd+ 從 break-even 母體切出正 EV 子集，回撤/連敗顯著改善；「瞄更遠」成立。
> - 參數優化（alpha, target）後 OOS 驗證通過（L4/L5/trail OOS Sharpe ≈ IS）；6 年每年 EV 正。
> - **Caveats**：(1) N 薄（120/OOS 40/每年 14–28）；(2) 每筆 Sharpe 屬「真實但溫和」(0.15–0.23)；
>   (3) 深目標 OOS 偏強與高波 regime confounded；(4) alpha=1.0 寬停=單筆風險點數大（高波年 EV 大、pct 持平）。

## Derived Hypotheses
- **H128**：alpha=1.0（錨點寬停）最佳 → 系統化測「2nd+ 專屬更寬停損 / 停損放在第一次極值外」的賠率曲線。
- **H129**：次數 dose-response（3rd>2nd？）；本回測未細分序數，逐次 EV 遞增則可加碼第 3+ 次。
- **部署形態**：2nd+ 訊號可作 chart-ui 主圖指標 + 清單（重用 detect_day），盤中即時標記第二次同向 reclaim。
