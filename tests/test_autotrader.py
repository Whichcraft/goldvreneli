"""
Unit tests for autotrader.py — size_from_risk, _calc_atr, AutoTrader lifecycle.
No external API calls; uses SyntheticPriceFeed + MockBroker from replay.py.
"""

import time
import pytest
import numpy as np
import pandas as pd

from autotrader import (
    AutoTrader,
    MultiTrader,
    TraderConfig,
    TraderState,
    StopMode,
    EntryMode,
    size_from_risk,
    _calc_atr,
)
from replay import SyntheticPriceFeed, MockBroker, ReplayPriceFeed


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_bars(n=30, base=100.0, seed=42) -> pd.DataFrame:
    """Synthetic OHLCV DataFrame for indicator tests."""
    rng = np.random.default_rng(seed)
    closes = base + np.cumsum(rng.normal(0, 0.5, n))
    closes = np.maximum(closes, 1.0)
    high = closes + rng.uniform(0, 1, n)
    low  = closes - rng.uniform(0, 1, n)
    return pd.DataFrame({"open": closes, "high": high, "low": low,
                         "close": closes, "volume": np.full(n, 1_000_000)})


def wait_for_state(at: AutoTrader, states, timeout=5.0, poll=0.05):
    """Block until AutoTrader reaches one of the given states (or timeout)."""
    if isinstance(states, TraderState):
        states = {states}
    deadline = time.time() + timeout
    while time.time() < deadline:
        if at.status.state in states:
            return True
        time.sleep(poll)
    return False


# ── size_from_risk ─────────────────────────────────────────────────────────────

class TestSizeFromRisk:
    def test_basic(self):
        # risk 1% of $10k with stop distance $1 → 100 shares
        assert size_from_risk(10_000, 1.0, 50.0, 1.0) == 100

    def test_minimum_one_share(self):
        # tiny equity → at least 1
        assert size_from_risk(1.0, 1.0, 100.0, 500.0) == 1

    def test_proportional_to_equity(self):
        qty1 = size_from_risk(10_000, 1.0, 50.0, 1.0)
        qty2 = size_from_risk(20_000, 1.0, 50.0, 1.0)
        assert qty2 == qty1 * 2

    def test_proportional_to_risk_pct(self):
        qty1 = size_from_risk(10_000, 1.0, 50.0, 1.0)
        qty2 = size_from_risk(10_000, 2.0, 50.0, 1.0)
        assert qty2 == qty1 * 2

    def test_invalid_stop_distance(self):
        with pytest.raises(ValueError):
            size_from_risk(10_000, 1.0, 50.0, 0.0)

    def test_invalid_entry_price(self):
        with pytest.raises(ValueError):
            size_from_risk(10_000, 1.0, 0.0, 1.0)

    def test_fractional_result_truncates(self):
        # 1% of $10k = $100 risk, stop=$3 → 33.33 → 33
        assert size_from_risk(10_000, 1.0, 50.0, 3.0) == 33


# ── _calc_atr ─────────────────────────────────────────────────────────────────

class TestCalcAtr:
    def test_returns_positive_float(self):
        bars = make_bars(30)
        atr = _calc_atr(bars)
        assert isinstance(atr, float)
        assert atr > 0

    def test_requires_enough_bars(self):
        bars = make_bars(14)  # need at least 15 for period=14
        with pytest.raises(ValueError):
            _calc_atr(bars)

    def test_exact_minimum_bars(self):
        bars = make_bars(15)
        atr = _calc_atr(bars)
        assert atr > 0

    def test_custom_period(self):
        bars = make_bars(30)
        atr5  = _calc_atr(bars, period=5)
        atr14 = _calc_atr(bars, period=14)
        assert atr5 != atr14  # different periods → different values

    def test_higher_volatility_gives_higher_atr(self):
        bars_calm     = make_bars(30, base=100.0)
        # scale range to be 10× wider
        bars_volatile = bars_calm.copy()
        bars_volatile["high"]  = bars_calm["close"] + (bars_calm["high"]  - bars_calm["close"]) * 10
        bars_volatile["low"]   = bars_calm["close"] - (bars_calm["close"] - bars_calm["low"])   * 10
        assert _calc_atr(bars_volatile) > _calc_atr(bars_calm)


