import os
import time
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from dotenv import load_dotenv, dotenv_values, set_key

load_dotenv()

from version import __version__
from autotrader import (
    AutoTrader, MultiTrader, TraderConfig, TraderState,
    StopMode, EntryMode, size_from_risk,
)
from replay import ReplayPriceFeed, SyntheticPriceFeed, MockBroker, load_sessions
from scanner import scan, ScanFilters, UNIVERSE

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE    = os.path.join(INSTALL_DIR, ".env")

# ── Config ────────────────────────────────────────────────────────────────────
st.set_page_config(page_title=f"Goldvreneli Trading v{__version__}", layout="wide")

# ── .env helpers ──────────────────────────────────────────────────────────────
def env_get(key: str, default: str = "") -> str:
    return os.environ.get(key, dotenv_values(ENV_FILE).get(key, default))

def env_save(values: dict):
    """Write multiple key=value pairs to .env and reload into os.environ."""
    if not os.path.exists(ENV_FILE):
        open(ENV_FILE, "w").close()
    for k, v in values.items():
        set_key(ENV_FILE, k, v)
        os.environ[k] = v

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"## Goldvreneli `v{__version__}`")
    st.divider()

    broker = st.radio("Broker", ["Alpaca (Paper)", "IBKR"],
                      horizontal=True, label_visibility="collapsed")

    st.divider()

    # Allow programmatic navigation (e.g. Scanner → AutoTrader handoff)
    if "nav_page" in st.session_state:
        st.session_state["nav_radio"] = st.session_state.pop("nav_page")

    if broker == "Alpaca (Paper)":
        pages = ["Portfolio", "AutoTrader", "Scanner", "Backtest", "Settings"]
        icons = ["💼", "🤖", "🔍", "🧪", "⚙️"]
    else:
        pages = ["Portfolio", "Settings"]
        icons = ["💼", "⚙️"]

    page = st.radio(
        "Page",
        pages,
        format_func=lambda p: f"{icons[pages.index(p)]}  {p}",
        label_visibility="collapsed",
        key="nav_radio",
    )

    st.divider()
    st.caption("Alpaca Paper · IBKR · MIT License")

# ── Alpaca helpers ────────────────────────────────────────────────────────────
@st.cache_resource
def get_alpaca_clients(api_key, secret_key):
    from alpaca.trading.client import TradingClient
    from alpaca.data.historical import StockHistoricalDataClient
    trading = TradingClient(api_key=api_key, secret_key=secret_key, paper=True)
    data    = StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)
    return trading, data

# ── IBKR helpers ──────────────────────────────────────────────────────────────
def get_gateway(ibkr_user, ibkr_pass, trading_mode):
    if "gateway" not in st.session_state:
        from gateway_manager import GatewayManager
        st.session_state.gateway = GatewayManager(
            username=ibkr_user,
            password=ibkr_pass,
            trading_mode=trading_mode,
        )
    return st.session_state.gateway

def get_ib():
    if "ib" not in st.session_state or not st.session_state.ib.isConnected():
        from ib_async import IB
        st.session_state.ib = IB()
    return st.session_state.ib

# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS PAGE (shared by both brokers)
# ══════════════════════════════════════════════════════════════════════════════
if page == "Settings":
    st.title("Settings")

    with st.form("settings_form"):

        # ── Alpaca ────────────────────────────────────────────────────────────
        st.subheader("Alpaca Paper Trading")
        c1, c2 = st.columns(2)
        f_alpaca_key    = c1.text_input("API Key",    value=env_get("ALPACA_PAPER_API_KEY"),    type="password")
        f_alpaca_secret = c2.text_input("Secret Key", value=env_get("ALPACA_PAPER_SECRET_KEY"), type="password")

        st.divider()

        # ── IBKR ──────────────────────────────────────────────────────────────
        st.subheader("IBKR")
        c1, c2, c3 = st.columns(3)
        f_ibkr_user    = c1.text_input("Username",     value=env_get("IBKR_USERNAME"))
        f_ibkr_pass    = c2.text_input("Password",     value=env_get("IBKR_PASSWORD"),  type="password")
        f_ibkr_mode    = c3.selectbox("Trading Mode",  ["paper", "live"],
                                       index=0 if env_get("IBKR_MODE", "paper") == "paper" else 1)
        c4, c5 = st.columns(2)
        f_ibc_path     = c4.text_input("IBC Path",     value=env_get("IBC_PATH",     os.path.join(INSTALL_DIR, "ibc")))
        f_gateway_path = c5.text_input("Gateway Path", value=env_get("GATEWAY_PATH", os.path.join(INSTALL_DIR, "Jts", "ibgateway")))

        st.divider()

        # ── AutoTrader defaults ───────────────────────────────────────────────
        st.subheader("AutoTrader Defaults")
        c1, c2, c3, c4 = st.columns(4)
        f_at_symbol    = c1.text_input("Default Symbol",         value=env_get("AT_SYMBOL",    ""))
        f_at_threshold = c2.number_input("Trailing Stop %",      min_value=0.1, max_value=10.0,
                                          value=float(env_get("AT_THRESHOLD", "0.5")), step=0.1)
        f_at_poll      = c3.number_input("Poll Interval (s)",    min_value=1,
                                          value=int(env_get("AT_POLL", "5")),           step=1)
        f_at_loss_lim  = c4.number_input("Daily Loss Limit ($)", min_value=0.0,
                                          value=float(env_get("AT_DAILY_LOSS_LIMIT", "0")), step=100.0,
                                          help="Stop new trades when realized losses reach this amount. 0 = disabled.")

        st.divider()

        # ── Scanner defaults ──────────────────────────────────────────────────
        st.subheader("Scanner Filters")
        c1, c2, c3, c4 = st.columns(4)
        f_scan_n          = c1.number_input("Top N results",       min_value=1,   max_value=50,
                                             value=int(env_get("SCAN_TOP_N",        "10")))
        f_scan_rsi_lo     = c2.number_input("RSI min",             min_value=1,   max_value=99,
                                             value=int(env_get("SCAN_RSI_LO",       "35")))
        f_scan_rsi_hi     = c3.number_input("RSI max",             min_value=1,   max_value=99,
                                             value=int(env_get("SCAN_RSI_HI",       "72")))
        f_scan_vol_mult   = c4.number_input("Volume multiplier",   min_value=0.0, max_value=10.0,
                                             value=float(env_get("SCAN_VOL_MULT",   "1.0")), step=0.1)
        c1, c2, c3, c4 = st.columns(4)
        f_scan_min_price  = c1.number_input("Min price ($)",       min_value=0.0,
                                             value=float(env_get("SCAN_MIN_PRICE",  "5.0")), step=1.0)
        f_scan_min_adv    = c2.number_input("Min ADV ($M)",        min_value=0.0,
                                             value=float(env_get("SCAN_MIN_ADV_M",  "5.0")), step=1.0)
        f_scan_sma20_tol  = c3.number_input("SMA20 tolerance (%)", min_value=0.0, max_value=20.0,
                                             value=float(env_get("SCAN_SMA20_TOL",  "3.0")), step=0.5,
                                             help="Allow price this % below SMA20")
        f_scan_min_ret5d  = c4.number_input("Min 5d return (%)",   min_value=-20.0, max_value=20.0,
                                             value=float(env_get("SCAN_MIN_RET5D",  "-1.0")), step=0.5)
        f_scan_watchlist  = st.text_area(
            "Default watchlist (comma-separated — used as pre-selection in Scanner)",
            value=env_get("SCAN_WATCHLIST", ""),
            height=80,
            placeholder="AAPL, MSFT, NVDA, …  (leave blank to start with full universe)",
        )

        st.divider()
        saved = st.form_submit_button("Save Settings", type="primary")

    if saved:
        env_save({
            "ALPACA_PAPER_API_KEY":    f_alpaca_key,
            "ALPACA_PAPER_SECRET_KEY": f_alpaca_secret,
            "IBKR_USERNAME":           f_ibkr_user,
            "IBKR_PASSWORD":           f_ibkr_pass,
            "IBKR_MODE":               f_ibkr_mode,
            "IBC_PATH":                f_ibc_path,
            "GATEWAY_PATH":            f_gateway_path,
            "AT_SYMBOL":               f_at_symbol,
            "AT_THRESHOLD":            str(f_at_threshold),
            "AT_POLL":                 str(f_at_poll),
            "AT_DAILY_LOSS_LIMIT":     str(f_at_loss_lim),
            "SCAN_TOP_N":              str(f_scan_n),
            "SCAN_RSI_LO":             str(f_scan_rsi_lo),
            "SCAN_RSI_HI":             str(f_scan_rsi_hi),
            "SCAN_VOL_MULT":           str(f_scan_vol_mult),
            "SCAN_MIN_PRICE":          str(f_scan_min_price),
            "SCAN_MIN_ADV_M":          str(f_scan_min_adv),
            "SCAN_SMA20_TOL":          str(f_scan_sma20_tol),
            "SCAN_MIN_RET5D":          str(f_scan_min_ret5d),
            "SCAN_WATCHLIST":          f_scan_watchlist,
        })
        # Clear cached clients so they reconnect with new keys
        get_alpaca_clients.clear()
        # Reset IBKR auto-start flags so gateway restarts with new credentials
        st.session_state.pop("gw_start_attempted", None)
        st.session_state.pop("ib_connect_attempted", None)
        if "gateway" in st.session_state:
            del st.session_state["gateway"]
        st.success("Settings saved to .env")
        st.rerun()

    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# ALPACA DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if broker == "Alpaca (Paper)":
    from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, GetOrdersRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from datetime import datetime, timedelta, time as dtime

    api_key    = env_get("ALPACA_PAPER_API_KEY")
    secret_key = env_get("ALPACA_PAPER_SECRET_KEY")

    if not api_key or not secret_key:
        st.warning("API keys not configured. Go to **Settings** to add them.")
        st.stop()

    try:
        trading_client, data_client = get_alpaca_clients(api_key, secret_key)
    except Exception as e:
        st.error(f"Alpaca connection failed: {e}")
        st.stop()

    account = trading_client.get_account()

    st.title("Portfolio Dashboard (Alpaca Paper)")

    # ── Page: Portfolio ───────────────────────────────────────────────────────
    if page == "Portfolio":
        day_pl     = float(account.equity) - float(account.last_equity)
        day_pl_pct = (day_pl / float(account.last_equity) * 100) if float(account.last_equity) else 0.0
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Portfolio Value", f"${float(account.portfolio_value):,.2f}")
        col2.metric("Cash",            f"${float(account.cash):,.2f}")
        col3.metric("Buying Power",    f"${float(account.buying_power):,.2f}")
        col4.metric("Equity",          f"${float(account.equity):,.2f}")
        col5.metric("Day P&L",         f"${day_pl:+,.2f}",
                    delta=f"{day_pl_pct:+.2f}%",
                    delta_color="normal")

        st.divider()

        st.subheader("Open Positions")
        positions = trading_client.get_all_positions()
        if positions:
            pos_data = [{
                "Symbol":       p.symbol,
                "Qty":          float(p.qty),
                "Avg Entry":    f"${float(p.avg_entry_price):.2f}",
                "Current":      f"${float(p.current_price):.2f}",
                "Market Value": f"${float(p.market_value):,.2f}",
                "P&L ($)":      f"${float(p.unrealized_pl):,.2f}",
                "P&L (%)":      f"{float(p.unrealized_plpc)*100:.2f}%",
                "Side":         p.side.value,
            } for p in positions]
            st.dataframe(pd.DataFrame(pos_data), width="stretch", hide_index=True)

            fig = go.Figure(go.Bar(
                x=[p.symbol for p in positions],
                y=[float(p.unrealized_pl) for p in positions],
                marker_color=["green" if float(p.unrealized_pl) >= 0 else "red" for p in positions],
                text=[f"${float(p.unrealized_pl):,.2f}" for p in positions],
                textposition="outside",
            ))
            fig.update_layout(title="Unrealized P&L by Position", yaxis_title="P&L ($)", height=350)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No open positions.")

        st.divider()

        st.subheader("Price Chart")
        chart_symbol  = st.text_input("Symbol",
                                       value=st.session_state.get("_chart_sym", "AAPL")).upper()
        st.session_state["_chart_sym"] = chart_symbol
        timeframe_opt = st.selectbox("Timeframe", ["1D", "1W", "1M", "3M"], index=2)
        tf_map   = {"1D": (1,  TimeFrame.Hour), "1W": (7,  TimeFrame.Hour),
                    "1M": (30, TimeFrame.Day),  "3M": (90, TimeFrame.Day)}
        days, tf = tf_map[timeframe_opt]

        if chart_symbol:
            try:
                bars = data_client.get_stock_bars(StockBarsRequest(
                    symbol_or_symbols=chart_symbol, timeframe=tf,
                    start=datetime.now() - timedelta(days=days),
                )).df
                if not bars.empty:
                    bars = bars.reset_index()
                    fig2 = go.Figure(go.Candlestick(
                        x=bars["timestamp"],
                        open=bars["open"], high=bars["high"],
                        low=bars["low"],   close=bars["close"],
                    ))
                    fig2.update_layout(title=f"{chart_symbol} — {timeframe_opt}",
                                       xaxis_rangeslider_visible=False, height=400)
                    st.plotly_chart(fig2, width="stretch")
            except Exception as e:
                st.error(f"Chart error: {e}")

        st.divider()

        st.subheader("Place Order")
        with st.form("order_form"):
            c1, c2, c3, c4, c5 = st.columns(5)
            sym        = c1.text_input("Symbol", value="AAPL").upper()
            side       = c2.selectbox("Side", ["BUY", "SELL"])
            order_type = c3.selectbox("Type", ["Market", "Limit"])
            qty        = c4.number_input("Qty", min_value=1.0, value=1.0, step=1.0)
            limit_px   = c5.number_input("Limit Price", min_value=0.0, value=0.0, step=0.01,
                                          disabled=(order_type == "Market"))
            submitted  = st.form_submit_button("Submit Order", type="primary")

        if submitted:
            if not sym:
                st.error("Symbol must not be empty.")
                st.stop()
            try:
                order_side = OrderSide.BUY if side == "BUY" else OrderSide.SELL
                if order_type == "Market":
                    req = MarketOrderRequest(symbol=sym, qty=qty, side=order_side, time_in_force=TimeInForce.DAY)
                else:
                    req = LimitOrderRequest(symbol=sym, qty=qty, limit_price=limit_px,
                                            side=order_side, time_in_force=TimeInForce.GTC)
                order = trading_client.submit_order(req)
                st.success(f"Order submitted — ID: {order.id} | Status: {order.status}")
            except Exception as e:
                st.error(f"Order failed: {e}")

        st.divider()

        st.subheader("Open Orders")
        open_orders = trading_client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN))
        if open_orders:
            st.dataframe(pd.DataFrame([{
                "ID":     str(o.id)[:8] + "…",
                "Symbol": o.symbol,
                "Side":   o.side.value,
                "Type":   o.order_type.value,
                "Qty":    float(o.qty),
                "Filled": float(o.filled_qty),
                "Limit":  f"${float(o.limit_price):.2f}" if o.limit_price else "—",
                "Status": o.status.value,
            } for o in open_orders]), width="stretch", hide_index=True)
            if st.button("Cancel All Orders", type="secondary"):
                trading_client.cancel_orders()
                st.success("All open orders cancelled.")
                st.rerun()
        else:
            st.info("No open orders.")

    # ── Page: AutoTrader ─────────────────────────────────────────────────────
    elif page == "AutoTrader":
        st.subheader("AutoTrader — Multi-Position Manager")
        st.caption("Enters positions and exits automatically via trailing stop, take-profit, breakeven, or time stop.")

        def alpaca_get_price(symbol: str) -> float:
            from alpaca.data.requests import StockLatestQuoteRequest
            quote = data_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))
            return float(quote[symbol].ask_price or quote[symbol].bid_price)

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

        if "multitrader" not in st.session_state:
            st.session_state.multitrader = MultiTrader(
                get_price        = alpaca_get_price,
                place_buy        = alpaca_buy,
                place_sell       = alpaca_sell,
                get_bars         = alpaca_get_bars,
                daily_loss_limit = float(env_get("AT_DAILY_LOSS_LIMIT", "0")),
            )
        mt = st.session_state.multitrader

        # ── New position form ─────────────────────────────────────────────
        # Handle multi-symbol prefill from Scanner
        _prefill_list = st.session_state.pop("at_prefill_list", None)
        _prefill_single = st.session_state.pop("at_prefill", None)
        if _prefill_list:
            _default_symbol = _prefill_list[0]
            _queued = _prefill_list[1:]
            if _queued:
                st.session_state["at_queue"] = _queued
        else:
            _default_symbol = _prefill_single or env_get("AT_SYMBOL", "")

        with st.form("at_config"):
            st.markdown("**New Position**")
            c1, c2, c3 = st.columns(3)
            at_symbol   = c1.text_input("Symbol", value=_default_symbol).upper()
            at_stop_mode = c2.selectbox("Stop Mode", ["PCT", "ATR"],
                                        help="PCT = fixed %; ATR = N × ATR(14) dollars")
            at_stop_val  = c3.number_input(
                "Trailing Stop %",
                min_value=0.1, max_value=20.0,
                value=float(env_get("AT_THRESHOLD", "0.5")), step=0.1,
                help="For PCT: % drop from peak triggers sell. For ATR: multiplier × ATR(14).",
            )

            # Qty sizing mode
            qty_mode = st.radio("Qty mode", ["Shares", "Dollar amount", "Risk %"],
                                horizontal=True, label_visibility="collapsed")
            if qty_mode == "Shares":
                at_qty = st.number_input("Qty (shares)", min_value=1, value=1, step=1)
            elif qty_mode == "Dollar amount":
                qc1, qc2 = st.columns(2)
                at_dollar_amt  = qc1.number_input("$ amount to invest", min_value=1.0,
                                                   value=1000.0, step=100.0)
                at_price_est   = qc2.number_input("Est. price per share ($)", min_value=0.01,
                                                   value=100.0, step=1.0)
                at_qty = max(1, int(at_dollar_amt / at_price_est))
                st.caption(f"≈ **{at_qty}** shares @ ${at_price_est:.2f} = ${at_qty * at_price_est:,.2f}")
            else:
                rc1, rc2, rc3 = st.columns(3)
                at_equity    = rc1.number_input("Account equity ($)", min_value=1.0,
                                                 value=float(account.equity) if 'account' in dir() else 10000.0,
                                                 step=500.0)
                at_risk_pct  = rc2.number_input("Risk per trade (%)", min_value=0.1,
                                                 max_value=10.0, value=1.0, step=0.1)
                at_entry_est = rc3.number_input("Est. entry price ($)", min_value=0.01,
                                                 value=100.0, step=1.0)
                stop_dist_est = at_entry_est * at_stop_val / 100
                at_qty = size_from_risk(at_equity, at_risk_pct, at_entry_est, stop_dist_est)
                st.caption(f"**{at_qty}** shares — risking "
                           f"${at_equity * at_risk_pct / 100:,.2f} @ ${stop_dist_est:.2f} stop dist")

            at_poll = st.number_input("Poll interval (s)", min_value=1,
                                      value=int(env_get("AT_POLL", "5")), step=1)

            with st.expander("Entry mode"):
                at_entry_mode    = st.selectbox("Entry", ["MARKET", "LIMIT", "SCALE"])
                ec1, ec2         = st.columns(2)
                at_limit_price   = ec1.number_input("Limit price ($)", min_value=0.0, value=0.0, step=0.01,
                                                     disabled=(at_entry_mode != "LIMIT"))
                at_limit_timeout = ec2.number_input("Limit timeout (s)", min_value=5, value=60, step=5,
                                                     disabled=(at_entry_mode != "LIMIT"))
                sc1, sc2         = st.columns(2)
                at_scale_n       = sc1.number_input("Tranches", min_value=2, max_value=10, value=3, step=1,
                                                     disabled=(at_entry_mode != "SCALE"))
                at_scale_ivl     = sc2.number_input("Interval between tranches (s)", min_value=5,
                                                     value=30, step=5, disabled=(at_entry_mode != "SCALE"))

            with st.expander("Exit targets"):
                xc1, xc2         = st.columns(2)
                at_tp_pct        = xc1.number_input("Take-profit trigger (%)", min_value=0.0, value=0.0, step=0.1,
                                                     help="0 = disabled. Sell at_tp_fraction of position when up this %.")
                at_tp_frac       = xc2.slider("Fraction to sell at take-profit", min_value=0.1,
                                               max_value=1.0, value=1.0, step=0.1)
                xc3, xc4         = st.columns(2)
                at_be_pct        = xc3.number_input("Breakeven trigger (%)", min_value=0.0, value=0.0, step=0.1,
                                                     help="0 = disabled. Once up this %, move stop floor to entry price.")
                at_time_stop     = xc4.number_input("Time stop (minutes)", min_value=0, value=0, step=5,
                                                     help="0 = disabled. Exit after this many minutes.")

            col_start, col_stop_all = st.columns(2)
            start_btn    = col_start.form_submit_button("▶ Start", type="primary")
            stop_all_btn = col_stop_all.form_submit_button("⏹ Stop All")

        if start_btn:
            if not at_symbol:
                st.error("Symbol must not be empty.")
            else:
                cfg = TraderConfig(
                    stop_mode             = StopMode(at_stop_mode.lower()),
                    stop_value            = at_stop_val,
                    poll_interval         = float(at_poll),
                    entry_mode            = EntryMode(at_entry_mode.lower()),
                    limit_price           = at_limit_price,
                    limit_timeout_s       = float(at_limit_timeout),
                    scale_tranches        = at_scale_n,
                    scale_interval_s      = float(at_scale_ivl),
                    tp_trigger_pct        = at_tp_pct,
                    tp_qty_fraction       = at_tp_frac,
                    breakeven_trigger_pct = at_be_pct,
                    time_stop_minutes     = float(at_time_stop),
                )
                try:
                    mt.start(at_symbol, int(at_qty), config=cfg)
                    queue = st.session_state.pop("at_queue", [])
                    if queue:
                        st.session_state["at_prefill_list"] = queue
                        st.success(f"Started {at_symbol}. Next in queue: {queue[0]}")
                    else:
                        st.success(f"Started {at_symbol} — {at_stop_mode} stop @ {at_stop_val}")
                except Exception as e:
                    st.error(str(e))
            st.rerun()

        if stop_all_btn:
            mt.stop_all()
            st.session_state.pop("at_queue", None)
            st.info("All positions stopped.")
            st.rerun()

        if st.session_state.get("at_queue"):
            q = st.session_state["at_queue"]
            st.info(f"Queue: {' → '.join(q)}  (configure & start each in turn)")

        # ── Positions table ───────────────────────────────────────────────
        statuses = mt.statuses()
        if statuses:
            state_color = {
                "idle":     "gray",
                "entering": "blue",
                "watching": "green",
                "sold":     "blue",
                "stopped":  "orange",
                "error":    "red",
            }

            st.divider()
            st.subheader("Positions")

            rows = []
            for sym, s in statuses.items():
                sc = state_color.get(s.state.value, "gray")
                rows.append({
                    "Symbol":   sym,
                    "State":    s.state.value.upper(),
                    "Entry":    f"${s.entry_price:.2f}",
                    "Current":  f"${s.current_price:.2f}",
                    "Peak":     f"${s.peak_price:.2f}",
                    "Stop":     f"${s.stop_floor:.2f}",
                    "Drawdown": f"{s.drawdown_pct:.2f}%",
                    "P&L":      f"${s.pnl:+,.2f}",
                    "Mode":     s.config.stop_mode.value.upper(),
                    "ATR":      f"${s.atr_value:.2f}" if s.atr_value else "—",
                    "BE":       "✓" if s.breakeven_active else "—",
                    "TP":       "✓" if s.tp_executed else "—",
                })
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

            # Per-position drawdown bars and stop buttons
            active = [(sym, s) for sym, s in statuses.items()
                      if s.state == TraderState.WATCHING]
            if active:
                for sym, s in active:
                    with st.container(border=True):
                        mc1, mc2, mc3, mc4, mc5 = st.columns([2, 2, 2, 2, 1])
                        mc1.metric("Symbol",  sym)
                        mc2.metric("Current", f"${s.current_price:.2f}",
                                   delta=f"Entry ${s.entry_price:.2f}")
                        mc3.metric("Peak",    f"${s.peak_price:.2f}")
                        mc4.metric("Stop",    f"${s.stop_floor:.2f}")
                        if mc5.button("Stop", key=f"stop_{sym}"):
                            mt.stop(sym)
                            st.rerun()

                        pnl_color = "green" if s.pnl >= 0 else "red"
                        st.markdown(f"**P&L:** :{pnl_color}[${s.pnl:+,.2f}]")
                        pct = min(s.drawdown_pct / s.threshold_pct, 1.0) if s.threshold_pct else 0.0
                        st.progress(pct, text=f"Drawdown {s.drawdown_pct:.2f}% / {s.threshold_pct:.2f}%")
                        if s.breakeven_active:
                            st.caption("Breakeven active — stop floor at entry")
                        if s.tp_executed:
                            st.caption("Take-profit executed — trailing remaining shares")

            # Daily summary
            st.divider()
            dl1, dl2 = st.columns(2)
            dl1.metric("Unrealized P&L (watching)", f"${mt.daily_pnl():+,.2f}")
            dl2.metric("Realized losses today",     f"${mt.realized_losses():,.2f}")

            # Combined log
            all_logs = mt.all_logs()
            if all_logs:
                st.subheader("Activity Log")
                log_data = [{"Time":   e.timestamp.strftime("%H:%M:%S"),
                             "Action": e.action,
                             "Price":  f"${e.price:.2f}" if e.price else "—",
                             "Note":   e.note}
                            for e in reversed(all_logs)]
                st.dataframe(pd.DataFrame(log_data), width="stretch", hide_index=True)

        # Auto-refresh while any position is watching
        if any(s.state == TraderState.WATCHING for s in mt.statuses().values()):
            time.sleep(5)
            st.rerun()

    # ── Page: Scanner ────────────────────────────────────────────────────────
    elif page == "Scanner":
        st.subheader("Position Scanner")
        st.caption("Scans ~600 liquid US stocks, ETFs, and ADRs, applies technical filters, proposes the top candidates.")

        # ── Build filters from saved settings ─────────────────────────────────
        scan_filters = ScanFilters(
            min_price     = float(env_get("SCAN_MIN_PRICE", "5.0")),
            min_adv_m     = float(env_get("SCAN_MIN_ADV_M", "5.0")),
            rsi_lo        = float(env_get("SCAN_RSI_LO",    "35")),
            rsi_hi        = float(env_get("SCAN_RSI_HI",    "72")),
            vol_mult      = float(env_get("SCAN_VOL_MULT",  "1.0")),
            sma20_tol_pct = float(env_get("SCAN_SMA20_TOL", "3.0")),
            min_ret_5d    = float(env_get("SCAN_MIN_RET5D", "-1.0")),
        )

        col_a, col_b, col_c = st.columns([1, 2, 2])
        top_n      = col_a.number_input("Top N results", min_value=1, max_value=50,
                                         value=int(env_get("SCAN_TOP_N", "10")))
        use_hist   = col_b.checkbox("Historical date", value=False)
        as_of_date = col_c.date_input("As-of date", value=datetime.now().date(),
                                       disabled=not use_hist)

        # ── Symbol selection ──────────────────────────────────────────────────
        _watchlist_raw = env_get("SCAN_WATCHLIST", "")
        _watchlist = [s.strip().upper() for s in _watchlist_raw.replace(",", " ").split() if s.strip()]
        _watchlist_valid = [s for s in _watchlist if s in UNIVERSE]

        _default_all = len(_watchlist_valid) == 0
        with st.expander(
            f"Symbol list — {'full universe' if _default_all else f'{len(_watchlist_valid)} from watchlist'} ({len(UNIVERSE)} available)",
            expanded=False,
        ):
            sel_all = st.checkbox("Scan full universe", value=_default_all, key="scan_sel_all")
            selected_syms = st.multiselect(
                "Symbols to scan",
                options=sorted(UNIVERSE),
                default=_watchlist_valid,
                disabled=sel_all,
                placeholder="Type to search…",
                label_visibility="collapsed",
            )
        scan_symbols = None if sel_all else (selected_syms or None)

        with st.expander("Active filters"):
            st.markdown(f"""
| Filter | Value |
|--------|-------|
| Symbols | {"Full universe (%d)" % len(UNIVERSE) if scan_symbols is None else "%d selected" % len(scan_symbols)} |
| Min price | ${scan_filters.min_price:.0f} |
| Min ADV | ${scan_filters.min_adv_m:.0f}M |
| RSI(14) | {scan_filters.rsi_lo:.0f} – {scan_filters.rsi_hi:.0f} |
| Volume | ≥ {scan_filters.vol_mult:.1f}× 20-day avg |
| SMA20 tolerance | {scan_filters.sma20_tol_pct:.1f}% below allowed |
| Min 5d return | {scan_filters.min_ret_5d:.1f}% |
| Above SMA50 | required |

_Adjust thresholds in **⚙️ Settings → Scanner Filters**_
""")

        run_scan = st.button("Run Scan", type="primary")

        if run_scan:
            progress_bar = st.progress(0, text="Scanning…")

            def on_progress(done, total):
                progress_bar.progress(done / total, text=f"Scanning {done}/{total}…")

            as_of_dt = datetime.combine(as_of_date, datetime.max.time()) if use_hist else None
            with st.spinner("Running scan…"):
                st.session_state.scan_results = scan(data_client, top_n=int(top_n),
                                                      progress_cb=on_progress, as_of=as_of_dt,
                                                      filters=scan_filters, symbols=scan_symbols)
            st.session_state.scan_ts = datetime.now()
            progress_bar.empty()

        results = st.session_state.get("scan_results", pd.DataFrame())

        if not results.empty:
            scan_ts = st.session_state.get("scan_ts")
            if scan_ts:
                age_s = (datetime.now() - scan_ts).total_seconds()
                age_str = f"{int(age_s / 60)}m ago" if age_s >= 60 else f"{int(age_s)}s ago"
                stale = age_s > 1800  # 30 min
                msg = f"Last scan: {scan_ts.strftime('%H:%M:%S')} ({age_str})"
                if stale:
                    st.warning(f"Results may be stale — {msg}")
                else:
                    st.caption(msg)
            st.success(f"Found {len(results)} candidates. Select rows then send to AutoTrader.")

            selection = st.dataframe(
                results,
                width="stretch",
                on_select="rerun",
                selection_mode="multi-row",
                key="scanner_table",
            )

            # Multi-select → AutoTrader
            rows = selection.selection.get("rows", [])
            selected_symbols = [results.index[r] for r in rows]
            if selected_symbols:
                st.info(f"Selected: {', '.join(f'**{s}**' for s in selected_symbols)}")
                if st.button(f"▶ Send {len(selected_symbols)} symbol(s) to AutoTrader", type="primary"):
                    st.session_state.at_prefill_list = selected_symbols
                    st.session_state.nav_page        = "AutoTrader"
                    st.rerun()

            chart_col = "RS vs SPY" if "RS vs SPY" in results.columns else "5d Ret%"
            fig_scan = go.Figure(go.Bar(
                x=results.index,
                y=results[chart_col],
                marker_color=["green" if v >= 0 else "red" for v in results[chart_col]],
                text=[f"{v:+.2f}%" for v in results[chart_col]],
                textposition="outside",
            ))
            fig_scan.update_layout(title=f"{chart_col} — Top Candidates",
                                   yaxis_title=chart_col, height=350)
            st.plotly_chart(fig_scan, width="stretch")
        elif not run_scan:
            st.info("Run a scan to see candidates.")

    # ── Page: Backtest ────────────────────────────────────────────────────────
    elif page == "Backtest":
        st.subheader("Backtest / Test Mode")
        st.caption("Replay historical data or generate synthetic prices to test AutoTrader logic outside market hours.")

        DEFAULT_FILLS = os.path.join(os.path.dirname(__file__), "backtest_fills.json")

        # ── Feed configuration ────────────────────────────────────────────
        st.markdown("**Price Feed**")
        feed_type = st.radio("Feed type", ["Replay (historical 1-min bars)", "Synthetic (random walk)"],
                             horizontal=True)

        if feed_type.startswith("Replay"):
            fc1, fc2, fc3 = st.columns(3)
            bt_symbol = fc1.text_input("Symbol", value=env_get("AT_SYMBOL", "")).upper()
            _today = datetime.now().date()
            _bt_default_date = _today - timedelta(days=[3, 1, 1, 1, 1, 1, 2][_today.weekday()])
            bt_date   = fc2.date_input("Date", value=_bt_default_date,
                                        help="Must be a trading day (Mon–Fri, non-holiday)")
            bt_speed  = fc3.number_input("Speed (×)", min_value=1, max_value=10000,
                                          value=200, step=50,
                                          help="200 = 200× real-time. Recommended poll interval = 60 / speed.")
            bt_poll   = round(60.0 / bt_speed, 3)

            # ── Time window ───────────────────────────────────────────────
            tr_mode = st.radio("Time window (ET)", ["Full day", "Duration", "Custom range"],
                               horizontal=True)
            bt_start_time = bt_end_time = bt_duration_hours = None

            if tr_mode == "Duration":
                trc1, trc2 = st.columns(2)
                _st = trc1.time_input("Start time (ET)", value=dtime(9, 30))
                bt_start_time = _st
                bt_duration_hours = trc2.select_slider(
                    "Duration",
                    options=[0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 6.5],
                    value=2.0,
                    format_func=lambda x: f"{x:g}h",
                )
                end_dt = datetime(2000, 1, 1, _st.hour, _st.minute) + timedelta(hours=bt_duration_hours)
                st.caption(f"Replaying {bt_duration_hours:g}h from "
                           f"{_st.strftime('%H:%M')} → {end_dt.strftime('%H:%M')} ET  |  "
                           f"≈{int(bt_duration_hours * 60)} bars  |  "
                           f"poll {bt_poll}s")
            elif tr_mode == "Custom range":
                trc1, trc2 = st.columns(2)
                bt_start_time = trc1.time_input("Start time (ET)", value=dtime(9, 30))
                bt_end_time   = trc2.time_input("End time (ET)",   value=dtime(11, 30))
                dur_m = (datetime.combine(datetime.today(), bt_end_time)
                         - datetime.combine(datetime.today(), bt_start_time)).seconds // 60
                st.caption(f"{bt_start_time.strftime('%H:%M')} → {bt_end_time.strftime('%H:%M')} ET  |  "
                           f"≈{dur_m} bars  |  poll {bt_poll}s")
            else:
                st.caption(f"Full trading day  |  poll {bt_poll}s")
        else:
            sc1, sc2, sc3, sc4 = st.columns(4)
            bt_symbol   = sc1.text_input("Symbol (label only)", value="SIM").upper()
            bt_start_px = sc2.number_input("Start price ($)", min_value=1.0, value=100.0, step=1.0)
            bt_vol      = sc3.number_input("Volatility % / step", min_value=0.01, value=0.5, step=0.05)
            bt_drift    = sc4.number_input("Drift % / step", min_value=-5.0, max_value=5.0,
                                            value=0.0, step=0.05)
            sc5, sc6    = st.columns(2)
            bt_seed_on  = sc5.checkbox("Fix random seed", value=False)
            bt_seed     = sc6.number_input("Seed", min_value=0, value=42, step=1,
                                            disabled=not bt_seed_on)
            bt_poll     = 0.2   # synthetic runs fast

        st.divider()

        # ── Trader configuration ──────────────────────────────────────────
        st.markdown("**Trader Config**")
        tc1, tc2, tc3 = st.columns(3)
        bt_qty        = tc1.number_input("Qty", min_value=1, value=10, step=1)
        bt_stop_mode  = tc2.selectbox("Stop mode", ["PCT", "ATR"])
        bt_stop_val   = tc3.number_input(
            "Stop value (% or ATR mult)", min_value=0.1, value=0.5, step=0.1
        )
        tc4, tc5, tc6 = st.columns(3)
        bt_tp_pct     = tc4.number_input("Take-profit %", min_value=0.0, value=0.0, step=0.1)
        bt_be_pct     = tc5.number_input("Breakeven trigger %", min_value=0.0, value=0.0, step=0.1)
        bt_time_stop  = tc6.number_input("Time stop (min)", min_value=0, value=0, step=1)

        st.divider()

        # ── Output file ───────────────────────────────────────────────────
        st.markdown("**Output**")
        bt_output = st.text_input("Fills log file", value=DEFAULT_FILLS,
                                   help="JSON file; sessions are appended on each run.")

        col_start, col_stop = st.columns(2)
        bt_start = col_start.button("▶ Start Backtest", type="primary")
        bt_stop  = col_stop.button("⏹ Stop")

        # ── Controls ──────────────────────────────────────────────────────
        if bt_start:
            # Clean up previous session
            if "bt_at" in st.session_state:
                try:
                    st.session_state.bt_at.stop()
                except Exception:
                    pass

            try:
                # Build feed
                if feed_type.startswith("Replay"):
                    feed = ReplayPriceFeed(
                        data_client,
                        bt_symbol,
                        str(bt_date),
                        speed          = float(bt_speed),
                        start_time     = bt_start_time,
                        end_time       = bt_end_time,
                        duration_hours = bt_duration_hours,
                    )
                    poll_iv = feed.recommended_poll_interval
                    meta = {
                        "feed":     "replay",
                        "symbol":   bt_symbol,
                        "date":     str(bt_date),
                        "speed":    bt_speed,
                        "bars":     feed.bar_count,
                        "window":   (f"{bt_start_time.strftime('%H:%M') if bt_start_time else 'open'}"
                                     f"–{bt_end_time.strftime('%H:%M') if bt_end_time else 'close'} ET"),
                    }
                else:
                    feed = SyntheticPriceFeed(
                        start_price    = bt_start_px,
                        volatility_pct = bt_vol,
                        drift_pct      = bt_drift,
                        seed           = int(bt_seed) if bt_seed_on else None,
                    )
                    poll_iv = bt_poll
                    meta = {
                        "feed": "synthetic", "symbol": bt_symbol,
                        "start_price": bt_start_px, "volatility": bt_vol,
                        "drift": bt_drift,
                    }

                broker = MockBroker(
                    get_price_fn = feed.get_price,
                    output_file  = bt_output,
                    session_meta = {**meta,
                                    "stop_mode": bt_stop_mode,
                                    "stop_val":  bt_stop_val,
                                    "qty":       bt_qty},
                )

                cfg = TraderConfig(
                    stop_mode             = StopMode(bt_stop_mode.lower()),
                    stop_value            = bt_stop_val,
                    poll_interval         = poll_iv,
                    tp_trigger_pct        = bt_tp_pct,
                    breakeven_trigger_pct = bt_be_pct,
                    time_stop_minutes     = float(bt_time_stop),
                )

                at = AutoTrader(
                    get_price  = broker.get_price,
                    place_buy  = broker.buy,
                    place_sell = broker.sell,
                    get_bars   = (lambda sym: data_client.get_stock_bars(
                                     StockBarsRequest(symbol_or_symbols=sym,
                                                      timeframe=TimeFrame.Day,
                                                      start=datetime.now() - timedelta(days=30))
                                 ).df.reset_index(level=0, drop=True))
                                 if bt_stop_mode == "ATR" else None,
                )
                at._on_close = lambda pnl: broker.close(pnl)
                at.start(bt_symbol, int(bt_qty), config=cfg)

                st.session_state.bt_at     = at
                st.session_state.bt_broker = broker
                st.session_state.bt_feed   = feed
                st.success(f"Backtest started — {bt_symbol} | {feed_type.split()[0]} feed | "
                           f"poll {poll_iv:.2f}s | log → {bt_output}")
            except Exception as e:
                st.error(str(e))
            st.rerun()

        if bt_stop and "bt_at" in st.session_state:
            st.session_state.bt_at.stop()
            st.info("Backtest stopped.")
            st.rerun()

        # ── Live status ───────────────────────────────────────────────────
        at = st.session_state.get("bt_at")
        if at:
            s = at.status
            state_col = {"idle": "gray", "entering": "blue", "watching": "green",
                         "sold": "blue", "stopped": "orange", "error": "red"}
            sc = state_col.get(s.state.value, "gray")
            st.markdown(f"**State:** :{sc}[{s.state.value.upper()}]")

            if s.state != TraderState.IDLE:
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Entry",   f"${s.entry_price:.2f}")
                m2.metric("Current", f"${s.current_price:.2f}")
                m3.metric("Peak",    f"${s.peak_price:.2f}")
                m4.metric("Stop",    f"${s.stop_floor:.2f}")
                pnl_col = "green" if s.pnl >= 0 else "red"
                m5.metric("P&L",     f"${s.pnl:+,.2f}")

                if s.threshold_pct:
                    pct = min(s.drawdown_pct / s.threshold_pct, 1.0)
                    st.progress(pct, text=f"Drawdown {s.drawdown_pct:.2f}% / {s.threshold_pct:.2f}%")

                feed = st.session_state.get("bt_feed")
                if isinstance(feed, ReplayPriceFeed):
                    st.progress(feed.progress,
                                text=f"Bar {feed.current_bar}/{feed.bar_count}  {feed.current_time}")
                    if feed.exhausted and s.state == TraderState.WATCHING:
                        st.warning("All bars replayed — AutoTrader still watching at last price.")

            if s.log:
                st.subheader("Trade Log")
                log_df = pd.DataFrame([{
                    "Time":   e.timestamp.strftime("%H:%M:%S"),
                    "Action": e.action,
                    "Price":  f"${e.price:.2f}" if e.price else "—",
                    "Note":   e.note,
                } for e in reversed(s.log)])
                st.dataframe(log_df, width="stretch", hide_index=True)

            if s.state in (TraderState.SOLD, TraderState.STOPPED):
                broker_obj = st.session_state.get("bt_broker")
                fills = broker_obj.fills if broker_obj else []
                buys  = [f for f in fills if f["action"] == "BUY"]
                sells = [f for f in fills if f["action"] == "SELL"]
                pnl_color = "green" if s.pnl >= 0 else "red"
                st.info(
                    f"**Session complete** — "
                    f"P&L: **:{pnl_color}[${s.pnl:+,.2f}]** | "
                    f"Buys: {len(buys)} | Sells: {len(sells)} | "
                    f"Total fills: {len(fills)}"
                )

            if s.state == TraderState.WATCHING:
                time.sleep(1)
                st.rerun()

        st.divider()

        # ── Session history ───────────────────────────────────────────────
        st.subheader("Session History")
        if st.button("Refresh history"):
            st.rerun()
        sessions = load_sessions(bt_output)
        if sessions:
            rows = []
            for s in sessions:
                meta = s.get("meta", {})
                fills = s.get("fills", [])
                buys  = [f for f in fills if f["action"] == "BUY"]
                sells = [f for f in fills if f["action"] == "SELL"]
                rows.append({
                    "ID":       s.get("id", "—"),
                    "Started":  s.get("started_at", "")[:19],
                    "Closed":   s.get("closed_at", "open")[:19] if s.get("closed_at") else "open",
                    "Symbol":   meta.get("symbol", "—"),
                    "Feed":     meta.get("feed", "—"),
                    "Buys":     len(buys),
                    "Sells":    len(sells),
                    "P&L":      f"${s['pnl']:+,.2f}" if s.get("pnl") is not None else "—",
                })
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

            # Expandable fills per session
            for s in sessions[:5]:   # show last 5
                fills = s.get("fills", [])
                if not fills:
                    continue
                pnl_str = f"${s['pnl']:+,.2f}" if s.get('pnl') is not None else 'open'
                label = (f"Session {s.get('id','?')}  "
                         f"{s.get('meta',{}).get('symbol','?')}  "
                         f"P&L {pnl_str}")
                with st.expander(label):
                    st.dataframe(pd.DataFrame(fills), width="stretch", hide_index=True)
        else:
            st.info(f"No sessions recorded yet in `{DEFAULT_FILLS}`.")

