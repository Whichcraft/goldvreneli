"""
AutoTrader — advanced trailing-stop position manager.

Entry modes:
  MARKET  — immediate market order (default)
  LIMIT   — wait for price ≤ limit_price within timeout, then market buy
  SCALE   — buy in N equal tranches at configurable intervals

Stop modes:
  PCT  — sell when price drops threshold_pct % below peak (default)
  ATR  — sell when price drops N × ATR(14) dollars below peak

Additional exit features:
  Take-profit  — sell a configurable fraction of the position when profit hits target %
  Breakeven    — once up X %, raise the stop floor to entry price
  Time stop    — exit after N minutes regardless of price

Risk sizing helper:
  size_from_risk(equity, risk_pct, entry_price, stop_distance) → int

Multi-position management:
  MultiTrader — concurrent AutoTrader instances keyed by symbol, with
                optional daily loss limit.
"""

import dataclasses
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)
logging.getLogger(__name__).addHandler(logging.NullHandler())


# ── Enums ─────────────────────────────────────────────────────────────────────

class TraderState(Enum):
    IDLE      = "idle"
    ENTERING  = "entering"   # executing entry phase (limit/scale)
    WATCHING  = "watching"   # in position, monitoring
    SOLD      = "sold"
    STOPPED   = "stopped"
    ERROR     = "error"


class StopMode(Enum):
    PCT = "pct"   # fixed % trailing stop
    ATR = "atr"   # N × ATR(14) dollar trailing stop


class EntryMode(Enum):
    MARKET = "market"
    LIMIT  = "limit"
    SCALE  = "scale"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class TraderConfig:
    # Stop
    stop_mode:             StopMode = StopMode.PCT
    stop_value:            float    = 0.5     # % for PCT; N multiplier for ATR
    poll_interval:         float    = 5.0

    # Entry
    entry_mode:            EntryMode = EntryMode.MARKET
    limit_price:           float     = 0.0
    limit_timeout_s:       float     = 60.0
    scale_tranches:        int       = 1
    scale_interval_s:      float     = 30.0

    # Take-profit
    tp_trigger_pct:        float     = 0.0   # 0 = disabled
    tp_qty_fraction:       float     = 1.0   # fraction to sell (1.0 = close all)

    # Breakeven stop
    breakeven_trigger_pct: float     = 0.0   # 0 = disabled

    # Time stop
    time_stop_minutes:     float     = 0.0   # 0 = disabled


@dataclass
class TradeLog:
    timestamp: datetime
    action:    str    # BUY | SELL | PEAK | STOP | TAKE_PROFIT | BREAKEVEN | TIME_STOP | CANCEL | INFO | ERROR
    price:     float
    note:      str = ""


@dataclass
class AutoTraderStatus:
    # Core state
    state:          TraderState = TraderState.IDLE
    symbol:         str         = ""
    qty:            int         = 1
    qty_remaining:  int         = 0

    # Prices
    entry_price:    float = 0.0
    peak_price:     float = 0.0
    current_price:  float = 0.0
    stop_floor:     float = 0.0   # absolute stop price (computed each tick)

    # Metrics (kept for UI compat)
    threshold_pct:  float = 0.5   # kept in sync: % equiv of current stop distance from peak
    drawdown_pct:   float = 0.0
    pnl:            float = 0.0

    # ATR
    atr_value:      float = 0.0

    # Take-profit
    tp_price:       float = 0.0
    tp_executed:    bool  = False
    realized_pnl:   float = 0.0   # cumulative P&L from partial exits (e.g. take-profit)

    # Breakeven
    breakeven_active: bool = False

    # Scale entry
    tranches_filled:  int = 0

    # Config snapshot and timing
    config:         TraderConfig        = field(default_factory=TraderConfig)
    entry_time:     Optional[datetime]  = None
    log:            List[TradeLog]      = field(default_factory=list)


# ── Standalone helpers ────────────────────────────────────────────────────────

def size_from_risk(
    equity:        float,
    risk_pct:      float,
    entry_price:   float,
    stop_distance: float,
) -> int:
    """
    Calculate share qty that risks exactly risk_pct % of equity.

    Parameters
    ----------
    equity        : account equity in dollars
    risk_pct      : e.g. 1.0 means risk 1 % of equity
    entry_price   : expected fill price per share
    stop_distance : dollar distance from entry to stop (e.g. entry * threshold/100,
                    or ATR × multiplier)

    Returns at least 1 share.
    """
    if stop_distance <= 0 or entry_price <= 0:
        raise ValueError("stop_distance and entry_price must be positive")
    risk_dollars = equity * risk_pct / 100.0
    return max(1, int(risk_dollars / stop_distance))


