"""
AutoTrader — trailing-stop position manager.

Buys a position, tracks the peak price, and sells when the price
drops more than `threshold_pct` % from the peak (trailing stop).

Works with both Alpaca and IBKR backends.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class TraderState(Enum):
    IDLE      = "idle"
    WATCHING  = "watching"   # Entered position, monitoring
    SOLD      = "sold"
    STOPPED   = "stopped"
    ERROR     = "error"


@dataclass
class TradeLog:
    timestamp: datetime
    action: str   # BUY | SELL | PEAK | STOP
    price: float
    note: str = ""


@dataclass
class AutoTraderStatus:
    state:       TraderState = TraderState.IDLE
    symbol:      str = ""
    entry_price: float = 0.0
    peak_price:  float = 0.0
    current_price: float = 0.0
    drawdown_pct:  float = 0.0
    threshold_pct: float = 0.5
    qty:           int   = 1
    pnl:           float = 0.0
    log:           list  = field(default_factory=list)


class AutoTrader:
    """
    Trailing-stop auto-trader.

    Parameters
    ----------
    get_price   : callable(symbol) -> float   — fetch latest price
    place_buy   : callable(symbol, qty)       — execute buy
    place_sell  : callable(symbol, qty)       — execute sell
    threshold_pct : float — sell when price drops this % below peak (default 0.5)
    poll_interval : float — seconds between price checks (default 5)
    """

    def __init__(
        self,
        get_price:     Callable[[str], float],
        place_buy:     Callable[[str, int], None],
        place_sell:    Callable[[str, int], None],
        threshold_pct: float = 0.5,
        poll_interval: float = 5.0,
    ):
        self._get_price     = get_price
        self._place_buy     = place_buy
        self._place_sell    = place_sell
        self.status         = AutoTraderStatus(threshold_pct=threshold_pct)
        self._poll_interval = poll_interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event    = threading.Event()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, symbol: str, qty: int, threshold_pct: Optional[float] = None):
        """Buy `qty` shares of `symbol` and start monitoring."""
        if self.status.state == TraderState.WATCHING:
            raise RuntimeError("AutoTrader already running.")

        if threshold_pct is not None:
            self.status.threshold_pct = threshold_pct

        self.status.symbol    = symbol.upper()
        self.status.qty       = qty
        self.status.state     = TraderState.WATCHING
        self.status.log       = []
        self._stop_event.clear()

        # Buy entry
        price = self._get_price(symbol)
        self._place_buy(symbol, qty)
        self.status.entry_price = price
        self.status.peak_price  = price
        self._log("BUY", price, f"Entered {qty} × {symbol} @ ${price:.2f}")

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"AutoTrader started: {symbol} qty={qty} threshold={self.status.threshold_pct}%")

    def stop(self):
        """Stop monitoring (does NOT sell the position)."""
        self._stop_event.set()
        self.status.state = TraderState.STOPPED
        self._log("STOP", self.status.current_price, "Manually stopped — position remains open")

    def set_threshold(self, pct: float):
        """Adjust trailing stop threshold live."""
        self.status.threshold_pct = pct

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self):
        while not self._stop_event.is_set():
            try:
                price = self._get_price(self.status.symbol)
                self.status.current_price = price

                # Update peak
                if price > self.status.peak_price:
                    self.status.peak_price = price
                    self._log("PEAK", price, f"New peak ${price:.2f}")

                # Drawdown from peak
                drawdown = (self.status.peak_price - price) / self.status.peak_price * 100
                self.status.drawdown_pct = drawdown
                self.status.pnl = (price - self.status.entry_price) * self.status.qty

                # Trigger sell
                if drawdown >= self.status.threshold_pct:
                    self._place_sell(self.status.symbol, self.status.qty)
                    self.status.state = TraderState.SOLD
                    self._log(
                        "SELL", price,
                        f"Trailing stop hit: {drawdown:.2f}% drop from peak ${self.status.peak_price:.2f} | P&L ${self.status.pnl:.2f}"
                    )
                    self._stop_event.set()
                    break

            except Exception as e:
                logger.error(f"AutoTrader error: {e}")
                self.status.state = TraderState.ERROR
                self._log("ERROR", 0.0, str(e))
                self._stop_event.set()
                break

            time.sleep(self._poll_interval)

    def _log(self, action: str, price: float, note: str = ""):
        entry = TradeLog(timestamp=datetime.now(), action=action, price=price, note=note)
        self.status.log.append(entry)
        logger.info(f"[{action}] {note}")
