"""
AlpacaStreamManager — WebSocket price feed for Alpaca.

Replaces per-poll REST requests with a persistent WebSocket subscription.
The manager subscribes to symbols lazily on the first get_price() call and
caches the latest quote.  Callers should fall back to REST when get_price()
returns None (stream not yet connected or quote is stale).

Usage (goldvreneli.py):
    mgr = AlpacaStreamManager(api_key, secret_key)
    ...
    price = mgr.get_price(symbol) or alpaca_rest_get_price(symbol)
"""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_STALE_S = 5.0  # cached price older than this is treated as stale


class AlpacaStreamManager:
    """
    Maintains a live WebSocket connection to Alpaca market data.

    Subscribes to symbols on demand via get_price() — no manual subscribe()
    call needed.  The underlying StockDataStream runs in a daemon thread so
    it is cleaned up automatically when the process exits.
    """

    def __init__(self, api_key: str, secret_key: str,
                 stale_s: float = _DEFAULT_STALE_S) -> None:
        self._api_key    = api_key
        self._secret_key = secret_key
        self._stale_s    = stale_s
        # symbol → (price, monotonic timestamp)
        self._prices: dict[str, tuple[float, float]] = {}
        self._lock       = threading.Lock()
        self._subscribed: set[str] = set()
        self._stream     = None          # StockDataStream, created on first subscribe
        self._thread: Optional[threading.Thread] = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_price(self, symbol: str) -> Optional[float]:
        """Return the latest WebSocket price for *symbol*, or None.

        None means either the symbol is not yet subscribed, the stream hasn't
        received a tick yet, or the cached price is stale.  Callers should
        fall back to the REST API in that case.
        """
        self._ensure_subscribed(symbol)
        with self._lock:
            entry = self._prices.get(symbol)
        if entry is None:
            return None
        price, ts = entry
        return price if (time.monotonic() - ts) <= self._stale_s else None

    @property
    def is_alive(self) -> bool:
        """True if the background stream thread is running."""
        return bool(self._thread and self._thread.is_alive())

    def stop(self) -> None:
        """Disconnect the WebSocket and clear internal state."""
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
        self._stream   = None
        self._thread   = None
        self._subscribed.clear()
        with self._lock:
            self._prices.clear()
        logger.info("Alpaca WebSocket stopped")

    # ── Internal ───────────────────────────────────────────────────────────────

    def _ensure_subscribed(self, symbol: str) -> None:
        if symbol in self._subscribed:
            return
        self._subscribed.add(symbol)

        _sym = symbol  # capture for async closure

        async def _handler(data) -> None:
            ask = float(getattr(data, "ask_price", 0) or 0)
            bid = float(getattr(data, "bid_price", 0) or 0)
            price = ask or bid
            if price > 0:
                with self._lock:
                    self._prices[_sym] = (price, time.monotonic())

        if self._stream is None:
            # First subscription — create stream, register handler, start thread
            from alpaca.data.live import StockDataStream
            self._stream = StockDataStream(self._api_key, self._secret_key)
            self._stream.subscribe_quotes(_handler, symbol)
            self._thread = threading.Thread(
                target=self._stream.run,
                daemon=True,
                name="alpaca-ws",
            )
            self._thread.start()
            logger.info(f"Alpaca WebSocket started; subscribed to {symbol}")
        else:
            # Stream already running — dynamic subscription
            self._stream.subscribe_quotes(_handler, symbol)
            logger.debug(f"Subscribed to live quotes: {symbol}")