# ══════════════════════════════════════════════════════════════════════════════
# IBKR DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
else:
    from ib_async import Stock, MarketOrder, LimitOrder, util

    ibkr_user    = env_get("IBKR_USERNAME")
    ibkr_pass    = env_get("IBKR_PASSWORD")
    trading_mode = env_get("IBKR_MODE", "paper")
    ibkr_client_id = 1

    if not ibkr_user or not ibkr_pass:
        st.warning("IBKR credentials not configured. Go to **Settings** to add them.")
        st.stop()

    gw = get_gateway(ibkr_user, ibkr_pass, trading_mode)
    ib = get_ib()
    api_port = 4002 if trading_mode == "paper" else 4001

    # ── Auto-start gateway and connect when credentials are present ───────────
    if not st.session_state.get("gw_start_attempted"):
        st.session_state.gw_start_attempted = True
        if not gw.is_running():
            with st.spinner("Starting IB Gateway via IBC…"):
                try:
                    gw.start()
                except Exception as e:
                    st.error(f"Gateway start failed: {e}")
            with st.spinner("Waiting for API port (up to 90 s)…"):
                gw.wait_for_api(timeout=90)
            st.rerun()

    if not ib.isConnected() and gw.api_port_open() and not st.session_state.get("ib_connect_attempted"):
        st.session_state.ib_connect_attempted = True
        try:
            ib.connect("127.0.0.1", api_port, clientId=ibkr_client_id)
        except Exception:
            pass
        st.rerun()

    st.title(f"Portfolio Dashboard (IBKR {'Paper' if trading_mode == 'paper' else 'Live'})")

    with st.container(border=True):
        st.subheader("Gateway")
        gw_running   = gw.is_running()
        api_open     = gw.api_port_open()
        ib_connected = ib.isConnected()

        s1, s2, s3 = st.columns(3)
        s1.metric("Process",    "Running"     if gw_running   else "Stopped",
                  delta_color="normal" if gw_running   else "inverse")
        s2.metric("API Port",   "Open"        if api_open     else "Closed",
                  delta_color="normal" if api_open     else "inverse")
        s3.metric("IB Session", "Connected"   if ib_connected else "Disconnected",
                  delta_color="normal" if ib_connected else "inverse")

        c1, c2, c3, c4 = st.columns(4)
        if c1.button("Start Gateway", disabled=gw_running):
            with st.spinner("Starting IB Gateway via IBC…"):
                gw.start()
            with st.spinner("Waiting for API port (up to 90s)…"):
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

    if not ib_connected:
        st.info("Start and connect to IB Gateway to see your portfolio.")
        st.stop()

    st.divider()

    summary = ib.accountSummary()
    tags = {v.tag: v.value for v in summary if v.currency in ("USD", "")}

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Net Liquidation", f"${float(tags.get('NetLiquidation', 0)):,.2f}")
    col2.metric("Total Cash",      f"${float(tags.get('TotalCashValue', 0)):,.2f}")
    col3.metric("Buying Power",    f"${float(tags.get('BuyingPower', 0)):,.2f}")
    col4.metric("Unrealized P&L",  f"${float(tags.get('UnrealizedPnL', 0)):,.2f}")
    col5.metric("Realized P&L",    f"${float(tags.get('RealizedPnL', 0)):,.2f}")

    st.divider()

    st.subheader("Open Positions")
    positions = ib.positions()
    if positions:
        st.dataframe(pd.DataFrame([{
            "Symbol":   p.contract.symbol,
            "SecType":  p.contract.secType,
            "Exchange": p.contract.exchange,
            "Qty":      p.position,
            "Avg Cost": f"${p.avgCost:.2f}",
        } for p in positions]), width="stretch", hide_index=True)

        fig = go.Figure(go.Bar(
            x=[p.contract.symbol for p in positions],
            y=[p.position for p in positions],
            text=[str(p.position) for p in positions],
            textposition="outside",
        ))
        fig.update_layout(title="Position Sizes", yaxis_title="Qty", height=350)
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No open positions.")

    st.divider()

    st.subheader("Place Order")
    with st.form("ibkr_order_form"):
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        sym        = c1.text_input("Symbol",   value="AAPL").upper()
        exchange   = c2.text_input("Exchange", value="SMART")
        currency   = c3.text_input("Currency", value="USD")
        side       = c4.selectbox("Side", ["BUY", "SELL"])
        order_type = c5.selectbox("Type", ["Market", "Limit"])
        qty        = c6.number_input("Qty", min_value=1, value=1, step=1)
        limit_px   = st.number_input("Limit Price", min_value=0.0, value=0.0, step=0.01,
                                      disabled=(order_type == "Market"))
        submitted  = st.form_submit_button("Submit Order", type="primary")

    if submitted:
        try:
            contract = Stock(sym, exchange, currency)
            order    = MarketOrder(side, qty) if order_type == "Market" else LimitOrder(side, qty, limit_px)
            trade    = ib.placeOrder(contract, order)
            ib.sleep(1)
            st.success(f"Order placed — Status: {trade.orderStatus.status}")
        except Exception as e:
            st.error(f"Order failed: {e}")

    st.divider()

    st.subheader("Open Orders")
    open_trades = ib.openTrades()
    if open_trades:
        st.dataframe(pd.DataFrame([{
            "Symbol": t.contract.symbol,
            "Side":   t.order.action,
            "Type":   t.order.orderType,
            "Qty":    t.order.totalQuantity,
            "Filled": t.orderStatus.filled,
            "Status": t.orderStatus.status,
        } for t in open_trades]), width="stretch", hide_index=True)

        if st.button("Cancel All Orders", type="secondary"):
            for t in open_trades:
                ib.cancelOrder(t.order)
            st.success("All open orders cancelled.")
            st.rerun()
    else:
        st.info("No open orders.")