# ── SyntheticPriceFeed ────────────────────────────────────────────────────────

class TestSyntheticPriceFeed:
    def test_starts_near_start_price(self):
        feed = SyntheticPriceFeed(start_price=100.0, volatility_pct=0.001, seed=1)
        price = feed.get_price("X")
        assert 90 < price < 110

    def test_deterministic_with_seed(self):
        prices_a = [SyntheticPriceFeed(100, seed=7).get_price("X") for _ in range(5)]
        prices_b = [SyntheticPriceFeed(100, seed=7).get_price("X") for _ in range(5)]
        assert prices_a == prices_b

    def test_step_increments(self):
        feed = SyntheticPriceFeed(100, seed=1)
        for i in range(1, 4):
            feed.get_price("X")
            assert feed.step == i

    def test_reset(self):
        feed = SyntheticPriceFeed(100, seed=1)
        feed.get_price("X")
        feed.get_price("X")
        feed.reset()
        assert feed.step == 0

    def test_price_always_positive(self):
        feed = SyntheticPriceFeed(0.02, volatility_pct=5.0, seed=99)
        for _ in range(100):
            assert feed.get_price("X") > 0


# ── MockBroker ────────────────────────────────────────────────────────────────

class TestMockBroker:
    def test_buy_records_fill(self, tmp_path):
        feed   = SyntheticPriceFeed(100, seed=1)
        broker = MockBroker(feed.get_price, output_file=str(tmp_path / "fills.json"))
        broker.get_price("AAPL")
        broker.buy("AAPL", 10)
        assert len(broker.fills) == 1
        assert broker.fills[0]["action"] == "BUY"
        assert broker.fills[0]["qty"]    == 10

    def test_sell_records_fill(self, tmp_path):
        feed   = SyntheticPriceFeed(100, seed=1)
        broker = MockBroker(feed.get_price, output_file=str(tmp_path / "fills.json"))
        broker.get_price("AAPL")
        broker.sell("AAPL", 5)
        fill = broker.fills[0]
        assert fill["action"] == "SELL"
        assert fill["qty"]    == 5

    def test_flush_writes_json(self, tmp_path):
        import json
        out    = tmp_path / "fills.json"
        feed   = SyntheticPriceFeed(100, seed=1)
        broker = MockBroker(feed.get_price, output_file=str(out))
        broker.get_price("AAPL")
        broker.buy("AAPL", 1)
        data = json.loads(out.read_text())
        assert "sessions" in data
        assert len(data["sessions"]) == 1

    def test_close_records_pnl(self, tmp_path):
        import json
        out    = tmp_path / "fills.json"
        feed   = SyntheticPriceFeed(100, seed=1)
        broker = MockBroker(feed.get_price, output_file=str(out))
        broker.close(pnl=42.5)
        data    = json.loads(out.read_text())
        session = data["sessions"][0]
        assert session["pnl"]       == 42.5
        assert session["closed_at"] is not None

    def test_corrupted_json_is_handled(self, tmp_path):
        """MockBroker should not crash if the JSON file is corrupted."""
        out = tmp_path / "fills.json"
        out.write_text("not valid json")
        feed   = SyntheticPriceFeed(100, seed=1)
        broker = MockBroker(feed.get_price, output_file=str(out))
        broker.get_price("AAPL")
        broker.buy("AAPL", 1)
        # Should have written a fresh valid JSON, recovering from corruption
        import json
        data = json.loads(out.read_text())
        assert "sessions" in data


# ── AutoTrader lifecycle ──────────────────────────────────────────────────────