def _calc_atr(bars: pd.DataFrame, period: int = 14) -> float:
    """
    Compute ATR(period) from a DataFrame with high / low / close columns.
    Raises ValueError if fewer than period + 1 rows.
    """
    if len(bars) < period + 1:
        raise ValueError(f"Need at least {period + 1} bars; got {len(bars)}")
    high  = bars["high"]
    low   = bars["low"]
    close = bars["close"]
    prev  = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev).abs(),
        (low  - prev).abs(),
    ], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


# ── AutoTrader ────────────────────────────────────────────────────────────────

class AutoTrader:
    """
    Single-symbol trailing-stop trader.

    Parameters
    ----------
    get_price     : callable(symbol) -> float
    place_buy     : callable(symbol, qty)
    place_sell    : callable(symbol, qty)
    get_bars      : optional callable(symbol) -> DataFrame with high/low/close
                    Required when stop_mode == ATR.
    threshold_pct : legacy default stop % (overridden by TraderConfig)
    poll_interval : legacy default poll interval (overridden by TraderConfig)
    """

    # ATR bars cache TTL in seconds (avoid hitting the API every poll tick)
    _ATR_CACHE_TTL = 300

    def __init__(
        self,
        get_price:     Callable[[str], float],
        place_buy:     Callable[[str, int], None],
        place_sell:    Callable[[str, int], None],
        get_bars:      Optional[Callable] = None,
        threshold_pct: float = 0.5,
        poll_interval: float = 5.0,
    ):
        self._get_price  = get_price
        self._place_buy  = place_buy
        self._place_sell = place_sell
        self._get_bars   = get_bars
        self._default_threshold = threshold_pct
        self._default_poll      = poll_interval

        self.status      = AutoTraderStatus()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # ATR bars cache
        self._bars_cache:      Optional[pd.DataFrame] = None
        self._bars_fetched_at: float                  = 0.0

        # Optional callback wired by MultiTrader to track realized P&L
        self._on_close: Optional[Callable[[float], None]] = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(
        self,
        symbol:        str,
        qty:           int,
        config:        Optional[TraderConfig] = None,
        # Legacy kwargs
        threshold_pct: Optional[float] = None,
        poll_interval: Optional[float] = None,
    ):
        """Buy `qty` shares of `symbol` and begin monitoring."""
        if qty < 1:
            raise ValueError(f"qty must be at least 1, got {qty}")
        if not symbol or not symbol.strip():
            raise ValueError("symbol must not be empty")
        if self.status.state in (TraderState.ENTERING, TraderState.WATCHING):
            raise RuntimeError(f"AutoTrader already active ({self.status.state.value}).")

        if config is None:
            config = TraderConfig(
                stop_value    = threshold_pct if threshold_pct is not None else self._default_threshold,
                poll_interval = poll_interval if poll_interval is not None else self._default_poll,
            )
        else:
            # Always work on a private copy so mutations in _run() (e.g. disabling
            # take-profit after it fires) never affect the caller's TraderConfig.
            config = dataclasses.replace(config)

        if config.stop_mode == StopMode.ATR and self._get_bars is None:
            raise ValueError("ATR stop mode requires a get_bars callable.")

        self.status = AutoTraderStatus(
            symbol       = symbol.upper(),
            qty          = qty,
            qty_remaining= qty,
            config       = config,
            entry_time   = datetime.now(),
        )
        self._stop_event.clear()
        self._bars_cache      = None
        self._bars_fetched_at = 0.0

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"AutoTrader started: {symbol} qty={qty} stop={config.stop_mode.value}/{config.stop_value}")

    def stop(self):
        """Stop monitoring without selling the position."""
        self._stop_event.set()
        self.status.state = TraderState.STOPPED
        self._log("STOP", self.status.current_price, "Manually stopped — position remains open")

    def set_threshold(self, pct: float):
        """Adjust trailing stop % live (PCT mode only)."""
        self.status.config.stop_value = pct
        self.status.threshold_pct     = pct

    def attach(
        self,
        symbol:      str,
        qty:         int,
        entry_price: float,
        config:      Optional[TraderConfig] = None,
    ):
        """
        Attach to an already-held position — skip the buy order and start
        monitoring immediately from *entry_price*.

        Useful when the app restarts with open broker positions that should be
        managed with a trailing stop.
        """
        if qty < 1:
            raise ValueError(f"qty must be at least 1, got {qty}")
        if not symbol or not symbol.strip():
            raise ValueError("symbol must not be empty")
        if self.status.state in (TraderState.ENTERING, TraderState.WATCHING):
            raise RuntimeError(f"AutoTrader already active ({self.status.state.value}).")

        config = dataclasses.replace(config) if config else TraderConfig()

        self.status = AutoTraderStatus(
            symbol        = symbol.upper(),
            qty           = qty,
            qty_remaining = qty,
            entry_price   = entry_price,
            peak_price    = entry_price,
            config        = config,
            entry_time    = datetime.now(),
            state         = TraderState.WATCHING,  # skip entry phase in _run()
        )
        self._stop_event.clear()
        self._bars_cache      = None
        self._bars_fetched_at = 0.0

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"AutoTrader attached: {symbol} qty={qty} entry=${entry_price:.2f}")

    # ── Internal: entry ────────────────────────────────────────────────────────

    def _do_market_entry(self) -> bool:
        price = self._get_price(self.status.symbol)
        self._place_buy(self.status.symbol, self.status.qty)
        self.status.entry_price     = price
        self.status.peak_price      = price
        self.status.qty_remaining   = self.status.qty
        self.status.tranches_filled = 1
        self._log("BUY", price, f"Market: {self.status.qty} × {self.status.symbol} @ ${price:.2f}")
        return True

    def _do_limit_entry(self) -> bool:
        cfg      = self.status.config
        deadline = time.time() + cfg.limit_timeout_s
        self._log("INFO", cfg.limit_price,
                  f"Waiting for price ≤ ${cfg.limit_price:.2f} (timeout {cfg.limit_timeout_s:.0f}s)…")
        while time.time() < deadline and not self._stop_event.is_set():
            price = self._get_price(self.status.symbol)
            self.status.current_price = price
            if price <= cfg.limit_price:
                self._place_buy(self.status.symbol, self.status.qty)
                self.status.entry_price     = price
                self.status.peak_price      = price
                self.status.qty_remaining   = self.status.qty
                self.status.tranches_filled = 1
                self._log("BUY", price,
                          f"Limit fill: {self.status.qty} × {self.status.symbol} @ ${price:.2f}")
                return True
            time.sleep(cfg.poll_interval)
        self._log("CANCEL", 0.0,
                  f"Limit entry timed out after {cfg.limit_timeout_s:.0f}s — no fill")
        return False

    def _do_scale_entry(self) -> bool:
        cfg  = self.status.config
        n    = max(1, cfg.scale_tranches)
        base = self.status.qty // n
        rem  = self.status.qty - base * n   # extra share goes to first tranche

        total_cost   = 0.0
        total_filled = 0

        for i in range(n):
            if self._stop_event.is_set():
                break
            tranche_qty = base + (rem if i == 0 else 0)
            if tranche_qty <= 0:
                continue
            price = self._get_price(self.status.symbol)
            self.status.current_price = price
            self._place_buy(self.status.symbol, tranche_qty)
            total_cost   += price * tranche_qty
            total_filled += tranche_qty
            self.status.tranches_filled = i + 1
            if i == 0:
                self.status.peak_price = price
            self._log("BUY", price, f"Tranche {i + 1}/{n}: {tranche_qty} @ ${price:.2f}")
            if i < n - 1 and not self._stop_event.is_set():
                time.sleep(cfg.scale_interval_s)

        if total_filled == 0:
            return False
        self.status.qty           = total_filled
        self.status.qty_remaining = total_filled
        self.status.entry_price   = total_cost / total_filled
        # Refresh peak after all tranches filled
        try:
            self.status.peak_price = max(
                self.status.peak_price,
                self._get_price(self.status.symbol),
            )
        except Exception:
            pass
        return True

    # ── Internal: ATR ──────────────────────────────────────────────────────────

    def _get_atr(self) -> float:
        """Return cached ATR value, refreshing if stale."""
        now = time.time()
        if self._bars_cache is None or (now - self._bars_fetched_at) > self._ATR_CACHE_TTL:
            try:
                bars = self._get_bars(self.status.symbol)
                if bars is not None and len(bars) >= 15:
                    self._bars_cache      = bars
                    self._bars_fetched_at = now
            except Exception as e:
                logger.warning(f"get_bars failed: {e}")

        if self._bars_cache is None:
            return 0.0
        try:
            return _calc_atr(self._bars_cache)
        except Exception:
            return 0.0

    # ── Internal: stop price ───────────────────────────────────────────────────

    def _update_stop_floor(self):
        cfg = self.status.config
        if cfg.stop_mode == StopMode.ATR:
            atr = self._get_atr()
            self.status.atr_value = atr
            if atr > 0:
                dist = atr * cfg.stop_value
                raw  = self.status.peak_price - dist
                # Keep threshold_pct in sync for the UI progress bar
                self.status.threshold_pct = (dist / self.status.peak_price * 100) if self.status.peak_price else cfg.stop_value
            else:
                # ATR unavailable — fall back to PCT
                raw = self.status.peak_price * (1 - cfg.stop_value / 100)
                self.status.threshold_pct = cfg.stop_value
        else:
            raw = self.status.peak_price * (1 - cfg.stop_value / 100)
            self.status.threshold_pct = cfg.stop_value

        # Breakeven floor
        if self.status.breakeven_active:
            raw = max(raw, self.status.entry_price)

        self.status.stop_floor = raw

    # ── Internal: main loop ────────────────────────────────────────────────────

    def _run(self):
        cfg = self.status.config
        s   = self.status

        # ── Entry phase (skipped when attach() pre-set state=WATCHING) ───────
        if s.state != TraderState.WATCHING:
            s.state = TraderState.ENTERING

            if cfg.entry_mode == EntryMode.MARKET:
                entered = self._do_market_entry()
            elif cfg.entry_mode == EntryMode.LIMIT:
                entered = self._do_limit_entry()
            else:  # SCALE
                entered = self._do_scale_entry()

            if not entered or self._stop_event.is_set():
                s.state = TraderState.STOPPED
                return

            s.state = TraderState.WATCHING
        else:
            # Attach path — record initial state so the trade log isn't empty
            self._log("INFO", s.entry_price,
                      f"Attached to existing position: {s.qty} × {s.symbol} @ ${s.entry_price:.2f}")

        # Initial ATR fetch and stop floor
        self._update_stop_floor()

        # Take-profit price
        if cfg.tp_trigger_pct > 0:
            s.tp_price = s.entry_price * (1 + cfg.tp_trigger_pct / 100)
            self._log("INFO", s.tp_price,
                      f"Take-profit set @ ${s.tp_price:.2f} (+{cfg.tp_trigger_pct}%)"
                      f" — will sell {cfg.tp_qty_fraction * 100:.0f}% of position")

        if cfg.stop_mode == StopMode.ATR and s.atr_value > 0:
            self._log("INFO", s.entry_price,
                      f"ATR(14) = ${s.atr_value:.2f} → stop distance ${s.atr_value * cfg.stop_value:.2f}")

        # ── Monitor loop ─────────────────────────────────────────────────────
        while not self._stop_event.is_set():
            try:
                price = self._get_price(s.symbol)
                s.current_price = price
                s.pnl           = (price - s.entry_price) * s.qty_remaining + s.realized_pnl

                # New peak
                if price > s.peak_price:
                    s.peak_price = price
                    self._update_stop_floor()
                    self._log("PEAK", price, f"New peak ${price:.2f} | stop floor ${s.stop_floor:.2f}")

                # Breakeven activation
                if (not s.breakeven_active
                        and cfg.breakeven_trigger_pct > 0
                        and price >= s.entry_price * (1 + cfg.breakeven_trigger_pct / 100)):
                    s.breakeven_active = True
                    self._update_stop_floor()
                    self._log("BREAKEVEN", price,
                              f"Breakeven active — stop floor raised to entry ${s.entry_price:.2f}")

                # Drawdown % from peak (for UI progress bar)
                s.drawdown_pct = (s.peak_price - price) / s.peak_price * 100 if s.peak_price else 0.0

                # ── Take-profit ───────────────────────────────────────────
                if cfg.tp_trigger_pct > 0 and not s.tp_executed and price >= s.tp_price:
                    sell_qty = min(
                        s.qty_remaining,
                        max(1, int(s.qty_remaining * cfg.tp_qty_fraction)),
                    )
                    self._place_sell(s.symbol, sell_qty)
                    s.qty_remaining -= sell_qty
                    s.tp_executed    = True
                    tp_pnl           = (price - s.entry_price) * sell_qty
                    s.realized_pnl  += tp_pnl
                    self._log("TAKE_PROFIT", price,
                              f"Take-profit @ ${price:.2f} | sold {sell_qty} shares | partial P&L ${tp_pnl:.2f}")
                    if s.qty_remaining <= 0:
                        s.pnl   = s.realized_pnl   # all shares exited via TP
                        s.state = TraderState.SOLD
                        if self._on_close:
                            self._on_close(s.pnl)
                        self._stop_event.set()
                        break
                    # Disable TP; trail remaining shares
                    cfg.tp_trigger_pct = 0

                # ── Time stop ─────────────────────────────────────────────
                if (cfg.time_stop_minutes > 0
                        and s.entry_time
                        and (datetime.now() - s.entry_time).total_seconds() >= cfg.time_stop_minutes * 60):
                    self._place_sell(s.symbol, s.qty_remaining)
                    s.state = TraderState.SOLD
                    self._log("TIME_STOP", price,
                              f"Time stop after {cfg.time_stop_minutes:.0f}min | P&L ${s.pnl:.2f}")
                    if self._on_close:
                        self._on_close(s.pnl)
                    self._stop_event.set()
                    break

                # ── Trailing stop ─────────────────────────────────────────
                if price <= s.stop_floor:
                    self._place_sell(s.symbol, s.qty_remaining)
                    s.state = TraderState.SOLD
                    self._log("SELL", price,
                              f"Trailing stop @ ${price:.2f} ({s.drawdown_pct:.2f}% from peak ${s.peak_price:.2f})"
                              f" | P&L ${s.pnl:.2f}")
                    if self._on_close:
                        self._on_close(s.pnl)
                    self._stop_event.set()
                    break

            except Exception as e:
                logger.error(f"AutoTrader [{s.symbol}] error: {e}")
                s.state = TraderState.ERROR
                self._log("ERROR", 0.0, str(e))
                self._stop_event.set()
                break

            time.sleep(cfg.poll_interval)

    def _log(self, action: str, price: float, note: str = ""):
        entry = TradeLog(timestamp=datetime.now(), action=action, price=price, note=note)
        self.status.log.append(entry)
        logger.info(f"[{self.status.symbol}][{action}] {note}")


