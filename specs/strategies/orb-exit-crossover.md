# 出場策略交叉實驗

## 背景與動機

現有兩套成熟策略：
- **ORBLong**：寬進場窗口（09:30–11:00），固定 % SL + OR 寬度 TP + trailing stop
- **EstHL**：嚴格早盤進場（08:58–09:05），EmaHL SL + SatZone 兩段式出場 + Dow Trail Stop

兩者比較發現：
- EstHL 早年（2021–2023）明顯較優（2021: +404 vs -498）
- ORBLong 近年（2024–2026）全面碾壓（2025: +1,823 vs +634）
- 差異可能來自**出場機制**，而非進場機制

本實驗嘗試交叉組合，驗證出場策略的貢獻是否是主要差異來源。

---

## 實驗方向

### 方向 A：EstHL 進場 × ORBLong 出場

**進場**：維持 EstHL 的嚴格條件
- 時間窗口：08:58–09:05
- 30m 20MA 方向濾網
- BigCost max(2日) + ½ SL 閾值
- OR 寬度 0.5~1.5× RollingOR

**出場**：改用 ORBLong 的出場機制
- SL = sl_pct × entry（固定百分比，0.4%）
- TP = entry + tp_or_multiplier × max(OR寬度, or_min_width)（OR 寬度倍數，1.5×）
- Trailing stop：09:45 後啟動，追蹤最高收盤回撤 sl_pct
- 強制出場：13:30

**預期觀察**：
- 若 EstHL 的問題在於出場太早（SatZone Phase 2 提前離場），換成 TP 型出場應能讓獲利跑更遠
- 2024–2025 ORBLong 強勢期，是否能沿用到 EstHL 的早盤進場？

---

### 方向 B：ORBLong 進場 × EstHL 出場

**進場**：維持 ORBLong 的條件
- 時間窗口：09:30–11:00
- 突破 OR 高點（08:45–09:30）
- Close > 10 日 TrendMA（趨勢方向）

**出場**：改用 EstHL 的出場機制
- SL = 0.25 × EmaHL
- SatZone 兩段式：High ≥ SatZoneUpper → 觸及；觸及後 Close < 5MA → 出場
- Dow Theory trailing stop（9:45 後，5根 pivot，2根確認）
- 強制出場：13:30

**預期觀察**：
- ORBLong 的出場常在強勢行情中過早觸及 TP，EstHL 出場是否能讓獲利跑得更長？
- 2021–2023 ORBLong 表現平庸（PF 0.80–1.26），換出場後是否能改善？

---

## 實作注意事項

### 資料需求
方向 A 和 B 都需要 `load_data_for_orb_est_hl()` 提供的欄位：
- `EmaHL`, `SatZoneUpper`, `SatZoneLower`（EstHL 出場用）
- `MA30_20`, `Close30`, `BigCost1`, `BigCost2`（EstHL 進場用）
- `ORWidth`, `RollingOR`（OR 寬度濾網）
- `TrendMA`（ORBLong 進場用，需從 `load_data_with_night_ma` 合併）

最簡單的做法：在 `load_data_for_orb_est_hl()` 額外加入 TrendMA 欄位，
或建立一個合併版的 loader。

### 新策略類別（待實作）
```
src/strategies/orb_esthl_entry_orb_exit.py   # 方向 A
src/strategies/orb_orb_entry_esthl_exit.py   # 方向 B
```

或統一在一個檔案：
```
src/strategies/orb_crossover.py
```

---

## 評估標準

以下指標與現有兩策略對比：

| 指標 | ORBLong | EstHL | 方向 A | 方向 B |
|------|---------|-------|--------|--------|
| 2021 累計 | -498 | +404 | ? | ? |
| 2022 累計 | +228 | +445 | ? | ? |
| 2023 累計 | +302 | +317 | ? | ? |
| 2024 累計 | +1,037 | +774 | ? | ? |
| 2025 累計 | +1,823 | +634 | ? | ? |
| 2026 累計 | +1,723 | +283 | ? | ? |
| 全期 PF | — | — | ? | ? |
| 年度穩定性 | 差（2021） | 佳 | ? | ? |

**成功標準**：
- 方向 A：能保留 EstHL 早年優勢（2021–2023 > EstHL），同時改善近年表現
- 方向 B：能改善 ORBLong 早年弱勢（2021 不虧損），且不犧牲近年表現

---

## 優先順序

先實作**方向 B**（ORBLong 進場 × EstHL 出場）：
- ORBLong 筆數較多（平均 50–75 筆/年），統計意義更強
- 2021 的 -498 是最大痛點，如能修復，整體改善最顯著
