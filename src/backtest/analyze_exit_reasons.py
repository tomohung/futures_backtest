"""
列出指定期間每筆交易的出場原因。

用法:
    uv run python src/backtest/analyze_exit_reasons.py --start 2026-01-01
"""

import argparse
from collections import deque
from datetime import time as dtime

import numpy as np
from backtesting import Backtest, Strategy

from src.backtest.runner import load_data_for_orb_est_hl
from src.strategies.estimate_hl_exit import EstimateHLExitMixin

_OR_START    = dtime(8, 45)
_TRAIL_START = dtime(9, 45)
_FORCE_EXIT  = dtime(13, 30)

EXIT_SL      = "SL"
EXIT_SATZONE = "SatZone"
EXIT_DOW     = "DowTrail"
EXIT_FORCE   = "Force@13:30"


class ORBEstHLWithReason(EstimateHLExitMixin, Strategy):
    """Same as ORBWithEstHLExitStrategy but records exit reason per trade."""

    sl_ema_fraction: float = 0.25
    long_only: bool = True
    bigcost_days: int = 2
    or_end_min: int = 537
    entry_end_min: int = 555
    skip_thursday: bool = True
    skip_friday: bool = True

    def init(self):
        self._init_estimate_hl_exit()
        self._prev_date = None
        self._or_end = dtime(self.or_end_min // 60, self.or_end_min % 60)
        h, m = divmod(self.or_end_min + 1, 60)
        self._entry_start = dtime(h, m)
        self._entry_end = dtime(self.entry_end_min // 60, self.entry_end_min % 60)
        self._reset_daily()
        self._exit_reasons: list[tuple] = []  # (exit_bar_idx, reason)

    def _reset_daily(self):
        self._or_high: float = -np.inf
        self._or_low: float = np.inf
        self._entered: bool = False
        self._sl_price: float | None = None
        self._low_buf: deque = deque(maxlen=11)
        self._high_buf: deque = deque(maxlen=5)
        self._dow_trail_stop: float | None = None

    def _close_with_reason(self, reason: str):
        self._exit_reasons.append((len(self.data) - 1, reason))
        self.position.close()

    def next(self):
        cur_ts   = self.data.index[-1]
        cur_time = cur_ts.time()
        cur_date = cur_ts.date()
        close    = float(self.data.Close[-1])

        if cur_date != self._prev_date:
            self._reset_daily()
            self._prev_date = cur_date

        self._record_bar()

        if _OR_START <= cur_time <= self._or_end:
            self._or_high = max(self._or_high, float(self.data.High[-1]))
            self._or_low  = min(self._or_low,  float(self.data.Low[-1]))

        _wd = cur_date.weekday()
        if self.skip_thursday and _wd == 3:
            return
        if self.skip_friday and _wd == 4:
            return

        if (not self._entered
                and self._entry_start <= cur_time <= self._entry_end
                and self._or_high != -np.inf):

            ema_hl = float(self.data.EmaHL[-1])
            if not np.isnan(ema_hl):
                ma30    = float(self.data.MA30_20[-1])
                close30 = float(self.data.Close30[-1])
                bc_vals = [float(getattr(self.data, f"BigCost{i}")[-1])
                           for i in range(1, self.bigcost_days + 1)]
                or_width   = float(self.data.ORWidth[-1])
                rolling_or = float(self.data.RollingOR[-1])
                sl_dist = self.sl_ema_fraction * ema_hl
                trend_nan = np.isnan(ma30) or np.isnan(close30)

                if not np.isnan(rolling_or):
                    if not (0.5 * rolling_or <= or_width <= 1.5 * rolling_or):
                        return

                valid_bc = [v for v in bc_vals if not np.isnan(v)]

                if close > self._or_high:
                    trend_ok = trend_nan or (close30 > ma30)
                    cost_ok  = (not valid_bc
                                or self._or_high > max(valid_bc) + 0.5 * sl_dist)
                    if trend_ok and cost_ok:
                        self.buy(size=1)
                        self._sl_price = close - sl_dist
                        self._entered = True

        if not self.position:
            return

        # 1. SL
        if self._sl_price is not None:
            if self.position.is_long and close < self._sl_price:
                self._close_with_reason(EXIT_SL)
                return

        # 2. SatZone
        if self.position.is_long and self._check_long_exit():
            self._close_with_reason(EXIT_SATZONE)
            return

        # 3. Dow Theory trailing stop
        if cur_time >= _TRAIL_START:
            if self.position.is_long:
                self._low_buf.append(float(self.data.Low[-1]))
                if len(self._low_buf) == 11:
                    lows = list(self._low_buf)
                    if lows[5] == min(lows):
                        if self._dow_trail_stop is None or lows[5] > self._dow_trail_stop:
                            self._dow_trail_stop = lows[5]
                if self._dow_trail_stop is not None and close < self._dow_trail_stop:
                    self._close_with_reason(EXIT_DOW)
                    return

        # 4. Force exit
        if cur_time >= _FORCE_EXIT:
            self._close_with_reason(EXIT_FORCE)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end",   default=None)
    args = parser.parse_args()

    print("Loading data...")
    df = load_data_for_orb_est_hl(start=args.start, end=args.end)

    bt = Backtest(df, ORBEstHLWithReason,
                  cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run()
    strat = stats["_strategy"]

    trades = stats["_trades"].copy()
    if trades.empty:
        print("No trades found.")
        return

    # Map exit bar index → reason
    reason_map = {bar: reason for bar, reason in strat._exit_reasons}
    trades["ExitReason"] = trades["ExitBar"].map(reason_map).fillna("?")
    trades["Weekday"]    = trades["EntryTime"].dt.strftime("%a")
    trades["EntryTime"]  = trades["EntryTime"].dt.strftime("%m-%d %H:%M")
    trades["ExitTime"]   = trades["ExitTime"].dt.strftime("%H:%M")

    print(f"\n{'='*72}")
    print(f"  {args.start} ~ {args.end or 'latest'}  共 {len(trades)} 筆")
    print(f"{'='*72}")
    print(f"{'日期時間':<13} {'出':<6} {'星期':<4} {'進場':>7} {'出場':>7} {'損益':>6}  出場原因")
    print(f"{'-'*72}")

    total = 0
    for _, t in trades.iterrows():
        total += t["PnL"]
        win = "✓" if t["PnL"] > 0 else "✗"
        print(f"{t['EntryTime']:<13} {t['ExitTime']:<6} {t['Weekday']:<4} "
              f"{t['EntryPrice']:>7.0f} {t['ExitPrice']:>7.0f} "
              f"{t['PnL']:>+6.0f}  {win} {t['ExitReason']}")

    print(f"{'-'*72}")
    wins = (trades["PnL"] > 0).sum()
    print(f"  總損益 {total:+.0f}  勝率 {wins}/{len(trades)} = {wins/len(trades)*100:.1f}%")
    print()
    print("  出場原因統計:")
    for reason, grp in trades.groupby("ExitReason"):
        w = (grp["PnL"] > 0).sum()
        print(f"    {reason:<12} {len(grp):>3} 筆  勝率 {w/len(grp)*100:.0f}%  "
              f"總損益 {grp['PnL'].sum():+.0f}  平均 {grp['PnL'].mean():+.1f}")


if __name__ == "__main__":
    main()
