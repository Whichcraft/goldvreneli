"""
core.py — Framework-agnostic application core for Goldvreneli.

Manages credentials, API client lifecycle, and trading session objects
independently of any UI framework (Streamlit, Qt, CLI, …).

Session store protocol
----------------------
Any mutable mapping that supports:

    session[key] = value
    value = session[key]
    key in session
    session.get(key, default)
    del session[key]
    session.pop(key, *args)

Both a plain Python ``dict`` and Streamlit's ``st.session_state`` satisfy
this interface — no adapter needed.

Typical Streamlit usage
-----------------------
    from core import env_get, get_alpaca_clients, get_multi_trader
    import streamlit as st

    trading_client, data_client = get_alpaca_clients(api_key, secret_key)
    mt = get_multi_trader(st.session_state,
                          get_price_fn, buy_fn, sell_fn, bars_fn)

Typical Qt / CLI usage
-----------------------
    from core import env_get, get_alpaca_clients, get_multi_trader

    session: dict = {}
    trading_client, data_client = get_alpaca_clients(api_key, secret_key)
    mt = get_multi_trader(session, get_price_fn, buy_fn, sell_fn, bars_fn)
"""

import os
from typing import Any, Callable, Dict, MutableMapping, Optional, Tuple

from dotenv import dotenv_values, load_dotenv, set_key

load_dotenv()

INSTALL_DIR: str = os.path.dirname(os.path.abspath(__file__))
ENV_FILE: str    = os.path.join(INSTALL_DIR, ".env")


# ── Credentials ───────────────────────────────────────────────────────────────

def env_get(key: str, default: str = "") -> str:
    """Read a setting from os.environ, falling back to the .env file."""
    return os.environ.get(key, dotenv_values(ENV_FILE).get(key, default))


def env_save(values: Dict[str, str]) -> None:
    """Persist key=value pairs to .env and reload into os.environ."""
    if not os.path.exists(ENV_FILE):
        open(ENV_FILE, "w").close()
    for k, v in values.items():
        set_key(ENV_FILE, k, v)
        os.environ[k] = v


# ── Alpaca clients ─────────────────────────────────────────────────────────────
# Cached at module level so clients survive page reruns in any UI framework.

_alpaca_cache: Dict[Tuple[str, str], Any] = {}


def get_alpaca_clients(api_key: str, secret_key: str) -> Tuple[Any, Any]:
    """Return (TradingClient, StockHistoricalDataClient), cached by key pair."""
    cache_key = (api_key, secret_key)
    if cache_key not in _alpaca_cache:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.trading.client import TradingClient
        _alpaca_cache[cache_key] = (
            TradingClient(api_key=api_key, secret_key=secret_key, paper=True),
            StockHistoricalDataClient(api_key=api_key, secret_key=secret_key),
        )
    return _alpaca_cache[cache_key]


def clear_alpaca_cache() -> None:
    """Invalidate all cached Alpaca clients (call after changing API keys)."""
    _alpaca_cache.clear()


# ── IBKR clients ───────────────────────────────────────────────────────────────

def get_gateway(session: MutableMapping, ibkr_user: str, ibkr_pass: str,
                trading_mode: str) -> Any:
    """Return a GatewayManager, creating and storing it in *session* on first call."""
    if "gateway" not in session:
        from gateway_manager import GatewayManager
        session["gateway"] = GatewayManager(
            username=ibkr_user,
            password=ibkr_pass,
            trading_mode=trading_mode,
        )
    return session["gateway"]


def get_ib(session: MutableMapping) -> Any:
    """Return an IB instance from *session*, creating a fresh one if absent."""
    from ib_async import IB
    if "ib" not in session:
        session["ib"] = IB()
    return session["ib"]


# ── MultiTrader ────────────────────────────────────────────────────────────────

def get_portfolio_manager(
    session:       MutableMapping,
    data_client:   Any,
    get_price_fn:  Callable,
    place_buy_fn:  Callable,
    place_sell_fn: Callable,
    get_bars_fn:   Optional[Callable],
    get_equity_fn: Callable,
    **kwargs,
) -> Any:
    """
    Return the session's PortfolioManager, creating it on first call.

    kwargs are forwarded to PortfolioManager (target_slots, slot_pct,
    trader_config, scan_filters, daily_loss_limit).
    """
    if "portfolio_manager" not in session:
        from portfolio import PortfolioManager
        session["portfolio_manager"] = PortfolioManager(
            data_client   = data_client,
            get_price_fn  = get_price_fn,
            place_buy_fn  = place_buy_fn,
            place_sell_fn = place_sell_fn,
            get_bars_fn   = get_bars_fn,
            get_equity_fn = get_equity_fn,
            **kwargs,
        )
    return session["portfolio_manager"]


def get_multi_trader(
    session:       MutableMapping,
    get_price_fn:  Callable[[str], float],
    place_buy_fn:  Callable[[str, int], None],
    place_sell_fn: Callable[[str, int], None],
    get_bars_fn:   Optional[Callable] = None,
) -> Any:
    """
    Return the session's MultiTrader, creating it on first call.

    Broker callables are supplied by the UI/frontend layer so different
    frontends can wire in different brokers without changing core logic.
    """
    if "multitrader" not in session:
        from autotrader import MultiTrader
        session["multitrader"] = MultiTrader(
            get_price        = get_price_fn,
            place_buy        = place_buy_fn,
            place_sell       = place_sell_fn,
            get_bars         = get_bars_fn,
            daily_loss_limit = float(env_get("AT_DAILY_LOSS_LIMIT", "0")),
        )
    return session["multitrader"]
