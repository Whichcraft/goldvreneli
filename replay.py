"""
Backtest / offline-testing utilities for AutoTrader.

Price feeds
-----------
ReplayPriceFeed    — replays Alpaca historical 1-minute bars at configurable
                     speed; each get_price() call advances one bar.
SyntheticPriceFeed — geometric random-walk generator; runs indefinitely.

Broker
------
MockBroker         — wraps any price feed, records fills to a JSON file.
                     Thread-safe; upserts the current session on every fill.

Typical wiring
--------------
    feed   = ReplayPriceFeed(data_client, "AAPL", "2024-11-15", speed=200)
    broker = MockBroker(feed.get_price, output_file="backtest_fills.json",
                        session_meta={"feed": "replay", "symbol": "AAPL"})
    at = AutoTrader(
        get_price  = broker.get_price,
        place_buy  = broker.buy,
        place_sell = broker.sell,
    )
    at._on_close = lambda pnl: broker.close(pnl)
    at.start("AAPL", qty=10, config=cfg)
"""

import json
import math
import random
import threading
import uuid
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ── ReplayPriceFeed ───────────────────────────────────────────────────────────

class ReplayPriceFeed:
    """
    Replays Alpaca historical 1-minute bars as a get_price() callable.

    Parameters
    ----------
    data_client     : Alpaca StockHistoricalDataClient
    symbol          : ticker, e.g. "AAPL"
    replay_date     : "YYYY-MM-DD" — must be a trading day
    speed           : replay speed multiplier relative to real time.
                      Use recommended_poll_interval as the AutoTrader poll_interval.
    start_time      : datetime.time in ET — first bar to include (default: full day)
    end_time        : datetime.time in ET — last bar to include
    duration_hours  : if given together with start_time, sets end_time automatically
                      (takes precedence over an explicit end_time)
    """

    def __init__(
        self,
        data_client,
        symbol:         str,
        replay_date:    str,
        speed:          float          = 100.0,
        start_time:     Optional[dtime] = None,
        end_time:       Optional[dtime] = None,
        duration_hours: Optional[float] = None,
    ):
        self.symbol = symbol.upper()
        self.speed  = speed

        # Resolve end_time from duration
        if duration_hours is not None and start_time is not None:
            dummy  = datetime(2000, 1, 1, start_time.hour, start_time.minute)
            end_dt = dummy + timedelta(hours=duration_hours)
            end_time = end_dt.time()

        self._prices: List[float] = []
        self._times:  List[str]   = []
        self._idx     = 0
        self._lock    = threading.Lock()
        self._fetch(data_client, replay_date, start_time, end_time)

    def _fetch(self, data_client, replay_date: str,
               start_time: Optional[dtime], end_time: Optional[dtime]):
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        if start_time is not None and end_time is not None and start_time >= end_time:
            raise ValueError(
                f"start_time ({start_time.strftime('%H:%M')}) must be before "
                f"end_time ({end_time.strftime('%H:%M')})"
            )

        day_start = datetime.strptime(replay_date, "%Y-%m-%d")
        day_end   = day_start + timedelta(days=1)

        req  = StockBarsRequest(
            symbol_or_symbols=self.symbol,
            timeframe=TimeFrame.Minute,
            start=day_start,
            end=day_end,
        )
        bars = data_client.get_stock_bars(req).df
        if bars.empty:
            raise ValueError(
                f"No minute bars for {self.symbol} on {replay_date}. "
                "Choose a trading day (Mon–Fri, non-holiday)."
            )
        bars = bars.reset_index(level=0, drop=True).sort_index()

        # ── Time-window filter (convert UTC index → ET for comparison) ────────
        if start_time is not None or end_time is not None:
            try:
                et_index = bars.index.tz_convert("America/New_York")
            except TypeError:
                # Index is tz-naive — assume UTC then convert
                et_index = bars.index.tz_localize("UTC").tz_convert("America/New_York")
            bar_times = et_index.time
            mask = [True] * len(bars)
            if start_time is not None:
                mask = [m and t >= start_time for m, t in zip(mask, bar_times)]
            if end_time is not None:
                mask = [m and t <= end_time   for m, t in zip(mask, bar_times)]
            bars = bars[mask]
            if bars.empty:
                st_str = start_time.strftime("%H:%M") if start_time else "open"
                et_str = end_time.strftime("%H:%M")   if end_time   else "close"
                raise ValueError(
                    f"No bars found for {self.symbol} on {replay_date} "
                    f"between {st_str} and {et_str} ET."
                )

        self._prices = bars["close"].tolist()
        self._times  = [str(ts) for ts in bars.index.tolist()]

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def recommended_poll_interval(self) -> float:
        """Seconds between AutoTrader polls to play back at self.speed × real-time."""
        return max(0.05, 60.0 / self.speed)

    @property
    def exhausted(self) -> bool:
        return self._idx >= len(self._prices)

    @property
    def progress(self) -> float:
        """Fraction of bars consumed (0.0–1.0)."""
        with self._lock:
            return self._idx / len(self._prices) if self._prices else 0.0

    @property
    def bar_count(self) -> int:
        return len(self._prices)

    @property
    def current_bar(self) -> int:
        return self._idx

    @property
    def current_time(self) -> str:
        with self._lock:
            i = min(self._idx, len(self._times) - 1)
            return self._times[i] if self._times else ""

    def reset(self):
        with self._lock:
            self._idx = 0

    # ── get_price callable ────────────────────────────────────────────────────

    def get_price(self, symbol: str) -> float:
        with self._lock:
            if self._idx < len(self._prices):
                price = self._prices[self._idx]
                self._idx += 1
                return price
            # Exhausted — return last price so the AutoTrader can finish cleanly
            return self._prices[-1] if self._prices else 0.0


