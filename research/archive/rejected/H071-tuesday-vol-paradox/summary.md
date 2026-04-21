# Archive: Tuesday Volatility Paradox

## Status
Rejected

## Summary
原假說「Tue 振幅最大但策略績效卻較差，可能來自雙向甩動或趨勢逆向」未獲支持。歷史上 Tue 對 Reversal/Exhaustion 是**最佳**交易日（PF 排名 5/5），對 EstHL 是中段（3/5）；intraday efficiency ratio 顯示 Tue 是**更趨勢**的一天（+17% vs 其他），與雙向甩動假說相反。但研究副發現極具價值——套用 NVF 後 EstHL × Tue × 2024–2025 出現負期望值（PF 0.00 / 0.29），觸發 H072 系統性重審 NVF。

## Key Evidence
- **Weekday × Strategy PF**（2021–2026 raw, 無 NVF）：
  - EstHL Tue 1.74 (rank 3/5), Reversal Tue 2.16 (5/5 best), Exhaustion Tue 1.56 (5/5 best)
- **Intraday efficiency**：Tue 0.0749 vs others 0.0641（+16.8%，更趨勢非更甩動）
- **MAE/MFE**：EstHL Tue +20%（唯一反轉壓力上升），Reversal/Exhaustion Tue 反而 −25~40%
- **TrendMA 切片不適用**（EstHL long_only、Exhaustion 結構性逆勢）
- **2026 Q1（at 2026-04-21）**：三策略 Tue 均回升（EstHL 4/4 全勝、Reversal PF 8.11），N 偏小但證實「2024 異常→2025 過渡→2026 回常態」
- **NVF 副發現**：EstHL × Tue × NVF 2024 PF=0.00（N=3）, 2025 PF=0.29（N=6）；其他天 NVF 仍正向

## Why Rejected
1. 三個原始預期（PF 落後 40%、MAE/MFE +15%、H/L 時間更分散）**全部未獲支持**
2. Tue 對 Reversal/Exhaustion 反而是最強日，與假說方向相反
3. EstHL Tue 邊緣偏弱屬統計噪音（PF 1.74 仍獲利、且僅低於 Mon/Wed 約 30–40%）
4. 使用者「Tue 不好」的主觀印象來源是 NVF 過濾後的近 2 年表現，與原假說的市場結構性解釋無關

## Derived Hypotheses
- **H072**（已開）：NVF 效果 by weekday × strategy × year 重審。檢查 H066/H067 confirm 後的 NVF 穩定性，特別是 sub-cell（如 EstHL × Tue × 2024–2025）是否還持續失效。
- 暫擱：H074 候選「Reversal Tue 為何特別好」（PF 2.16，可考慮 Tue 加碼，但短期不動實盤）

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Visualisation：results/h071_overview.png
- Explore script：explore.py
