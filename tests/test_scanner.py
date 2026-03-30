"""
Unit tests for scanner.py — score_symbol with fixture DataFrames.
No Alpaca API calls.
"""

import numpy as np
import pandas as pd
import pytest

from scanner import score_symbol, ScanFilters


# ── Fixture helpers ───────────────────────────────────────────────────────────

def make_bars(n=60, base=100.0, trend=0.003, vol_mult=1.0, seed=0) -> pd.DataFrame:
    """
    Build a synthetic bars DataFrame suitable for score_symbol.

    trend     : daily multiplicative drift (0.003 ≈ +0.3%/day → uptrend)
    vol_mult  : multiplier on last-day volume vs average (for volume filter)
    """
    rng     = np.random.default_rng(seed)
    closes  = np.zeros(n)
    closes[0] = base
    for i in range(1, n):
        closes[i] = closes[i - 1] * (1 + trend + rng.normal(0, 0.004))
    closes = np.maximum(closes, 1.0)

    noise  = rng.uniform(0.1, 0.5, n)
    high   = closes + noise
    low    = closes - noise
    volume = np.full(n, 2_000_000.0)
    volume[-1] = volume[-1] * vol_mult  # scale last-day volume

    return pd.DataFrame({
        "open":   closes,
        "high":   high,
        "low":    low,
        "close":  closes,
        "volume": volume,
    })


def passing_bars() -> pd.DataFrame:
    """Bars that should pass default ScanFilters (RSI ~61, gentle uptrend)."""
    return make_bars(n=60, base=50.0, trend=0.001, vol_mult=1.5, seed=1)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestScoreSymbol:
    def test_passing_bars_return_dict(self):
        bars = passing_bars()
        result = score_symbol(bars)
        assert result is not None
        assert isinstance(result, dict)

    def test_result_has_expected_keys(self):
        bars   = passing_bars()
        result = score_symbol(bars)
        assert result is not None
        for key in ("Price", "RSI", "5d Ret%", "_score"):
            assert key in result, f"Missing key: {key}"

    def test_fewer_than_52_bars_returns_none(self):
        bars = make_bars(n=51)
        assert score_symbol(bars) is None

    def test_exactly_52_bars_is_ok(self):
        bars = make_bars(n=52, base=50.0, trend=0.003, vol_mult=1.5, seed=2)
        # May or may not pass filters, but must not crash
        result = score_symbol(bars)
        # result is None (filtered) or a dict — both are valid
        assert result is None or isinstance(result, dict)

    def test_low_price_filtered_out(self):
        """Price below min_price should return None."""
        bars = make_bars(n=60, base=2.0, trend=0.003, vol_mult=1.5, seed=3)
        f    = ScanFilters(min_price=5.0)
        assert score_symbol(bars, filters=f) is None

    def test_low_volume_filtered_out(self):
        """Last-day volume below vol_mult × avg should return None."""
        bars = make_bars(n=60, base=50.0, trend=0.003, vol_mult=0.1, seed=4)
        f    = ScanFilters(vol_mult=1.0)
        assert score_symbol(bars, filters=f) is None

    def test_downtrend_filtered_out(self):
        """Strong downtrend: price falls below SMA50 → filtered."""
        bars = make_bars(n=60, base=100.0, trend=-0.01, vol_mult=1.5, seed=5)
        result = score_symbol(bars)
        assert result is None  # last price should be below sma50

    def test_spy_rets_affect_score(self):
        bars    = passing_bars()
        no_spy  = score_symbol(bars, spy_rets=None)
        spy_up  = score_symbol(bars, spy_rets={"5d": 5.0, "20d": 3.0})
        spy_dwn = score_symbol(bars, spy_rets={"5d": -5.0, "20d": -3.0})

        if no_spy is None:
            pytest.skip("bars didn't pass filters — can't compare scores")

        # Stock looks relatively stronger vs a weak SPY
        assert spy_dwn["_score"] > no_spy["_score"]
        # Stock looks weaker vs a strong SPY
        assert spy_up["_score"] < no_spy["_score"]

    def test_custom_rsi_filter(self):
        """RSI outside the custom filter range should return None."""
        bars = passing_bars()
        # Set an impossible RSI range to force rejection
        f = ScanFilters(rsi_lo=95.0, rsi_hi=100.0)
        assert score_symbol(bars, filters=f) is None

    def test_score_is_numeric(self):
        bars   = passing_bars()
        result = score_symbol(bars)
        if result is None:
            pytest.skip("bars didn't pass default filters")
        assert isinstance(result["_score"], float)

    def test_adv_filter(self):
        """Low ADV (low price × volume) should be filtered."""
        bars = make_bars(n=60, base=6.0, trend=0.003, vol_mult=1.5, seed=6)
        # With price≈6 and volume=2M, ADV≈$12M — should be fine with default $5M
        # but with $15M floor it should fail
        f = ScanFilters(min_adv_m=15.0)
        assert score_symbol(bars, filters=f) is None
