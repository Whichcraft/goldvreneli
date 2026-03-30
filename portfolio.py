"""
PortfolioManager — maintains N concurrent scanner-driven trailing-stop positions.

Each slot invests `slot_pct` % of current equity in a scanner top pick.
On position close (trailing stop), the manager rescans (if stale) and
opens the next best candidate automatically.

Typical usage
-------------
    pm = PortfolioManager(
        data_client   = data_client,
        get_price_fn  = alpaca_get_price,
        place_buy_fn  = alpaca_buy,
        place_sell_fn = alpaca_sell,
        get_bars_fn   = alpaca_get_bars,
        get_equity_fn = lambda: float(trading_client.get_account().equity),
        target_slots  = 10,
        slot_pct      = 10.0,
    )
    pm.start()
"""

import logging
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional

from autotrader import MultiTrader, TraderConfig, TraderState

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Rescan when candidates are older than this (seconds)
_SCAN_MAX_AGE_S = 1800


class PortfolioManager:
    """
    Maintains up to `target_slots` concurrent AutoTrader positions, each
    sized at `slot_pct` % of account equity.  When a position closes via
    trailing stop the manager automatically opens the next scanner pick.

    Parameters
    ----------
    data_client      : Alpaca StockHistoricalDataClient
    get_price_fn     : callable(symbol) -> float
    place_buy_fn     : callable(symbol, qty)
    place_sell_fn    : callable(symbol, qty)
    get_bars_fn      : callable(symbol) -> DataFrame  (None if PCT stop only)
    get_equity_fn    : callable() -> float
    target_slots     : maximum simultaneous positions (default 10)
    slot_pct         : % of equity per slot (default 10.0; ignored when slot_dollar > 0)
    slot_dollar      : fixed $ amount per slot (0 = use slot_pct instead)
    trader_config    : TraderConfig applied to every position
    scan_filters     : scanner.ScanFilters instance (None = scanner defaults)
    daily_loss_limit : halt new entries after this cumulative loss ($, 0 = off)
    """

    def __init__(
        self,
        data_client,
        get_price_fn:     Callable[[str], float],
        place_buy_fn:     Callable[[str, int], None],
        place_sell_fn:    Callable[[str, int], None],
        get_bars_fn:      Optional[Callable],
        get_equity_fn:    Callable[[], float],
        target_slots:     int                    = 10,
        slot_pct:         float                  = 10.0,
        slot_dollar:      float                  = 0.0,
        trader_config:    Optional[TraderConfig] = None,
        scan_filters                             = None,
        daily_loss_limit: float                  = 0.0,
    ):
        self._data_client  = data_client
        self._get_price    = get_price_fn
        self._get_equity   = get_equity_fn
        self._target_slots = target_slots
        self._slot_pct     = slot_pct
        self._slot_dollar  = slot_dollar   # if > 0 overrides slot_pct
        self._config       = trader_config or TraderConfig()
        self._scan_filters = scan_filters

        self._multi = MultiTrader(
            get_price        = get_price_fn,
            place_buy        = place_buy_fn,
            place_sell       = place_sell_fn,
            get_bars         = get_bars_fn,
            daily_loss_limit = daily_loss_limit,
        )

        self._running:        bool                  = False
        self._candidates:     List[str]             = []
        self._candidates_ts:  Optional[datetime]    = None
        self._lock            = threading.Lock()
        self._scan_lock       = threading.Lock()   # prevents concurrent rescans
        self._log_entries:    List[Dict]            = []
        self._session_pnl:    float                 = 0.0

    # ── Public API ─────────────────────────────────────────────────────────────

    def _slot_label(self) -> str:
        if self._slot_dollar > 0:
            return f"${self._slot_dollar:,.0f}/slot"
        return f"{self._slot_pct:.0f}% of equity/slot"

    def start(self):
        """Run initial scan and fill all empty slots sequentially (one at a time)."""
        if self._running:
            return
        self._running = True
        self._log(f"Started (sequential) — {self._target_slots} slots, {self._slot_label()}")
        threading.Thread(target=self._fill_empty_slots, daemon=True).start()

    def start_all(self):
        """Run initial scan and open all empty slots simultaneously in parallel."""
        if self._running:
            return
        self._running = True
        self._log(f"Started (all at once) — {self._target_slots} slots, {self._slot_label()}")
        threading.Thread(target=self._fill_empty_slots_parallel, daemon=True).start()

    def stop(self):
        """Stop portfolio manager (open positions remain on the broker)."""
        if not self._running:
            return
        self._running = False
        self._multi.stop_all()
        self._log("Stopped")

    @property
    def running(self) -> bool:
        return self._running

    def active_count(self) -> int:
        """Positions in ENTERING or WATCHING state."""
        return sum(
            1 for s in self._multi.statuses().values()
            if s.state in (TraderState.ENTERING, TraderState.WATCHING)
        )

    def open_slot_count(self) -> int:
        return max(0, self._target_slots - self.active_count())

    def statuses(self) -> Dict:
        return self._multi.statuses()

    def session_pnl(self) -> float:
        with self._lock:
            return self._session_pnl

    def realized_losses(self) -> float:
        return self._multi.realized_losses()

    def log_entries(self) -> List[Dict]:
        with self._lock:
            return list(self._log_entries[-200:])

    def scan_age_s(self) -> Optional[float]:
        with self._lock:
            if self._candidates_ts is None:
                return None
            return (datetime.now() - self._candidates_ts).total_seconds()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _log(self, msg: str, level: str = "INFO"):
        entry = {"time": datetime.now().strftime("%H:%M:%S"), "level": level, "msg": msg}
        with self._lock:
            self._log_entries.append(entry)
        logger.info("[PortfolioMgr] %s", msg)

    def _rescan(self) -> List[str]:
        if not self._scan_lock.acquire(blocking=False):
            # Another scan is already in progress; wait for it to finish then
            # return whatever candidates it populated.
            with self._scan_lock:
                pass
            with self._lock:
                return list(self._candidates)
        try:
            from scanner import scan
            self._log("Scanning for candidates…")
            df = scan(
                self._data_client,
                top_n=max(50, self._target_slots * 5),
                filters=self._scan_filters,
            )
            syms = list(df.index) if not df.empty else []
            with self._lock:
                self._candidates    = syms
                self._candidates_ts = datetime.now()
            self._log(f"Scan complete — {len(syms)} candidates")
            return syms
        except Exception as e:
            self._log(f"Scan failed: {e}", "ERROR")
            return []
        finally:
            self._scan_lock.release()

    def _candidates_stale(self) -> bool:
        with self._lock:
            if not self._candidates or self._candidates_ts is None:
                return True
            return (datetime.now() - self._candidates_ts).total_seconds() > _SCAN_MAX_AGE_S

    def _next_candidate(self) -> Optional[str]:
        """Return top candidate not currently held or entering."""
        occupied = {
            sym for sym, s in self._multi.statuses().items()
            if s.state in (TraderState.ENTERING, TraderState.WATCHING)
        }
        with self._lock:
            for sym in self._candidates:
                if sym not in occupied:
                    return sym
        return None

    def _open_one_slot(self):
        if not self._running:
            return

        if self._candidates_stale():
            self._rescan()

        sym = self._next_candidate()
        if sym is None:
            self._log("No suitable candidates — slot stays empty")
            return

        try:
            price = self._get_price(sym)
            if self._slot_dollar > 0:
                qty = max(1, int(self._slot_dollar / price))
            else:
                equity = self._get_equity()
                qty    = max(1, int(equity * self._slot_pct / 100.0 / price))
        except Exception as e:
            self._log(f"Sizing error for {sym}: {e}", "ERROR")
            return

        def on_close(pnl: float, _sym=sym):
            with self._lock:
                self._session_pnl += pnl
            self._log(
                f"{_sym} closed | P&L ${pnl:+,.2f} | session ${self._session_pnl:+,.2f}",
                "INFO" if pnl >= 0 else "WARN",
            )
            if self._running:
                threading.Thread(target=self._open_one_slot, daemon=True).start()

        try:
            self._multi.start(sym, qty, config=self._config, on_close=on_close)
            self._log(f"Opened {sym} — {qty} sh @ ~${price:.2f}  (≈${qty * price:,.0f})")
        except Exception as e:
            self._log(f"Could not open {sym}: {e}", "ERROR")
            if self._running:
                threading.Thread(target=self._open_one_slot, daemon=True).start()

    def _fill_empty_slots(self):
        """Sequential startup: scan then open slots one by one."""
        self._rescan()
        for _ in range(self.open_slot_count()):
            if not self._running:
                break
            self._open_one_slot()

    def _fill_empty_slots_parallel(self):
        """Parallel startup: scan once then open all empty slots simultaneously."""
        self._rescan()
        n = self.open_slot_count()
        threads = [
            threading.Thread(target=self._open_one_slot, daemon=True)
            for _ in range(n)
        ]
        for t in threads:
            t.start()
