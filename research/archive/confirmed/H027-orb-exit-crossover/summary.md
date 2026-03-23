# Archive: 出場策略交叉實驗

## Status
Confirmed

## Summary
交叉組合 EstHL 與 ORBLong 的進場/出場機制。方向 A（EstHL 進場 × ORBLong 出場）成功，tp=3.0, entry_end=09:15，總損益 +4,221 pts，六年均無虧損。方向 B（ORBLong 進場 × EstHL 出場）失敗，SatZone 不適用於晚進場。

## Key Evidence
- 方向 A：+4,221 pts，六年均無虧損，穩定性最高
- 方向 A 最佳參數：tp_or_multiplier=3.0, entry_end=09:15
- 方向 B：失敗，SatZone 出場不適用於 ORBLong 的晚進場時間
- 方向 A 定位：穩定性與絕對報酬之間，適合保守配置

## Why Confirmed
驗證了出場機制是兩策略表現差異的主因。方向 A 提供了一個額外的策略選項，適合風險偏好較低的配置。

## Derived Hypotheses
- 無直接衍生（結論為策略選擇建議）

## Links
- Proposal：research/active/H027-orb-exit-crossover/proposal.md
- Spec：research/active/H027-orb-exit-crossover/spec.md
- Tasks：research/active/H027-orb-exit-crossover/tasks.md