class TestAutoTraderLifecycle:
    def _make_trader_and_broker(self, tmp_path, start_price=100.0,
                                 volatility=0.5, drift=0.0, seed=42):
        feed   = SyntheticPriceFeed(start_price, volatility_pct=volatility,
                                    drift_pct=drift, seed=seed)
        broker = MockBroker(feed.get_price, output_file=str(tmp_path / "fills.json"))
        at     = AutoTrader(
            get_price  = broker.get_price,
            place_buy  = broker.buy,
            place_sell = broker.sell,
            poll_interval = 0.01,
        )
        at._on_close = lambda pnl: broker.close(pnl)
        return at, broker, feed

    def test_idle_on_construction(self, tmp_path):
        at, _, _ = self._make_trader_and_broker(tmp_path)
        assert at.status.state == TraderState.IDLE

    def test_market_entry_transitions_to_watching(self, tmp_path):
        at, _, _ = self._make_trader_and_broker(tmp_path)
        cfg = TraderConfig(stop_value=50.0, poll_interval=0.01)
        at.start("AAPL", 10, config=cfg)
        reached = wait_for_state(at, TraderState.WATCHING, timeout=2)
        assert reached, f"Stuck in {at.status.state}"
        assert at.status.entry_price > 0
        assert at.status.qty == 10

    def test_stop_halts_without_selling(self, tmp_path):
        at, broker, _ = self._make_trader_and_broker(tmp_path)
        cfg = TraderConfig(stop_value=50.0, poll_interval=0.01)
        at.start("AAPL", 5, config=cfg)
        wait_for_state(at, TraderState.WATCHING, timeout=2)
        at.stop()
        assert at.status.state == TraderState.STOPPED
        # stop() must NOT place a sell order
        sell_fills = [f for f in broker.fills if f["action"] == "SELL"]
        assert len(sell_fills) == 0

    def test_trailing_stop_fires(self, tmp_path):
        """Feed with strong downward drift should trigger trailing stop."""
        at, broker, _ = self._make_trader_and_broker(
            tmp_path, start_price=100.0, volatility=0.1, drift=-5.0, seed=1)
        cfg = TraderConfig(stop_value=0.5, poll_interval=0.01)
        at.start("TEST", 1, config=cfg)
        reached = wait_for_state(at, TraderState.SOLD, timeout=10)
        assert reached, f"Stuck in {at.status.state}"
        sell_fills = [f for f in broker.fills if f["action"] == "SELL"]
        assert len(sell_fills) >= 1

    def test_take_profit_fires(self, tmp_path):
        """Feed with strong upward drift should trigger take-profit."""
        at, broker, _ = self._make_trader_and_broker(
            tmp_path, start_price=100.0, volatility=0.1, drift=5.0, seed=2)
        cfg = TraderConfig(
            stop_value=99.0,       # wide stop so trailing stop doesn't hit first
            tp_trigger_pct=1.0,    # take profit after +1%
            tp_qty_fraction=1.0,
            poll_interval=0.01,
        )
        at.start("TEST", 1, config=cfg)
        reached = wait_for_state(at, TraderState.SOLD, timeout=10)
        assert reached, f"Stuck in {at.status.state}"
        tp_logs = [l for l in at.status.log if l.action == "TAKE_PROFIT"]
        assert len(tp_logs) >= 1

    def test_attach_skips_buy(self, tmp_path):
        """attach() should not place a BUY order."""
        at, broker, _ = self._make_trader_and_broker(tmp_path)
        cfg = TraderConfig(stop_value=50.0, poll_interval=0.01)
        at.attach("AAPL", 5, entry_price=100.0, config=cfg)
        wait_for_state(at, TraderState.WATCHING, timeout=2)
        buy_fills = [f for f in broker.fills if f["action"] == "BUY"]
        assert len(buy_fills) == 0
        assert at.status.entry_price == 100.0

    def test_duplicate_start_raises(self, tmp_path):
        at, _, _ = self._make_trader_and_broker(tmp_path)
        cfg = TraderConfig(stop_value=50.0, poll_interval=0.01)
        at.start("AAPL", 1, config=cfg)
        wait_for_state(at, TraderState.WATCHING, timeout=2)
        with pytest.raises(RuntimeError):
            at.start("AAPL", 1, config=cfg)

    def test_invalid_qty_raises(self, tmp_path):
        at, _, _ = self._make_trader_and_broker(tmp_path)
        with pytest.raises(ValueError):
            at.start("AAPL", 0)

    def test_empty_symbol_raises(self, tmp_path):
        at, _, _ = self._make_trader_and_broker(tmp_path)
        with pytest.raises(ValueError):
            at.start("", 1)

    def test_time_stop_fires(self, tmp_path):
        at, broker, _ = self._make_trader_and_broker(
            tmp_path, volatility=0.001, seed=5)
        cfg = TraderConfig(
            stop_value=99.0,
            time_stop_minutes=0.001,  # ~0.06 seconds
            poll_interval=0.01,
        )
        at.start("TEST", 1, config=cfg)
        reached = wait_for_state(at, TraderState.SOLD, timeout=5)
        assert reached, f"Stuck in {at.status.state}"
        time_logs = [l for l in at.status.log if l.action == "TIME_STOP"]
        assert len(time_logs) == 1

    def test_error_state_on_get_price_exception(self, tmp_path):
        calls = [0]

        def bad_price(sym):
            calls[0] += 1
            if calls[0] > 2:
                raise RuntimeError("feed exploded")
            return 100.0

        broker_buys  = []
        broker_sells = []
        at = AutoTrader(
            get_price  = bad_price,
            place_buy  = lambda s, q: broker_buys.append((s, q)),
            place_sell = lambda s, q: broker_sells.append((s, q)),
            poll_interval = 0.01,
        )
        cfg = TraderConfig(stop_value=50.0, poll_interval=0.01)
        at.start("BOOM", 1, config=cfg)
        reached = wait_for_state(at, TraderState.ERROR, timeout=5)
        assert reached, f"Stuck in {at.status.state}"

    def test_max_loss_guard_beats_time_stop(self, tmp_path):
        """Max-loss guard must fire before time-stop when both conditions are met."""
        at, broker, _ = self._make_trader_and_broker(
            tmp_path, start_price=100.0, volatility=0.1, drift=-20.0, seed=5)
        cfg = TraderConfig(
            stop_value=50.0,          # wide trailing stop — would not fire soon
            max_loss_pct=2.0,
            time_stop_minutes=0.001,  # also nearly expired (< 0.1 s)
            poll_interval=0.01,
        )
        at.start("TEST", 1, config=cfg)
        reached = wait_for_state(at, TraderState.SOLD, timeout=10)
        assert reached
        # The exit log should mention max-loss, not time-stop
        actions = [e.action for e in at.status.log]
        assert "SELL" in actions
        # Should NOT have fired a TIME_STOP (max-loss takes priority)
        assert "TIME_STOP" not in actions

    def test_max_loss_guard_fires(self, tmp_path):
        """max_loss_pct should trigger a sell even when price is still above the trailing stop floor."""
        # Strong downward drift so price will drop well past max_loss_pct quickly
        at, broker, _ = self._make_trader_and_broker(
            tmp_path, start_price=100.0, volatility=0.1, drift=-20.0, seed=5)
        cfg = TraderConfig(
            stop_value=50.0,      # wide trailing stop — would not fire soon
            max_loss_pct=2.0,     # exit if down 2% from entry
            poll_interval=0.01,
        )
        at.start("TEST", 1, config=cfg)
        reached = wait_for_state(at, TraderState.SOLD, timeout=10)
        assert reached, f"Stuck in {at.status.state}"
        # Loss should not vastly exceed max_loss_pct (some overshoot is expected from polling)
        loss_pct = (at.status.entry_price - at.status.current_price) / at.status.entry_price * 100
        assert loss_pct >= 2.0, "Max-loss guard should have fired at or below entry - 2%"
        sell_fills = [f for f in broker.fills if f["action"] == "SELL"]
        assert len(sell_fills) >= 1

    def test_breakeven_raises_stop_floor(self, tmp_path):
        """After breakeven activates, stop floor must be >= entry price."""
        at, _, _ = self._make_trader_and_broker(
            tmp_path, start_price=100.0, volatility=0.1, drift=2.0, seed=10)
        cfg = TraderConfig(
            stop_value=99.0,
            breakeven_trigger_pct=0.5,  # activate after 0.5% gain
            poll_interval=0.01,
        )
        at.start("TEST", 1, config=cfg)
        wait_for_state(at, TraderState.WATCHING, timeout=2)
        # Wait for breakeven to activate
        deadline = time.time() + 5
        while time.time() < deadline:
            if at.status.breakeven_active:
                break
            time.sleep(0.05)
        if at.status.breakeven_active:
            assert at.status.stop_floor >= at.status.entry_price
        at.stop()


