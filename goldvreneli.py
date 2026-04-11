import logging
import os
import threading
import time
from datetime import datetime as _dt_now
from pathlib import Path
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from cachetools import TTLCache

from version import __version__
from core import (
    INSTALL_DIR, ENV_FILE, LIVE_FILLS_FILE,
    BrokerContext, Settings, ValidationError,
    env_get, env_save,
    get_alpaca_clients, clear_alpaca_cache,
    get_gateway, get_ib,
    get_multi_trader,
    get_portfolio_manager,
)
from stream import AlpacaStreamManager

# ── File logging (activates existing logger calls across all modules) ─────────
_log_dir = Path.home() / ".goldvreneli"
_log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(_log_dir / "goldvreneli.log")],
)
# ── Validate config at startup — catch bad env vars before any trading ─────────
try:
    _settings = Settings.from_env()
except ValidationError as _cfg_err:
    # Don't stop the app — fall back to defaults and warn the user
    _settings = Settings()
    import streamlit as _st_err
    _st_err.warning(
        f"⚠️ **Configuration error** — one or more env vars are invalid. "
        f"Defaults are in use until fixed in **Settings**.\n\n"
        f"```\n{_cfg_err}\n```"
    )

from autotrader import (
    AutoTrader, MultiTrader, TraderConfig, TraderState,
    StopMode, EntryMode, size_from_risk,
)
from scanner import scan, ScanFilters, UNIVERSE, UNIVERSE_US, UNIVERSE_INTL, UNIVERSE_INTL_FULL
from activity_tracker import render_sidebar_log

import pages.settings_page as settings_page
import pages.help_page as help_page
import pages.portfolio_page as portfolio_page
import pages.autotrader_page as autotrader_page
import pages.portfolio_mode_page as portfolio_mode_page
import pages.scanner_page as scanner_page
import pages.test_mode_page as test_mode_page
from ibkr_data import IBKRDataClient

# ── Config ────────────────────────────────────────────────────────────────────
st.set_page_config(page_title=f"Goldvreneli Trading v{__version__}", layout="wide")

# Hide the auto-generated Streamlit page-link nav at the top of the sidebar
st.markdown("""<style>[data-testid="stSidebarNav"] { display: none; }</style>""",
            unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"## Goldvreneli `v{__version__}`")

    broker = st.radio("Broker", ["Alpaca", "IBKR"],
                      horizontal=True, label_visibility="collapsed")

    if broker == "Alpaca":
        alpaca_is_live = st.toggle("Live Trading", key="alpaca_live")
        ibkr_is_live = False
        if alpaca_is_live:
            st.markdown(":red[**⚠️ LIVE TRADING — real money**]")
            st.markdown("🟢 **Active:** Alpaca · Live")
        else:
            st.markdown("🟡 **Active:** Alpaca · Paper")
    else:
        alpaca_is_live = False
        ibkr_is_live = st.toggle("Live Trading", key="ibkr_live")
        if ibkr_is_live:
            st.markdown(":red[**⚠️ LIVE TRADING — real money**]")
            st.markdown("🟢 **Active:** IBKR · Live")
        else:
            st.markdown("🟡 **Active:** IBKR · Paper")

    st.divider()

    # Allow programmatic navigation (e.g. Scanner → AutoTrader handoff)
    if "nav_page" in st.session_state:
        _target = st.session_state.pop("nav_page")
        if _target == "Test Mode":
            st.session_state["nav_test"]  = _target
            st.session_state.pop("nav_radio", None)
        else:
            st.session_state["nav_radio"] = _target
            st.session_state.pop("nav_test", None)

    # ── Main nav ──────────────────────────────────────────────────────────
    _main_pages = ["Scanner", "Portfolio Mode", "AutoTrader", "Portfolio", "Settings", "Help"]
    _main_icons = ["🔍", "📈", "🤖", "💼", "⚙️", "❓"]
    page = st.radio(
        "Page",
        _main_pages,
        format_func=lambda p: f"{_main_icons[_main_pages.index(p)]}  {p}",
        label_visibility="collapsed",
        key="nav_radio",
    )
    # Selecting main nav clears the test nav
    if page and st.session_state.get("nav_test"):
        st.session_state.pop("nav_test", None)

    # ── Testing nav ───────────────────────────────────────────────────────
    st.caption("**Testing**")
    _test_pages = ["Test Mode"]
    _test_icons = ["🎮"]
    test_page = st.radio(
        "Testing",
        _test_pages,
        format_func=lambda p: f"{_test_icons[_test_pages.index(p)]}  {p}",
        label_visibility="collapsed",
        index=None,
        key="nav_test",
    )
    # Selecting test nav clears the main nav highlight by overriding active page
    if test_page:
        page = test_page
    use_hist = st.toggle("🧪 Historic data mode", key="use_hist")
    if use_hist:
        as_of_date = st.date_input("As-of date", value=_dt_now.now().date(), key="as_of_date")
        st.caption("Scanner uses closing data up to this date.")
    else:
        as_of_date = _dt_now.now().date()

    st.divider()

    # ── Workflow hint ──────────────────────────────────────────────────────
    if broker == "Alpaca" and not test_page:
        st.caption("**Suggested workflow**")
        st.caption("1. 🔍 **Scanner** — find best stocks")
        st.caption("2. ⚡ **Quick Invest** — one click to open positions")
        st.caption("3. 📈 **Portfolio Mode** — fully automated, hands-off")

    st.divider()
    st.caption("Alpaca Paper/Live · IBKR · MIT License")

    # ── Activity Log (shown whenever a MultiTrader session is active) ──────
    _mt = st.session_state.get("multitrader")
    if _mt is not None:
        render_sidebar_log(_mt)

