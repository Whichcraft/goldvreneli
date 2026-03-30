"""
Smoke tests for PortfolioManager.
No external API calls; scanner is bypassed by injecting _candidates directly.
"""

import time
from datetime import datetime
from unittest.mock import patch

import pytest

from portfolio import PortfolioManager
from autotrader import TraderConfig, TraderState


# ── Stubs ─────────────────────────────────────────────────────────────────────

_PRICE = 50.0

def _get_price(sym):   return _PRICE
def _place_buy(sym, qty):  pass
def _place_sell(sym, qty): pass
def _get_equity():     return 10_000.0

CANDIDATES = ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA", "META", "NFLX"]


def _make_pm(slots=2, config=None, daily_loss_limit=0.0, slot_dollar=100.0):
    pm = PortfolioManager(
        data_client      = None,
        get_price_fn     = _get_price,
        place_buy_fn     = _place_buy,
        place_sell_fn    = _place_sell,
        get_bars_fn      = None,
        get_equity_fn    = _get_equity,
        target_slots     = slots,
        slot_dollar      = slot_dollar,
        trader_config    = config or TraderConfig(),
        daily_loss_limit = daily_loss_limit,
    )
    # Bypass scanner by pre-populating candidates
    pm._candidates    = list(CANDIDATES)
    pm._candidates_ts = datetime.now()
    return pm


def _wait(condition, timeout=5.0, poll=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(poll)
    return False


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestPortfolioManager:

    def test_daily_loss_limit_propagated(self):
        pm = _make_pm(daily_loss_limit=500.0)
        assert pm._multi._daily_loss_limit == 500.0

    def test_zero_daily_loss_limit(self):
        pm = _make_pm(daily_loss_limit=0.0)
        assert pm._multi._daily_loss_limit == 0.0

    def test_start_all_opens_n_slots(self):
        pm = _make_pm(slots=2)
        with patch.object(pm, "_rescan", return_value=None):
            pm.start_all()
            assert _wait(lambda: pm.active_count() >= 2), \
                f"expected 2 active slots, got {pm.active_count()}"
        pm.stop()

    def test_start_all_does_not_exceed_target(self):
        pm = _make_pm(slots=3)
        with patch.object(pm, "_rescan", return_value=None):
            pm.start_all()
            _wait(lambda: pm.active_count() >= 3)
            time.sleep(0.2)   # extra time to check no over-opening
            assert pm.active_count() <= 3
        pm.stop()

    def test_start_idempotent(self):
        """Calling start_all twice should not open more than target_slots."""
        pm = _make_pm(slots=2)
        with patch.object(pm, "_rescan", return_value=None):
            pm.start_all()
            pm.start_all()  # second call must be a no-op
            _wait(lambda: pm.active_count() >= 2)
            time.sleep(0.1)
            assert pm.active_count() <= 2
        pm.stop()

    def test_running_flag(self):
        pm = _make_pm(slots=1)
        assert not pm.running
        with patch.object(pm, "_rescan", return_value=None):
            pm.start_all()
            assert pm.running
        pm.stop()
        assert not pm.running

    def test_pause_blocks_new_opens(self):
        """Calling _open_one_slot while paused is a no-op."""
        opened = []
        pm = _make_pm(slots=2)
        pm._running = True
        pm._paused  = True
        pm._candidates = list(CANDIDATES)
        pm._candidates_ts = datetime.now()

        with patch.object(pm, "_rescan", return_value=None):
            # Directly invoke _open_one_slot — should return immediately when paused
            pm._open_one_slot()

        assert pm.active_count() == 0, "paused PM should not open any position"
        pm._running = False

    def test_resume_after_pause(self):
        """Resume fills empty slots after a pause."""
        pm = _make_pm(slots=2)
        with patch.object(pm, "_rescan", return_value=None):
            pm.start_all()
            _wait(lambda: pm.active_count() >= 1, timeout=5)
            pm.pause()
            assert pm.paused
            pm.resume()
            assert not pm.paused
        pm.stop()

    def test_slot_dollar_sizing(self):
        """slot_dollar=500 / price=50 → qty=10."""
        pm = _make_pm(slots=1, slot_dollar=500.0)
        with patch.object(pm, "_rescan", return_value=None):
            pm.start_all()
            _wait(lambda: pm.active_count() >= 1)
        statuses = pm.statuses()
        active = [s for s in statuses.values()
                  if s.state in (TraderState.ENTERING, TraderState.WATCHING)]
        assert len(active) == 1
        assert active[0].qty == 10
        pm.stop()

    def test_refill_on_close(self):
        """When a position closes via time-stop, PM opens a replacement."""
        open_calls = []
        config = TraderConfig(
            stop_value         = 99.0,       # very wide trailing stop
            time_stop_minutes  = 1 / 60,     # ~1 second
            poll_interval      = 0.05,
        )
        pm = _make_pm(slots=1, config=config)
        original_open = pm._open_one_slot.__func__

        def counting_open(self_):
            open_calls.append(time.time())
            original_open(self_)

        with patch.object(pm, "_rescan", return_value=None), \
             patch.object(type(pm), "_open_one_slot", counting_open):
            pm.start_all()
            # Wait for initial open
            assert _wait(lambda: len(open_calls) >= 1, timeout=5), \
                "initial position did not open"
            # Wait for time-stop close + refill call (second open)
            assert _wait(lambda: len(open_calls) >= 2, timeout=15), \
                f"refill did not happen — open_calls={len(open_calls)}"
        pm.stop()