# ── TraderConfig validation ───────────────────────────────────────────────────

class TestTraderConfigValidation:
    def test_zero_stop_value_raises(self):
        with pytest.raises(ValueError, match="stop_value"):
            TraderConfig(stop_value=0.0)

    def test_negative_stop_value_raises(self):
        with pytest.raises(ValueError, match="stop_value"):
            TraderConfig(stop_value=-1.0)

    def test_zero_poll_interval_raises(self):
        with pytest.raises(ValueError, match="poll_interval"):
            TraderConfig(poll_interval=0.0)

    def test_zero_scale_tranches_raises(self):
        with pytest.raises(ValueError, match="scale_tranches"):
            TraderConfig(scale_tranches=0)

    def test_tp_fraction_above_one_raises(self):
        with pytest.raises(ValueError, match="tp_qty_fraction"):
            TraderConfig(tp_qty_fraction=1.5)

    def test_tp_fraction_zero_raises(self):
        with pytest.raises(ValueError, match="tp_qty_fraction"):
            TraderConfig(tp_qty_fraction=0.0)

    def test_negative_max_loss_raises(self):
        with pytest.raises(ValueError, match="max_loss_pct"):
            TraderConfig(max_loss_pct=-1.0)

    def test_valid_config_ok(self):
        cfg = TraderConfig(stop_value=0.5, poll_interval=1.0, tp_qty_fraction=0.5,
                           max_loss_pct=5.0)
        assert cfg.stop_value == 0.5

    def test_zero_max_loss_ok(self):
        # 0.0 means disabled — should not raise
        cfg = TraderConfig(max_loss_pct=0.0)
        assert cfg.max_loss_pct == 0.0