# ── SyntheticPriceFeed ────────────────────────────────────────────────────────

class SyntheticPriceFeed:
    """
    Geometric random-walk price generator — runs indefinitely.

    Parameters
    ----------
    start_price    : initial price in dollars
    volatility_pct : % std-dev per step (e.g. 0.3 ≈ calm, 1.0 ≈ volatile)
    drift_pct      : % mean return per step (positive = upward bias)
    seed           : optional int for reproducibility
    """

    def __init__(
        self,
        start_price:    float = 100.0,
        volatility_pct: float = 0.5,
        drift_pct:      float = 0.0,
        seed:           Optional[int] = None,
    ):
        self.start_price    = start_price
        self.volatility_pct = volatility_pct
        self.drift_pct      = drift_pct
        self._price         = float(start_price)
        self._step          = 0
        self._rng           = random.Random(seed)
        self._lock          = threading.Lock()

    def reset(self):
        with self._lock:
            self._price = self.start_price
            self._step  = 0

    @property
    def step(self) -> int:
        return self._step

    def get_price(self, symbol: str) -> float:
        with self._lock:
            mu    = self.drift_pct / 100.0
            sigma = self.volatility_pct / 100.0
            shock = self._rng.gauss(0.0, 1.0)
            self._price *= math.exp(mu + sigma * shock)
            self._price  = max(0.01, round(self._price, 2))
            self._step  += 1
            return self._price


# ── MockBroker ────────────────────────────────────────────────────────────────

class MockBroker:
    """
    Fake broker that wraps a price feed and persists fills to a JSON file.

    The JSON file holds an array of sessions. Each run appends (or updates)
    a single session identified by a short UUID. The file is written
    atomically after every fill and on session close.

    Parameters
    ----------
    get_price_fn  : the underlying feed's get_price callable
    output_file   : path to the JSON log (created if absent)
    session_meta  : arbitrary dict stored alongside fills (symbol, feed config, etc.)
    """

    def __init__(
        self,
        get_price_fn: Callable[[str], float],
        output_file:  str = "backtest_fills.json",
        session_meta: Optional[Dict[str, Any]] = None,
    ):
        self._get_price_fn  = get_price_fn
        self._output_file   = Path(output_file)
        self._last_prices:  Dict[str, float] = {}
        self._write_lock    = threading.Lock()
        self._price_lock    = threading.Lock()

        self._output_file.parent.mkdir(parents=True, exist_ok=True)
        self._session: Dict[str, Any] = {
            "id":         str(uuid.uuid4())[:12],
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "closed_at":  None,
            "meta":       session_meta or {},
            "fills":      [],
            "pnl":        None,
        }
        # Write the session stub immediately so it appears in the history
        self._flush()

    # ── Public properties ─────────────────────────────────────────────────────

    @property
    def session_id(self) -> str:
        return self._session["id"]

    @property
    def fills(self) -> List[Dict]:
        with self._write_lock:
            return list(self._session["fills"])

    # ── Callables injected into AutoTrader ────────────────────────────────────

    def get_price(self, symbol: str) -> float:
        price = self._get_price_fn(symbol)
        with self._price_lock:
            self._last_prices[symbol] = price
        return price

    def buy(self, symbol: str, qty: int):
        self._record("BUY", symbol, qty)

    def sell(self, symbol: str, qty: int):
        self._record("SELL", symbol, qty)

    # ── Session lifecycle ─────────────────────────────────────────────────────

    def close(self, pnl: float = 0.0):
        """
        Mark session as closed with final P&L and flush to disk.
        Wire to AutoTrader._on_close:
            at._on_close = lambda pnl: broker.close(pnl)
        """
        with self._write_lock:
            self._session["closed_at"] = datetime.now().isoformat(timespec="seconds")
            self._session["pnl"]       = round(pnl, 2)
        self._flush()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _record(self, action: str, symbol: str, qty: int):
        with self._price_lock:
            price = self._last_prices.get(symbol, 0.0)
        fill = {
            "time":   datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "symbol": symbol,
            "qty":    qty,
            "price":  price,
            "value":  round(price * qty, 2),
        }
        with self._write_lock:
            self._session["fills"].append(fill)
        self._flush()

    def _flush(self):
        """Upsert this session in the JSON file (thread-safe)."""
        with self._write_lock:
            snapshot = json.loads(json.dumps(self._session))  # deep copy

        if self._output_file.exists():
            try:
                data = json.loads(self._output_file.read_text())
                if not isinstance(data, dict) or "sessions" not in data:
                    data = {"sessions": []}
            except (json.JSONDecodeError, OSError):
                data = {"sessions": []}
        else:
            data = {"sessions": []}

        sid  = snapshot["id"]
        idxs = [i for i, s in enumerate(data["sessions"]) if s.get("id") == sid]
        if idxs:
            data["sessions"][idxs[0]] = snapshot
        else:
            data["sessions"].append(snapshot)

        # Write to a temp file then rename for atomicity
        tmp = self._output_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self._output_file)


# ── Session history helper ────────────────────────────────────────────────────

def load_sessions(output_file: str) -> List[Dict]:
    """Load all sessions from a fills JSON file, newest first."""
    p = Path(output_file)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
        sessions = data.get("sessions", [])
        return list(reversed(sessions))
    except (json.JSONDecodeError, OSError):
        return []
