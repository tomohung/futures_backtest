"""
H137 Phase 2: 日盤結構閘做多加權 — 逐日向量化回測

策略: 閘開日 (開盤adj>MA_p 且 MA_p斜率向上) → long 08:45 open → exit 13:45 close
對照: 無條件每日做多 (always) / 買進持有 (日盤全段串接)
"""
import duckdb, numpy as np, pandas as pd

DB = "data/futures.duckdb"
IS_END = "2023-12-31"          # IS: 2021-12 ~ 2023-12; OOS: 2024-01 ~
POINT_VALUE = 200               # TX 每點 NT$

con = duckdb.connect(DB, read_only=True)
df = con.execute("""
    SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, open, close, adj_close
    FROM ohlcv_1m WHERE symbol='TX'
      AND CAST(timestamp AS TIME) BETWEEN '08:45' AND '13:45' ORDER BY timestamp
""").df()
con.close()
for c in ['open','close','adj_close']: df[c]=df[c].astype(float)
df['t']=df['t'].astype(str).str.slice(0,5)

day = df.groupby('d').agg(
    day_open=('open','first'), day_close=('close','last'), adj_last=('adj_close','last')
).reset_index().sort_values('d').reset_index(drop=True)
adjrow = df[df['t']=='08:45'].copy(); adjrow['adjo']=adjrow['open']+(adjrow['adj_close']-adjrow['close'])
day['adjo'] = adjrow.set_index('d')['adjo'].reindex(day['d']).values
day['day_ret'] = day['day_close'] - day['day_open']
day['day_pct'] = day['day_ret'] / day['day_open'] * 100
day['year'] = pd.to_datetime(day['d']).dt.year
day['ym'] = pd.to_datetime(day['d']).dt.to_period('M').astype(str)


def build_gate(d0, ma_p, slope_w):
    d = d0.copy()
    d[f'ma'] = d['adj_last'].rolling(ma_p).mean().shift(1)
    d['ma_ago'] = d['ma'].shift(slope_w)
    d['gate'] = (d['adjo'] > d['ma']) & (d['ma'] > d['ma_ago'])
    return d.dropna(subset=['ma','ma_ago']).reset_index(drop=True)


def metrics(rets_pt, entry_px, cost_pt=0.0):
    """rets_pt: 每筆日報酬(點), entry_px: 進場價 (for %). 未進場日不計入交易但計入 equity 平台."""
    r = rets_pt - cost_pt
    n = len(r)
    if n == 0:
        return None
    pct = r / entry_px * 100
    eq = np.cumsum(r)
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    sharpe = pct.mean()/pct.std()*np.sqrt(252) if pct.std()>0 else 0
    win = (r>0).mean()
    return dict(N=n, total=r.sum(), mean=r.mean(), win=win*100,
                sharpe=sharpe, maxdd=dd.min(), meanpct=pct.mean())


def run_strategy(d, cost_pt=0.0):
    g = d[d['gate']]
    return metrics(g['day_ret'].values, g['day_open'].values, cost_pt)

def run_always(d, cost_pt=0.0):
    return metrics(d['day_ret'].values, d['day_open'].values, cost_pt)


def show(label, m):
    if m is None:
        print(f"{label:26s} —"); return
    print(f"{label:26s} N={m['N']:4d}  總={m['total']:+7.0f}pt  "
          f"mean={m['mean']:+6.2f}  勝率={m['win']:4.1f}%  "
          f"Sharpe={m['sharpe']:+5.2f}  maxDD={m['maxdd']:+7.0f}pt")


# ==== 主結果: 預註冊參數 MA60 / slope20 ====
MA_P, SLOPE_W = 60, 20
d = build_gate(day, MA_P, SLOPE_W)
full = d
IS  = d[d['d']<=pd.Timestamp(IS_END)]
OOS = d[d['d']> pd.Timestamp(IS_END)]

print(f"=== H137 主結果 (MA{MA_P}, slope{SLOPE_W}), N={len(d)} {d['d'].min().date()}~{d['d'].max().date()} ===")
print("\n[全期] gross")
show("結構閘做多", run_strategy(full))
show("無條件做多(基準)", run_always(full))

print(f"\n[IS 2021-12~2023-12]")
show("結構閘做多", run_strategy(IS));  show("無條件做多", run_always(IS))
print(f"\n[OOS 2024-01~ (含2025關稅崩盤)]")
show("結構閘做多", run_strategy(OOS)); show("無條件做多", run_always(OOS))

print("\n[逐年] 結構閘 vs 無條件")
for yr in sorted(d.year.unique()):
    ys=d[d.year==yr]
    s=run_strategy(ys); a=run_always(ys)
    ss=f"閘 tot={s['total']:+6.0f}(N={s['N']:3d},Sh{s['sharpe']:+.2f},DD{s['maxdd']:+5.0f})" if s else "閘 —"
    aa=f"無條件 tot={a['total']:+6.0f}(N={a['N']:3d},Sh{a['sharpe']:+.2f},DD{a['maxdd']:+5.0f})" if a else ""
    print(f"  {yr}: {ss} | {aa}")

# ==== 成本敏感度 ====
print("\n[成本敏感度 round-trip] 全期 結構閘")
for cost in [0,1,2,3]:
    show(f"  cost={cost}pt", run_strategy(full, cost))

# ==== 參數敏感度 ====
print("\n[參數敏感度] gross 全期 結構閘 (total pt / Sharpe / maxDD)")
print(f"{'':8s}" + "".join(f"slope{w:<8d}" for w in [10,20,40]))
for ma_p in [20,60,120]:
    line=f"MA{ma_p:<6d}"
    for slope_w in [10,20,40]:
        dd=build_gate(day, ma_p, slope_w)
        m=run_strategy(dd)
        line+=f"{m['total']:+5.0f}/{m['sharpe']:+.2f}/{m['maxdd']:+5.0f} "
    print(line)

# ==== 崩盤剝離檢定 (invalidation #5) ====
print("\n[崩盤剝離] 排除 2022-01~2022-10 + 2025-03~2025-06 後, 平時 閘開vs閘關 日盤做多")
crash = ((d.ym>='2022-01')&(d.ym<='2022-10')) | ((d.ym>='2025-03')&(d.ym<='2025-06'))
peace = d[~crash]
show("  平時 閘開", run_strategy(peace))
off = peace[~peace['gate']]
show("  平時 閘關", metrics(off['day_ret'].values, off['day_open'].values))
print("  (若平時閘開仍>閘關且為正, 表示 edge 不只是避開兩事件)")

# save equity curve
d['pl'] = np.where(d['gate'], d['day_ret'], 0.0)
d[['d','year','gate','day_ret','pl']].to_csv(
    "research/active/H137-structural-long-gate/results/daily.csv", index=False)
print("\n已存 daily.csv")