# ── IBKR session helpers (thin wrappers that bind st.session_state) ───────────
def _get_gateway(ibkr_user, ibkr_pass, trading_mode):
    return get_gateway(st.session_state, ibkr_user, ibkr_pass, trading_mode)

def _get_ib():
    return get_ib(st.session_state)

# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS PAGE (shared by both brokers)
# ══════════════════════════════════════════════════════════════════════════════
if page == "Settings":
    settings_page.render()
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# HELP PAGE (shared by both brokers)
# ══════════════════════════════════════════════════════════════════════════════
if page == "Help":
    help_page.render()
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# ALPACA DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if broker == "Alpaca":
    from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, GetOrdersRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from datetime import datetime, timedelta, time as dtime

    # ── Live mode confirmation guard ──────────────────────────────────────────
    if not alpaca_is_live:
        st.session_state.pop("live_confirmed", None)

    if alpaca_is_live and not st.session_state.get("live_confirmed"):
        st.warning(
            "⚠️ **You're going to trade with your real money now!**\n\n"
            "Live orders will be placed on your real Alpaca account. "
            "This is not a simulation."
        )
        c1, c2 = st.columns([1, 1])
        if c1.button("I understand — switch to Live", type="primary"):
            st.session_state["live_confirmed"] = True
            st.rerun()
        if c2.button("Cancel — stay on Paper"):
            st.session_state["alpaca_live"] = False
            st.rerun()
        st.stop()

    if alpaca_is_live:
        api_key    = env_get("ALPACA_LIVE_API_KEY")
        secret_key = env_get("ALPACA_LIVE_SECRET_KEY")
        if not api_key or not secret_key:
            st.error("⚠️ Live trading API keys not configured.")
            st.markdown("Enter your **live** Alpaca API keys below, or go to **Settings**.")
            with st.form("live_creds_quick"):
                lc1, lc2 = st.columns(2)
                q_key    = lc1.text_input("Live API Key",    type="password")
                q_secret = lc2.text_input("Live Secret Key", type="password")
                if st.form_submit_button("Save & Connect", type="primary"):
                    if q_key and q_secret:
                        env_save({"ALPACA_LIVE_API_KEY": q_key, "ALPACA_LIVE_SECRET_KEY": q_secret})
                        clear_alpaca_cache()
                        st.rerun()
                    else:
                        st.error("Both fields are required.")
            st.stop()
    else:
        api_key    = env_get("ALPACA_PAPER_API_KEY")
        secret_key = env_get("ALPACA_PAPER_SECRET_KEY")
        if not api_key or not secret_key:
            st.warning("Paper trading API keys not configured. Go to **Settings** to add them.")
            st.stop()

    # ── Invalidate session objects when mode changes ───────────────────────────
    _cur_mode = "live" if alpaca_is_live else "paper"
    if st.session_state.get("_alpaca_mode") != _cur_mode:
        st.session_state.pop("multitrader", None)
        st.session_state.pop("portfolio_manager", None)
        st.session_state["_alpaca_mode"] = _cur_mode

    try:
        trading_client, data_client = get_alpaca_clients(api_key, secret_key, paper=not alpaca_is_live)
    except Exception as e:
        st.error(f"Alpaca connection failed: {e}")
        st.stop()

    account = trading_client.get_account()

    _mode_label = "Live" if alpaca_is_live else "Paper"
    if alpaca_is_live:
        st.error(f"⚠️ LIVE TRADING MODE — real money at risk")

    # ── Shared broker callables (used by AutoTrader, Portfolio Mode, Scanner) ─
    def alpaca_get_price(symbol: str) -> float:
        from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest
        quote = data_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))
        price = float(quote[symbol].ask_price or quote[symbol].bid_price)
        if price <= 0:
            trade = data_client.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbol))
            price = float(trade[symbol].price)
        return price

    def alpaca_buy(symbol: str, qty: int):
        trading_client.submit_order(MarketOrderRequest(
            symbol=symbol, qty=qty,
            side=OrderSide.BUY, time_in_force=TimeInForce.DAY
        ))

    def alpaca_sell(symbol: str, qty: int):
        trading_client.submit_order(MarketOrderRequest(
            symbol=symbol, qty=qty,
            side=OrderSide.SELL, time_in_force=TimeInForce.DAY
        ))

    def alpaca_get_bars(symbol: str) -> pd.DataFrame:
        bars = data_client.get_stock_bars(StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=datetime.now() - timedelta(days=30),
        )).df
        bars = bars.reset_index(level=0, drop=True)
        return bars[["open", "high", "low", "close", "volume"]]

    # Migrate old single-trader session key
    if "autotrader" in st.session_state and "multitrader" not in st.session_state:
        del st.session_state["autotrader"]

    # ── TTL caches — persist across Streamlit reruns via session_state ────────
    if "_gv_bars_cache" not in st.session_state:
        st.session_state["_gv_bars_cache"]   = TTLCache(maxsize=512, ttl=60)
        st.session_state["_gv_bars_lock"]    = threading.Lock()
        st.session_state["_gv_equity_cache"] = TTLCache(maxsize=1,   ttl=30)
        st.session_state["_gv_equity_lock"]  = threading.Lock()

    _bars_cache   = st.session_state["_gv_bars_cache"]
    _bars_lock    = st.session_state["_gv_bars_lock"]
    _equity_cache = st.session_state["_gv_equity_cache"]
    _equity_lock  = st.session_state["_gv_equity_lock"]

    def _get_bars_cached(symbol: str) -> pd.DataFrame:
        with _bars_lock:
            if symbol in _bars_cache:
                return _bars_cache[symbol]
            result = alpaca_get_bars(symbol)
            _bars_cache[symbol] = result
            return result

    def _get_equity_cached() -> float:
        with _equity_lock:
            if "_" in _equity_cache:
                return _equity_cache["_"]
            result = float(trading_client.get_account().equity)
            _equity_cache["_"] = result
            return result

    # ── WebSocket stream — subscribe lazily, fall back to REST on cache miss ──
    _stream_key = f"alpaca_stream_{api_key[:8]}"
    if _stream_key not in st.session_state or not st.session_state[_stream_key].is_alive:
        if _stream_key in st.session_state:
            st.session_state[_stream_key].stop()
        st.session_state[_stream_key] = AlpacaStreamManager(api_key, secret_key)
    _stream_mgr = st.session_state[_stream_key]

    def _get_price_streaming(symbol: str) -> float:
        cached = _stream_mgr.get_price(symbol)
        if cached is not None:
            return cached
        return alpaca_get_price(symbol)

    mt = get_multi_trader(st.session_state, _get_price_streaming, alpaca_buy, alpaca_sell, _get_bars_cached)
    ctx = BrokerContext(
        name="Alpaca",
        get_price=_get_price_streaming,
        buy=alpaca_buy,
        sell=alpaca_sell,
        get_bars=_get_bars_cached,
        get_equity=_get_equity_cached,
        data_client=data_client,
    )
    # Clear mt/pm (and stream) if user last used a different broker
    if st.session_state.get("_broker_last") != "Alpaca":
        st.session_state.pop("multitrader", None)
        st.session_state.pop("portfolio_manager", None)
        if _stream_key in st.session_state:
            st.session_state[_stream_key].stop()
            st.session_state.pop(_stream_key, None)
        st.session_state.pop("_gv_bars_cache", None)
        st.session_state.pop("_gv_equity_cache", None)
        st.session_state["_broker_last"] = "Alpaca"

    # ── Page dispatch (Alpaca) ─────────────────────────────────────────────────
    if page == "Portfolio":
        portfolio_page.render(broker, trading_client, data_client, account, _get_ib(), None,
                              alpaca_is_live, ibkr_is_live, ctx.get_bars)
    elif page == "AutoTrader":
        autotrader_page.render(mt, ctx, trading_client, None)
    elif page == "Portfolio Mode":
        portfolio_mode_page.render(mt, ctx, trading_client, None)
    elif page == "Scanner":
        scanner_page.render(ctx, mt, use_hist, as_of_date)
    elif page == "Test Mode":
        test_mode_page.render(ctx)