# ── Scale entry ───────────────────────────────────────────────────────────────

class TestScaleEntry:
    def _make_at(self, tmp_path, prices):
        """AutoTrader wired to a list of deterministic prices."""
        it      = iter(prices)
        def get_price(sym): return next(it, prices[-1])
        buys    = []
        sells   = []
        at = AutoTrader(
            get_price  = get_price,
            place_buy  = lambda s, q: buys.append((s, q)),
            place_sell = lambda s, q: sells.append((s, q)),
        )
        at._on_close = lambda pnl: None
        return at, buys, sells

    def test_scale_average_entry_price(self, tmp_path):
        """3-tranche scale: entry_price == weighted average of fill prices."""
        # Prices: 3 for entry polls, then high enough that trailing stop never fires
        prices = [100.0, 102.0, 104.0] + [200.0] * 100
        at, buys, _ = self._make_at(tmp_path, prices)
        cfg = TraderConfig(
            stop_value=99.0,       # very wide — won't fire
            entry_mode=EntryMode.SCALE,
            scale_tranches=3,
            scale_interval_s=0.0,
            poll_interval=0.01,
        )
        at.start("AAA", 9, config=cfg)
        wait_for_state(at, TraderState.WATCHING, timeout=5)
        # 9 shares across 3 tranches = 3 each (3+3+3)
        buy_qtys = [q for _, q in buys]
        assert sum(buy_qtys) == 9
        assert len(buy_qtys) == 3
        expected_avg = (100.0 * 3 + 102.0 * 3 + 104.0 * 3) / 9
        assert abs(at.status.entry_price - expected_avg) < 0.01
        at.stop()

    def test_scale_stop_fires_after_all_tranches(self, tmp_path):
        """Stop must fire correctly after scale entry completes."""
        # Buy at ~100, then drop sharply below stop
        prices = [100.0, 100.0, 100.0] + [50.0] * 100
        at, buys, sells = self._make_at(tmp_path, prices)
        cfg = TraderConfig(
            stop_value=0.5,
            entry_mode=EntryMode.SCALE,
            scale_tranches=2,
            scale_interval_s=0.0,
            poll_interval=0.01,
        )
        at.start("BBB", 2, config=cfg)
        reached = wait_for_state(at, TraderState.SOLD, timeout=5)
        assert reached, f"Stuck in {at.status.state}"
        assert len(sells) >= 1

    def test_scale_stop_mid_scale(self, tmp_path):
        """Calling stop() during scale entry results in STOPPED, no dangling sell."""
        prices = [100.0] * 1000
        it      = iter(prices)
        buys    = []
        sells   = []
        import threading
        paused = threading.Event()

        def slow_buy(s, q):
            buys.append((s, q))
            paused.wait(timeout=2)   # block after first tranche

        at = AutoTrader(
            get_price  = lambda sym: next(it, 100.0),
            place_buy  = slow_buy,
            place_sell = lambda s, q: sells.append((s, q)),
        )
        at._on_close = lambda pnl: None
        cfg = TraderConfig(
            stop_value=99.0,
            entry_mode=EntryMode.SCALE,
            scale_tranches=3,
            scale_interval_s=0.0,
            poll_interval=0.01,
        )
        at.start("CCC", 3, config=cfg)
        time.sleep(0.05)        # let first tranche buy call happen
        at.stop()
        paused.set()            # unblock buy so thread can exit cleanly
        wait_for_state(at, {TraderState.STOPPED, TraderState.SOLD, TraderState.ERROR}, timeout=3)
        assert len(sells) == 0  # stop() should not place a sell


