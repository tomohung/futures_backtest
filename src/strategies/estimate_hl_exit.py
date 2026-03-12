"""
Shared exit strategy Mixin based on Estimated H-L Satisfaction Zones.

Usage
-----
Mix into any backtesting.py Strategy subclass::

    class MyStrategy(EstimateHLExitMixin, Strategy):
        def init(self):
            self._init_estimate_hl_exit()
            # ... your own init

        def next(self):
            # ... your own entry logic

            # Collect today's sat-zone values and update close buffer
            self._record_bar()

            if self.position.is_long:
                if self._check_long_exit():
                    self.position.close()
            elif self.position.is_short:
                if self._check_short_exit():
                    self.position.close()

Prerequisite
------------
The DataFrame passed to ``Backtest()`` must contain ``SatZoneUpper`` and
``SatZoneLower`` columns as produced by
:func:`src.backtest.estimate_hl.compute_estimate_hl_zones`.
"""

from collections import deque

import numpy as np


class EstimateHLExitMixin:
    """Mixin that provides Estimated H-L zone exit logic.

    Exit rules (long side, short is mirrored):
      1. Among all ``SatZoneUpper`` values seen so far today, pick the
         **lowest one that is still above the current close** as the target.
      2. Phase 1: wait until ``High >= target_upper`` (zone touched).
      3. Phase 2: once touched, exit when the 1-min close drops below the
         5-bar moving average of recent closes.
      4. Fallback: if no valid target exists, hold until the caller's own
         forced-close logic handles the position.
    """

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def _init_estimate_hl_exit(self) -> None:
        """Call once inside ``init()``."""
        self._hl_prev_date = None
        self._reset_estimate_hl_exit()

    def _reset_estimate_hl_exit(self) -> None:
        """Reset all intra-day state.  Call at the start of each new trading day."""
        self._hl_zone_touched: bool = False
        self._close_buffer: deque = deque(maxlen=5)
        self._target_upper: float | None = None
        self._target_lower: float | None = None

    # ------------------------------------------------------------------
    # Per-bar update (call this every bar from next())
    # ------------------------------------------------------------------

    def _record_bar(self) -> None:
        """Record current bar's close and sat-zone values.

        Call this once per bar *before* ``_check_long_exit`` /
        ``_check_short_exit`` so the rolling close buffer and zone sets are
        up-to-date.
        """
        # Day rollover check
        cur_date = self.data.index[-1].date()
        if cur_date != self._hl_prev_date:
            self._reset_estimate_hl_exit()
            self._hl_prev_date = cur_date

        # Rolling close buffer (max 5)
        self._close_buffer.append(float(self.data.Close[-1]))

    # ------------------------------------------------------------------
    # Target selection
    # ------------------------------------------------------------------

    def _update_long_target(self) -> None:
        """Use the current bar's SatZoneUpper as the target (if above close)."""
        if self._hl_zone_touched:
            return  # keep the target fixed once touched
        sat_upper = float(self.data.SatZoneUpper[-1])
        if np.isnan(sat_upper):
            self._target_upper = None
        else:
            price = float(self.data.Close[-1])
            self._target_upper = sat_upper if sat_upper > price else None

    def _update_short_target(self) -> None:
        """Use the current bar's SatZoneLower as the target (if below close)."""
        if self._hl_zone_touched:
            return
        sat_lower = float(self.data.SatZoneLower[-1])
        if np.isnan(sat_lower):
            self._target_lower = None
        else:
            price = float(self.data.Close[-1])
            self._target_lower = sat_lower if sat_lower < price else None

    # ------------------------------------------------------------------
    # 5-bar MA helper
    # ------------------------------------------------------------------

    def _ma5(self) -> float | None:
        """Return the 5-bar MA of recent closes, or None if fewer than 5 bars."""
        if len(self._close_buffer) < 5:
            return None
        return sum(self._close_buffer) / 5

    # ------------------------------------------------------------------
    # Exit checks
    # ------------------------------------------------------------------

    def _check_long_exit(self) -> bool:
        """Return True when the long position should be closed.

        Phase 1: High >= target_upper  →  zone touched.
        Phase 2: close < 5-bar MA      →  exit.
        """
        self._update_long_target()

        if self._target_upper is None:
            return False  # no valid target; caller handles forced close

        high = float(self.data.High[-1])
        close = float(self.data.Close[-1])

        if not self._hl_zone_touched:
            if high >= self._target_upper:
                self._hl_zone_touched = True
            else:
                return False  # still waiting to touch the zone

        # Phase 2: exit when close drops below 5MA
        ma = self._ma5()
        if ma is None:
            return False  # not enough bars yet
        return close < ma

    def _check_short_exit(self) -> bool:
        """Return True when the short position should be closed.

        Phase 1: Low <= target_lower  →  zone touched.
        Phase 2: close > 5-bar MA     →  exit.
        """
        self._update_short_target()

        if self._target_lower is None:
            return False

        low = float(self.data.Low[-1])
        close = float(self.data.Close[-1])

        if not self._hl_zone_touched:
            if low <= self._target_lower:
                self._hl_zone_touched = True
            else:
                return False

        ma = self._ma5()
        if ma is None:
            return False
        return close > ma