# ══════════════════════════════════════════════════════════════════════════════
# IBKR DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
else:
    from ib_async import Stock, MarketOrder, LimitOrder, util

    ibkr_user      = env_get("IBKR_USERNAME")
    ibkr_pass      = env_get("IBKR_PASSWORD")
    trading_mode   = "live" if ibkr_is_live else "paper"
    ibkr_client_id = 1

    if not ibkr_user or not ibkr_pass:
        st.warning("IBKR credentials not configured. Go to **Settings** to add them.")
        st.stop()

    # ── Live mode confirmation guard ──────────────────────────────────────────
    if not ibkr_is_live:
        st.session_state.pop("ibkr_live_confirmed", None)

    if ibkr_is_live and not st.session_state.get("ibkr_live_confirmed"):
        st.warning(
            "⚠️ **You're going to trade with your real money now!**\n\n"
            "Live orders will be placed on your real IBKR account. "
            "This is not a simulation."
        )
        c1, c2 = st.columns([1, 1])
        if c1.button("I understand — switch to Live", type="primary"):
            st.session_state["ibkr_live_confirmed"] = True
            st.rerun()
        if c2.button("Cancel — stay on Paper"):
            st.session_state["ibkr_live"] = False
            st.rerun()
        st.stop()

    if ibkr_is_live:
        st.error("⚠️ **IBKR LIVE TRADING — real orders on your funded account**")

    gw = _get_gateway(ibkr_user, ibkr_pass, trading_mode)
    ib = _get_ib()
    api_port = 4001 if ibkr_is_live else 4002

    # Clear mt/pm/gateway/caches if broker or IBKR mode changed
    _ibkr_last_key = f"IBKR:{trading_mode}"
    if st.session_state.get("_broker_last") != _ibkr_last_key:
        st.session_state.pop("multitrader", None)
        st.session_state.pop("portfolio_manager", None)
        st.session_state.pop("gateway", None)
        st.session_state.pop("gw_start_attempted", None)
        st.session_state.pop("ib_connect_attempted", None)
        st.session_state.pop("_gv_bars_cache", None)
        st.session_state.pop("_gv_equity_cache", None)
        st.session_state["_broker_last"] = _ibkr_last_key

    # ── Detect crashes and dropped connections; reset flags to allow retry ────
    if st.session_state.get("gw_start_attempted") and not gw.is_running():
        # Gateway process died after a successful start — clear flags so the
        # auto-start block below fires again on the next rerun.
        st.session_state.pop("gw_start_attempted", None)
        st.session_state.pop("ib_connect_attempted", None)
        st.warning("⚠️ IB Gateway process is no longer running — attempting restart…")
        st.rerun()

    if st.session_state.get("ib_connect_attempted") and not ib.isConnected() and gw.api_port_open():
        # IB session dropped while the gateway is still up — allow one reconnect.
        st.session_state.pop("ib_connect_attempted", None)

    # ── Auto-start gateway and connect when credentials are present ───────────
    if not st.session_state.get("gw_start_attempted"):
        st.session_state.gw_start_attempted = True
        if not gw.is_running():
            with st.spinner("Starting IB Gateway via IBC\u2026"):
                try:
                    gw.start()
                except Exception as e:
                    st.error(f"Gateway start failed: {e}")
            with st.spinner("Waiting for API port (up to 90 s)\u2026"):
                gw.wait_for_api(timeout=90)
            st.rerun()

    if not ib.isConnected() and gw.api_port_open() and not st.session_state.get("ib_connect_attempted"):
        st.session_state.ib_connect_attempted = True
        try:
            ib.connect("127.0.0.1", api_port, clientId=ibkr_client_id)
        except Exception:
            pass
        st.rerun()

    # ── IBKR broker callables ─────────────────────────────────────────────────
    def ibkr_get_price(symbol: str) -> float:
        contract = Stock(symbol, "SMART", "USD")
        tickers = ib.reqTickers(contract)
        if tickers:
            t = tickers[0]
            price = t.marketPrice()
            if price and price > 0:
                return float(price)
            if t.bid and t.ask and t.bid > 0 and t.ask > 0:
                return float((t.bid + t.ask) / 2)
        raise ValueError(f"Could not get live price for {symbol}")

    def ibkr_buy(symbol: str, qty: int):
        contract = Stock(symbol, "SMART", "USD")
        ib.placeOrder(contract, MarketOrder("BUY", qty))
        ib.sleep(1)

    def ibkr_sell(symbol: str, qty: int):
        contract = Stock(symbol, "SMART", "USD")
        ib.placeOrder(contract, MarketOrder("SELL", qty))
        ib.sleep(1)

    def ibkr_get_bars(symbol: str) -> pd.DataFrame:
        contract = Stock(symbol, "SMART", "USD")
        bars = ib.reqHistoricalData(
            contract, endDateTime="", durationStr="30 D",
            barSizeSetting="1 day", whatToShow="TRADES",
            useRTH=True, formatDate=1, keepUpToDate=False,
        )
        if not bars:
            raise ValueError(f"No historical data for {symbol}")
        df = util.df(bars)[["open", "high", "low", "close", "volume"]]
        df.index = pd.to_datetime(df.index)
        return df

    def ibkr_get_equity() -> float:
        summary = ib.accountSummary()
        tags = {v.tag: v.value for v in summary if v.currency in ("USD", "")}
        return float(tags.get("NetLiquidation", 0))

    # ── TTL caches (IBKR bars are slow; equity query hits accountSummary) ─────
    if "_gv_bars_cache" not in st.session_state:
        st.session_state["_gv_bars_cache"]   = TTLCache(maxsize=512, ttl=60)
        st.session_state["_gv_bars_lock"]    = threading.Lock()
        st.session_state["_gv_equity_cache"] = TTLCache(maxsize=1,   ttl=30)
        st.session_state["_gv_equity_lock"]  = threading.Lock()

    _bars_cache   = st.session_state["_gv_bars_cache"]
    _bars_lock    = st.session_state["_gv_bars_lock"]
    _equity_cache = st.session_state["_gv_equity_cache"]
    _equity_lock  = st.session_state["_gv_equity_lock"]

    def _get_bars_cached(symbol: str) -> pd.DataFrame:
        with _bars_lock:
            if symbol in _bars_cache:
                return _bars_cache[symbol]
            result = ibkr_get_bars(symbol)
            _bars_cache[symbol] = result
            return result

    def _get_equity_cached() -> float:
        with _equity_lock:
            if "_" in _equity_cache:
                return _equity_cache["_"]
            result = ibkr_get_equity()
            _equity_cache["_"] = result
            return result

    data_client = IBKRDataClient(ib)
    mt = get_multi_trader(st.session_state, ibkr_get_price, ibkr_buy, ibkr_sell, _get_bars_cached)
    ctx = BrokerContext(
        name="IBKR",
        get_price=ibkr_get_price,
        buy=ibkr_buy,
        sell=ibkr_sell,
        get_bars=_get_bars_cached,
        get_equity=_get_equity_cached,
        data_client=data_client,
    )

    # ── Gateway status panel (shown on all IBKR pages except Settings/Help) ──
    if page not in ("Settings", "Help"):
        with st.container(border=True):
            st.subheader("Gateway")
            gw_running   = gw.is_running()
            api_open     = gw.api_port_open()
            ib_connected = ib.isConnected()

            s1, s2, s3 = st.columns(3)
            s1.metric("Process",    "Running"   if gw_running   else "Stopped",
                      delta_color="normal" if gw_running   else "inverse")
            s2.metric("API Port",   "Open"      if api_open     else "Closed",
                      delta_color="normal" if api_open     else "inverse")
            s3.metric("IB Session", "Connected" if ib_connected else "Disconnected",
                      delta_color="normal" if ib_connected else "inverse")

            c1, c2, c3, c4 = st.columns(4)
            if c1.button("Start Gateway", disabled=gw_running):
                with st.spinner("Starting IB Gateway via IBC\u2026"):
                    gw.start()
                with st.spinner("Waiting for API port (up to 90s)\u2026"):
                    ready = gw.wait_for_api(timeout=90)
                st.success("Gateway ready.") if ready else st.error("Timed out. Check logs.")
                st.rerun()
            if c2.button("Connect", disabled=(not api_open or ib_connected)):
                try:
                    ib.connect("127.0.0.1", api_port, clientId=ibkr_client_id)
                    st.success("Connected.")
                except Exception as e:
                    st.error(f"Connection failed: {e}")
                st.rerun()
            if c3.button("Disconnect", disabled=not ib_connected):
                ib.disconnect()
                st.info("Disconnected.")
                st.rerun()
            if c4.button("Stop Gateway", disabled=not gw_running):
                if ib_connected:
                    ib.disconnect()
                gw.stop()
                st.info("Gateway stopped.")
                st.rerun()
            with st.expander("Gateway Logs"):
                st.code(gw.get_logs())

        if not ib.isConnected():
            st.info("Start and connect to IB Gateway to use this page.")
            st.stop()

    # ── Page dispatch (IBKR) ──────────────────────────────────────────────────
    if page == "Portfolio":
        portfolio_page.render(broker, None, data_client, None, ib, gw,
                              alpaca_is_live, ibkr_is_live, ctx.get_bars)
    elif page == "AutoTrader":
        autotrader_page.render(mt, ctx, None, ib)
    elif page == "Portfolio Mode":
        portfolio_mode_page.render(mt, ctx, None, ib)
    elif page == "Scanner":
        scanner_page.render(ctx, mt, use_hist, as_of_date)
    elif page == "Test Mode":
        test_mode_page.render(ctx)