# ── Partial take-profit ───────────────────────────────────────────────────────

class TestPartialTakeProfit:
    def test_partial_sell_and_remainder_trails(self, tmp_path):
        """tp_qty_fraction=0.5: only half sold at take-profit; rest continues trailing."""
        feed   = SyntheticPriceFeed(100.0, volatility_pct=0.1, drift_pct=5.0, seed=7)
        sells  = []
        buys   = []
        at = AutoTrader(
            get_price  = feed.get_price,
            place_buy  = lambda s, q: buys.append(q),
            place_sell = lambda s, q: sells.append(q),
            poll_interval=0.01,
        )
        at._on_close = lambda pnl: None
        cfg = TraderConfig(
            stop_value=99.0,          # very wide trailing stop
            tp_trigger_pct=0.5,       # trigger after 0.5% gain
            tp_qty_fraction=0.5,      # sell half
            poll_interval=0.01,
        )
        at.start("TP", 10, config=cfg)
        # Wait for take-profit to execute
        deadline = time.time() + 5
        while time.time() < deadline:
            if at.status.tp_executed:
                break
            time.sleep(0.05)
        assert at.status.tp_executed, "Take-profit did not execute"
        # First sell should be exactly half of 10 shares
        assert sells[0] == 5
        # qty_remaining updated
        assert at.status.qty_remaining == 5
        at.stop()

    def test_full_tp_fraction_closes_all(self, tmp_path):
        """tp_qty_fraction=1.0 (default): position closes completely on take-profit."""
        feed  = SyntheticPriceFeed(100.0, volatility_pct=0.1, drift_pct=5.0, seed=8)
        sells = []
        at = AutoTrader(
            get_price  = feed.get_price,
            place_buy  = lambda s, q: None,
            place_sell = lambda s, q: sells.append(q),
            poll_interval=0.01,
        )
        at._on_close = lambda pnl: None
        cfg = TraderConfig(
            stop_value=99.0,
            tp_trigger_pct=0.5,
            tp_qty_fraction=1.0,
            poll_interval=0.01,
        )
        at.start("TP2", 4, config=cfg)
        reached = wait_for_state(at, TraderState.SOLD, timeout=5)
        assert reached
        assert sum(sells) == 4


# ── ATR stop full lifecycle ───────────────────────────────────────────────────

class TestAtrStopLifecycle:
    def test_atr_stop_fires(self, tmp_path):
        """ATR stop must fire when price drops N×ATR below peak."""
        # Fixed bars giving a known ATR (~1.0)
        bars = make_bars(30, base=100.0, seed=1)
        atr  = _calc_atr(bars)   # actual value, so we can size the drop

        # Price feed: rises a bit then drops well past ATR stop
        rise   = [100.0 + i * 0.5 for i in range(5)]   # up to ~102
        peak   = rise[-1]
        drop   = [peak - atr * 2 * (i + 1) for i in range(20)]  # drop hard
        prices = rise + drop + [drop[-1]] * 50
        it     = iter(prices)

        sells = []
        at = AutoTrader(
            get_price  = lambda sym: next(it, prices[-1]),
            place_buy  = lambda s, q: None,
            place_sell = lambda s, q: sells.append((s, q)),
            get_bars   = lambda sym: bars,
        )
        at._on_close = lambda pnl: None
        cfg = TraderConfig(
            stop_mode  = StopMode.ATR,
            stop_value = 1.0,   # 1× ATR
            poll_interval = 0.01,
        )
        at.start("ATR", 5, config=cfg)
        reached = wait_for_state(at, TraderState.SOLD, timeout=5)
        assert reached, f"ATR stop did not fire, state={at.status.state}"
        assert len(sells) >= 1
        assert at.status.atr_value > 0


