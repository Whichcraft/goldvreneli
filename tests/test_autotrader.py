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
    TraderConfig,
    TraderState,
    StopMode,
    EntryMode,
    size_from_risk,
    _calc_atr,
)
from replay import SyntheticPriceFeed, MockBroker


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
