"""
H093 衍生：守高位日（pos>=0.75 @10:30）的進場時機優化
  原始：10:30 直接進、抱到 13:45
  新法：10:30 之後，先出現 1分K %B<0（跌破 BB(20,2) 下軌），arm 後第一根「收盤>5MA」進場，13:45 出場

比較期望值（mean pnl%）、勝率、PF、訊號命中率、IS/OOS。
價格用 adj_close（intraday adjustment 為常數，不影響）。net 成本 3 點。
"""
import duckdb
import numpy as np
import pandas as pd

DB = "data/futures.duckdb"
COST_PTS = 3.0
IS_END = pd.Timestamp("2024-12-31")
POS_THR = 0.75
BB_N, BB_K, MA_N = 20, 2.0, 5

# 抓日盤 1 分K
SQL = """
SELECT timestamp::DATE AS d, timestamp::TIME AS t, adj_close
FROM ohlcv_1m
WHERE symbol='TX' AND timestamp::TIME BETWEEN TIME '08:45' AND TIME '13:45'
ORDER BY d, t
"""
with duckdb.connect(DB, read_only=True) as c:
    bars = c.execute(SQL).df()
bars["d"] = pd.to_datetime(bars["d"])

records = []
for d, g in bars.groupby("d"):
    g = g.reset_index(drop=True)
    if len(g) < 250:
        continue
    close = g["adj_close"].astype(float)
    t = g["t"]
    # 早盤區間 08:45~10:30 → pos_1030
    morn = g[t <= pd.to_datetime("10:30").time()]
    if len(morn) == 0:
        continue
    m_hi, m_lo = morn["adj_close"].max(), morn["adj_close"].min()
    # 用 1分K close 的區間（與進場價同口徑）
    if m_hi <= m_lo:
        continue
    close_1030 = morn["adj_close"].iloc[-1]
    pos = (close_1030 - m_lo) / (m_hi - m_lo)
    close_1345 = close.iloc[-1]

    # 指標（整段日盤滾動，10:30 時已暖機）
    ma = close.rolling(MA_N).mean()
    mid = close.rolling(BB_N).mean()
    sd = close.rolling(BB_N).std(ddof=0)
    lower = mid - BB_K * sd
    upper = mid + BB_K * sd
    pctb = (close - lower) / (upper - lower)

    # 10:30 之後掃描進場訊號
    after = g.index[t > pd.to_datetime("10:30").time()]
    after = [i for i in after if i < len(g) - 1]  # 留一根給出場(其實 13:45 收盤出場, 末根也可)
    armed = False
    entry_i = None
    for i in g.index:
        if t.iloc[i] <= pd.to_datetime("10:30").time():
            continue
        if pd.isna(pctb.iloc[i]) or pd.isna(ma.iloc[i]):
            continue
        if pctb.iloc[i] < 0:
            armed = True
        if armed and close.iloc[i] > ma.iloc[i]:
            entry_i = i
            break

    rec = dict(d=d, pos=pos, close_1030=close_1030, close_1345=close_1345)
    if entry_i is not None:
        ep = close.iloc[entry_i]
        rec["signal"] = True
        rec["entry_time"] = t.iloc[entry_i]
        rec["entry_price"] = ep
        rec["pnl_sig_net"] = (close_1345 - ep) / ep * 100 - COST_PTS / ep * 100
    else:
        rec["signal"] = False
        rec["pnl_sig_net"] = np.nan
    # 對照：同日 10:30 直接進
    rec["pnl_1030_net"] = (close_1345 - close_1030) / close_1030 * 100 - COST_PTS / close_1030 * 100
    records.append(rec)

df = pd.DataFrame(records)
qual = df[df["pos"] >= POS_THR].copy()
N = len(qual)
sig = qual[qual["signal"]].copy()
print(f"=== 合格日 pos>=0.75: N={N} ===")
print(f"出現 %B<0→站上5MA 進場訊號的日子: {len(sig)} ({len(sig)/N:.1%})")
if len(sig):
    print(f"進場時間分佈: 中位={sig['entry_time'].astype(str).sort_values().iloc[len(sig)//2]} "
          f"最早={sig['entry_time'].min()} 最晚={sig['entry_time'].max()}")
print()


def stat(s, col, label):
    r = s[col].dropna().values
    n = len(r)
    if n == 0:
        print(f"  {label}: N=0"); return
    eq = np.cumsum(r); mdd = (np.maximum.accumulate(eq) - eq).max()
    gw, gl = r[r > 0].sum(), -r[r < 0].sum()
    sh = r.mean()/r.std(ddof=1) if r.std(ddof=1) > 0 else np.nan
    print(f"  {label}: N={n:4d} 勝率={(r>0).mean():.1%} 期望值={r.mean():+.4f}% "
          f"中位={np.median(r):+.3f}% 總={r.sum():+.1f}% Sharpe={sh:.3f} MDD={mdd:.1f}% "
          f"PF={gw/gl if gl>0 else np.inf:.2f}")


print("=== 全期比較 ===")
print("[A] 所有合格日，10:30 直接進→13:45（原始策略）")
stat(qual, "pnl_1030_net", "全合格日")
print("[B] 僅有訊號的日子，等回檔(%B<0)+站上5MA 進→13:45（新策略）")
stat(sig, "pnl_sig_net", "訊號日-新進場")
print("[C] 對照：同一批訊號日，改成 10:30 直接進（隔離進場時機差異）")
stat(sig, "pnl_1030_net", "訊號日-10:30進")
print()

print("=== IS / OOS ===")
for lab, sub in [("IS(<=2024)", qual["d"] <= IS_END), ("OOS(>2024)", qual["d"] > IS_END)]:
    print(f"[{lab}]")
    stat(qual[sub], "pnl_1030_net", "  A 全合格日 10:30進")
    s2 = sig[sig["d"] <= IS_END] if "IS" in lab else sig[sig["d"] > IS_END]
    stat(s2, "pnl_sig_net", "  B 訊號日 新進場 ")
    stat(s2, "pnl_1030_net", "  C 訊號日 10:30進")