# ── MultiTrader ───────────────────────────────────────────────────────────────

class TestMultiTrader:
    def _make_mt(self, prices_by_sym=None, drift=0.0):
        """MultiTrader backed by per-symbol SyntheticPriceFeeds."""
        feeds: dict = {}
        buys  = []
        sells = []

        def get_price(sym):
            if sym not in feeds:
                feeds[sym] = SyntheticPriceFeed(100.0, volatility_pct=0.1,
                                                drift_pct=drift, seed=42)
            return feeds[sym].get_price(sym)

        mt = MultiTrader(
            get_price  = get_price,
            place_buy  = lambda s, q: buys.append((s, q)),
            place_sell = lambda s, q: sells.append((s, q)),
        )
        return mt, buys, sells

    def test_start_creates_active_trader(self):
        mt, buys, _ = self._make_mt()
        cfg = TraderConfig(stop_value=99.0, poll_interval=0.01)
        mt.start("AAPL", 1, config=cfg)
        wait_for_state(mt._traders["AAPL"], TraderState.WATCHING, timeout=3)
        assert mt._traders["AAPL"].status.state == TraderState.WATCHING
        mt.stop_all()

    def test_duplicate_symbol_raises(self):
        mt, _, _ = self._make_mt()
        cfg = TraderConfig(stop_value=99.0, poll_interval=0.01)
        mt.start("AAPL", 1, config=cfg)
        wait_for_state(mt._traders["AAPL"], TraderState.WATCHING, timeout=3)
        with pytest.raises(RuntimeError, match="already active"):
            mt.start("AAPL", 1, config=cfg)
        mt.stop_all()

    def test_two_symbols_run_concurrently(self):
        mt, buys, _ = self._make_mt()
        cfg = TraderConfig(stop_value=99.0, poll_interval=0.01)
        mt.start("AAPL", 1, config=cfg)
        mt.start("MSFT", 1, config=cfg)
        wait_for_state(mt._traders["AAPL"], TraderState.WATCHING, timeout=3)
        wait_for_state(mt._traders["MSFT"], TraderState.WATCHING, timeout=3)
        assert mt._traders["AAPL"].status.state == TraderState.WATCHING
        assert mt._traders["MSFT"].status.state == TraderState.WATCHING
        mt.stop_all()

    def test_stop_all_halts_all_traders(self):
        mt, _, _ = self._make_mt()
        cfg = TraderConfig(stop_value=99.0, poll_interval=0.01)
        mt.start("A", 1, config=cfg)
        mt.start("B", 1, config=cfg)
        for sym in ("A", "B"):
            wait_for_state(mt._traders[sym], TraderState.WATCHING, timeout=3)
        mt.stop_all()
        time.sleep(0.1)
        for sym in ("A", "B"):
            assert mt._traders[sym].status.state in (
                TraderState.STOPPED, TraderState.SOLD, TraderState.ERROR)

    def test_daily_loss_limit_blocks_new_trades(self):
        mt, _, _ = self._make_mt(drift=-50.0)  # strong drift down → quick loss
        cfg = TraderConfig(stop_value=0.1, poll_interval=0.01)
        mt._daily_loss_limit = 0.01   # tiny limit — easily exceeded
        mt.start("X", 10, config=cfg)
        reached = wait_for_state(mt._traders["X"], TraderState.SOLD, timeout=5)
        assert reached
        time.sleep(0.05)   # let _on_close update realized_loss
        assert mt._realized_loss > 0
        with pytest.raises(RuntimeError, match="Daily loss limit"):
            mt.start("Y", 10, config=cfg)

    def test_statuses_reflects_all_symbols(self):
        mt, _, _ = self._make_mt()
        cfg = TraderConfig(stop_value=99.0, poll_interval=0.01)
        mt.start("P", 1, config=cfg)
        mt.start("Q", 1, config=cfg)
        for sym in ("P", "Q"):
            wait_for_state(mt._traders[sym], TraderState.WATCHING, timeout=3)
        s = mt.statuses()
        assert "P" in s and "Q" in s
        mt.stop_all()

    def test_statuses_returns_snapshot_copies(self):
        """statuses() must return independent copies (modifying the dict does not mutate trader)."""
        mt, _, _ = self._make_mt()
        cfg = TraderConfig(stop_value=99.0, poll_interval=0.01)
        mt.start("SNAP", 1, config=cfg)
        wait_for_state(mt._traders["SNAP"], TraderState.WATCHING, timeout=3)
        s1 = mt.statuses()
        s2 = mt.statuses()
        # Two calls must return distinct dict objects
        assert s1 is not s2
        # Log list must be a copy, not the live list
        assert s1["SNAP"].log is not mt._traders["SNAP"].status.log
        mt.stop_all()

    def test_set_threshold_updates_watching_position(self):
        """set_threshold changes the stop_value for a WATCHING position."""
        mt, _, _ = self._make_mt()
        cfg = TraderConfig(stop_value=5.0, poll_interval=0.01)
        mt.start("TH", 1, config=cfg)
        wait_for_state(mt._traders["TH"], TraderState.WATCHING, timeout=3)
        mt.set_threshold("TH", 2.5)
        assert mt._traders["TH"].status.config.stop_value == pytest.approx(2.5)
        mt.stop_all()

    def test_set_threshold_noop_for_unknown_symbol(self):
        """set_threshold on a symbol that doesn't exist must not raise."""
        mt, _, _ = self._make_mt()
        mt.set_threshold("UNKNOWN", 1.0)   # should be a no-op

    def test_set_threshold_noop_when_not_watching(self):
        """set_threshold must be ignored if the trader is not in WATCHING state."""
        mt, _, _ = self._make_mt()
        # Trader not started yet — not present in _traders at all
        mt.set_threshold("IDLE", 1.0)   # must not raise