# ── size_from_risk (already defined above) ────────────────────────────────────


# ── MultiTrader ───────────────────────────────────────────────────────────────

class MultiTrader:
    """
    Manages multiple concurrent AutoTrader instances keyed by symbol.

    Parameters
    ----------
    get_price          : callable(symbol) -> float
    place_buy          : callable(symbol, qty)
    place_sell         : callable(symbol, qty)
    get_bars           : optional callable(symbol) -> DataFrame
    daily_loss_limit   : halt new trades when cumulative realized losses exceed
                         this dollar amount. 0 = disabled.
    """

    def __init__(
        self,
        get_price:        Callable[[str], float],
        place_buy:        Callable[[str, int], None],
        place_sell:       Callable[[str, int], None],
        get_bars:         Optional[Callable] = None,
        daily_loss_limit: float = 0.0,
    ):
        self._get_price        = get_price
        self._place_buy        = place_buy
        self._place_sell       = place_sell
        self._get_bars         = get_bars
        self._daily_loss_limit = daily_loss_limit
        self._traders:         Dict[str, AutoTrader] = {}
        self._realized_loss:   float                 = 0.0
        self._loss_lock        = threading.Lock()

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(
        self,
        symbol:        str,
        qty:           int,
        config:        Optional[TraderConfig] = None,
        threshold_pct: Optional[float]        = None,
        poll_interval: Optional[float]        = None,
        on_close:      Optional[Callable[[float], None]] = None,
    ) -> AutoTrader:
        """
        Start a new position. Raises RuntimeError if symbol already WATCHING
        or daily loss limit is breached.

        on_close : optional callback(pnl) called when the position closes,
                   in addition to the internal loss-limit accounting.
        """
        symbol = symbol.upper().strip()
        if not symbol:
            raise ValueError("symbol must not be empty")
        if qty < 1:
            raise ValueError(f"qty must be at least 1, got {qty}")

        # Atomic check-and-reserve under lock to prevent races
        with self._loss_lock:
            if symbol in self._traders and self._traders[symbol].status.state in (
                TraderState.ENTERING, TraderState.WATCHING
            ):
                raise RuntimeError(f"{symbol} is already active.")
            if self._daily_loss_limit > 0 and self._realized_loss >= self._daily_loss_limit:
                raise RuntimeError(
                    f"Daily loss limit ${self._daily_loss_limit:,.2f} reached "
                    f"(realized losses ${self._realized_loss:,.2f}) — no new trades."
                )

            at = AutoTrader(
                get_price  = self._get_price,
                place_buy  = self._place_buy,
                place_sell = self._place_sell,
                get_bars   = self._get_bars,
            )

            def _on_close(pnl: float):
                if pnl < 0:
                    with self._loss_lock:
                        self._realized_loss += abs(pnl)
                if on_close:
                    on_close(pnl)

            at._on_close = _on_close
            self._traders[symbol] = at   # reserve slot before starting thread

        at.start(symbol, qty, config=config,
                 threshold_pct=threshold_pct, poll_interval=poll_interval)

        logger.info(f"MultiTrader: started {symbol} qty={qty}")
        return at

    def attach(
        self,
        symbol:      str,
        qty:         int,
        entry_price: float,
        config:      Optional[TraderConfig] = None,
        on_close:    Optional[Callable[[float], None]] = None,
    ) -> "AutoTrader":
        """
        Attach trailing-stop monitoring to an existing broker position without
        placing a buy order.  Useful when the app restarts with open positions.
        """
        symbol = symbol.upper().strip()
        if not symbol:
            raise ValueError("symbol must not be empty")
        if qty < 1:
            raise ValueError(f"qty must be at least 1, got {qty}")

        with self._loss_lock:
            if symbol in self._traders and self._traders[symbol].status.state in (
                TraderState.ENTERING, TraderState.WATCHING
            ):
                raise RuntimeError(f"{symbol} is already active.")

            at = AutoTrader(
                get_price  = self._get_price,
                place_buy  = self._place_buy,
                place_sell = self._place_sell,
                get_bars   = self._get_bars,
            )

            def _on_close(pnl: float):
                if pnl < 0:
                    with self._loss_lock:
                        self._realized_loss += abs(pnl)
                if on_close:
                    on_close(pnl)

            at._on_close = _on_close
            self._traders[symbol] = at

        at.attach(symbol, qty, entry_price, config=config)
        logger.info(f"MultiTrader: attached {symbol} qty={qty} entry=${entry_price:.2f}")
        return at

    def stop(self, symbol: str):
        """Stop a single position by symbol (does not sell)."""
        symbol = symbol.upper()
        with self._loss_lock:
            at = self._traders.get(symbol)
        if at and at.status.state == TraderState.WATCHING:
            at.stop()

    def stop_all(self):
        """Stop all currently watching positions."""
        with self._loss_lock:
            traders = list(self._traders.values())
        for at in traders:
            if at.status.state == TraderState.WATCHING:
                at.stop()

    def statuses(self) -> Dict[str, AutoTraderStatus]:
        """Return a snapshot of all traders' statuses."""
        with self._loss_lock:
            return {sym: at.status for sym, at in self._traders.items()}

    def active_symbols(self) -> List[str]:
        """Return symbols currently in WATCHING state."""
        with self._loss_lock:
            return [sym for sym, at in self._traders.items()
                    if at.status.state == TraderState.WATCHING]

    def all_logs(self) -> List[TradeLog]:
        """Merge and sort all trade logs by timestamp."""
        with self._loss_lock:
            traders = list(self._traders.values())
        logs: List[TradeLog] = []
        for at in traders:
            logs.extend(at.status.log)
        logs.sort(key=lambda e: e.timestamp)
        return logs

    def unrealized_pnl(self) -> float:
        """Sum of current unrealized P&L across all active positions."""
        with self._loss_lock:
            return sum(at.status.pnl for at in self._traders.values()
                       if at.status.state in (TraderState.ENTERING, TraderState.WATCHING))

    def daily_pnl(self) -> float:
        """Deprecated alias for unrealized_pnl()."""
        return self.unrealized_pnl()

    def realized_losses(self) -> float:
        """Cumulative realized losses today (positive number)."""
        with self._loss_lock:
            return self._realized_loss