# ── ReplayPriceFeed ───────────────────────────────────────────────────────────

class TestReplayPriceFeed:
    """Tests for ReplayPriceFeed using monkeypatched _fetch to avoid API calls."""

    def _make_feed(self, prices, speed=100.0, start_time=None, end_time=None):
        """Build a ReplayPriceFeed with pre-loaded prices (no API call)."""
        from datetime import time as dtime
        feed = object.__new__(ReplayPriceFeed)
        import threading
        feed.symbol   = "TEST"
        feed.speed    = speed
        feed._prices  = list(prices)
        feed._times   = [f"2024-01-02 09:{i:02d}:00" for i in range(len(prices))]
        feed._idx     = 0
        feed._lock    = threading.Lock()
        return feed

    def test_returns_prices_in_sequence(self):
        feed = self._make_feed([10.0, 20.0, 30.0])
        assert feed.get_price("X") == 10.0
        assert feed.get_price("X") == 20.0
        assert feed.get_price("X") == 30.0

    def test_exhausted_after_last_bar(self):
        feed = self._make_feed([1.0, 2.0])
        feed.get_price("X")
        feed.get_price("X")
        assert feed.exhausted

    def test_returns_last_price_when_exhausted(self):
        feed = self._make_feed([5.0, 9.0])
        feed.get_price("X")
        feed.get_price("X")   # now exhausted
        assert feed.get_price("X") == 9.0   # returns last, doesn't advance

    def test_recommended_poll_interval(self):
        feed = self._make_feed([1.0], speed=200.0)
        assert abs(feed.recommended_poll_interval - 60.0 / 200.0) < 1e-9

    def test_progress_fraction(self):
        feed = self._make_feed([1.0, 2.0, 3.0, 4.0])
        feed.get_price("X")
        feed.get_price("X")
        assert abs(feed.progress - 0.5) < 1e-9

    def test_reset_restarts_sequence(self):
        feed = self._make_feed([7.0, 8.0, 9.0])
        feed.get_price("X")
        feed.get_price("X")
        feed.reset()
        assert feed.get_price("X") == 7.0

    def test_bar_count(self):
        feed = self._make_feed([1.0] * 13)
        assert feed.bar_count == 13

    def test_current_bar_advances(self):
        feed = self._make_feed([1.0, 2.0, 3.0])
        assert feed.current_bar == 0
        feed.get_price("X")
        assert feed.current_bar == 1
