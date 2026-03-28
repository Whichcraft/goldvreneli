import os
import time
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from version import __version__
from autotrader import AutoTrader, TraderState
from scanner import scan

# ── Config ────────────────────────────────────────────────────────────────────
st.set_page_config(page_title=f"Goldvreneli Trading v{__version__}", layout="wide")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Goldvreneli")
    st.caption(f"v{__version__}")

    st.divider()
    st.subheader("Broker")
    broker = st.radio("", ["Alpaca (Paper)", "IBKR"], label_visibility="collapsed")

    if broker == "Alpaca (Paper)":
        api_key    = st.text_input("API Key",    value=os.environ.get("ALPACA_PAPER_API_KEY", ""),    type="password")
        secret_key = st.text_input("Secret Key", value=os.environ.get("ALPACA_PAPER_SECRET_KEY", ""), type="password")
        if not api_key or not secret_key:
            st.warning("Enter your Alpaca paper API keys.")
            st.stop()
    else:
        ibkr_user = st.text_input("IBKR Username", value=os.environ.get("IBKR_USERNAME", ""))
        ibkr_pass = st.text_input("IBKR Password", value=os.environ.get("IBKR_PASSWORD", ""), type="password")
        trading_mode = st.selectbox("Mode", ["paper", "live"])
        ibkr_client_id = st.number_input("Client ID", value=1)
        st.caption("Paper port: 4002 | Live port: 4001")

    st.divider()
    st.subheader("Navigation")
    if broker == "Alpaca (Paper)":
        page = st.radio("", ["Portfolio", "AutoTrader", "Scanner"], label_visibility="collapsed")
    else:
        page = st.radio("", ["Portfolio"], label_visibility="collapsed")

    st.divider()
    with st.expander("About"):
        st.markdown(f"""
**Goldvreneli Trading**
Version `{__version__}`

**Features**
- Portfolio overview & orders
- AutoTrader (trailing stop)
- Position Scanner

**Brokers**
- Alpaca Paper Trading
- IBKR (via IB Gateway)
        """)


# ── Alpaca helpers ────────────────────────────────────────────────────────────
@st.cache_resource
def get_alpaca_clients(api_key, secret_key):
    from alpaca.trading.client import TradingClient
    from alpaca.data.historical import StockHistoricalDataClient
    trading = TradingClient(api_key=api_key, secret_key=secret_key, paper=True)
    data    = StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)
    return trading, data

# ── IBKR helpers ──────────────────────────────────────────────────────────────
def get_gateway():
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
# ALPACA DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if broker == "Alpaca (Paper)":
    from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, GetOrdersRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from datetime import datetime, timedelta

    try:
        trading_client, data_client = get_alpaca_clients(api_key, secret_key)
    except Exception as e:
        st.error(f"Alpaca connection failed: {e}")
        st.stop()

    account = trading_client.get_account()

    st.title("Portfolio Dashboard (Alpaca Paper)")

    # ── Page: Portfolio ───────────────────────────────────────────────────────
    if page == "Portfolio":
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Portfolio Value", f"${float(account.portfolio_value):,.2f}")
        col2.metric("Cash",            f"${float(account.cash):,.2f}")
        col3.metric("Buying Power",    f"${float(account.buying_power):,.2f}")
        col4.metric("Equity",          f"${float(account.equity):,.2f}")

        st.divider()

        # Positions
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
            st.dataframe(pd.DataFrame(pos_data), use_container_width=True, hide_index=True)

            fig = go.Figure(go.Bar(
                x=[p.symbol for p in positions],
                y=[float(p.unrealized_pl) for p in positions],
                marker_color=["green" if float(p.unrealized_pl) >= 0 else "red" for p in positions],
                text=[f"${float(p.unrealized_pl):,.2f}" for p in positions],
                textposition="outside",
            ))
            fig.update_layout(title="Unrealized P&L by Position", yaxis_title="P&L ($)", height=350)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No open positions.")

        st.divider()

        # Price chart
        st.subheader("Price Chart")
        chart_symbol  = st.text_input("Symbol", value="AAPL").upper()
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
                    st.plotly_chart(fig2, use_container_width=True)
            except Exception as e:
                st.error(f"Chart error: {e}")

        st.divider()

        # Place Order
        st.subheader("Place Order")
        with st.form("order_form"):
            c1, c2, c3, c4, c5 = st.columns(5)
            sym        = c1.text_input("Symbol", value="AAPL").upper()
            side       = c2.selectbox("Side", ["BUY", "SELL"])
            order_type = c3.selectbox("Type", ["Market", "Limit"])
            qty        = c4.number_input("Qty", min_value=0.0, value=1.0, step=1.0)
            limit_px   = c5.number_input("Limit Price", min_value=0.0, value=0.0, step=0.01,
                                          disabled=(order_type == "Market"))
            submitted  = st.form_submit_button("Submit Order", type="primary")

        if submitted:
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

        # Open Orders
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
            } for o in open_orders]), use_container_width=True, hide_index=True)
            if st.button("Cancel All Orders", type="secondary"):
                trading_client.cancel_orders()
                st.success("All open orders cancelled.")
                st.rerun()
        else:
            st.info("No open orders.")

    # ── Page: AutoTrader ─────────────────────────────────────────────────────
    elif page == "AutoTrader":
        st.subheader("AutoTrader — Trailing Stop")
        st.caption("Buys a position and sells automatically when price drops below the trailing stop threshold.")

        # Alpaca price fetcher
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

        # Init AutoTrader in session state
        if "autotrader" not in st.session_state:
            st.session_state.autotrader = AutoTrader(
                get_price=alpaca_get_price,
                place_buy=alpaca_buy,
                place_sell=alpaca_sell,
            )
        at = st.session_state.autotrader
        s  = at.status

        # Config form
        with st.form("at_config"):
            c1, c2, c3, c4 = st.columns(4)
            at_symbol    = c1.text_input("Symbol", value="AAPL").upper()
            at_qty       = c2.number_input("Qty", min_value=1, value=1, step=1)
            at_threshold = c3.number_input("Trailing Stop %", min_value=0.1, max_value=10.0,
                                            value=0.5, step=0.1,
                                            help="Sell when price drops this % below peak")
            at_poll      = c4.number_input("Poll interval (s)", min_value=1, value=5, step=1)
            col_start, col_stop = st.columns(2)
            start_btn = col_start.form_submit_button("▶ Start AutoTrader", type="primary")
            stop_btn  = col_stop.form_submit_button("⏹ Stop")

        if start_btn:
            if s.state == TraderState.WATCHING:
                st.warning("AutoTrader already running.")
            else:
                at._poll_interval = at_poll
                try:
                    at.start(at_symbol, int(at_qty), threshold_pct=at_threshold)
                    st.success(f"AutoTrader started: {at_symbol} | Stop at {at_threshold}%")
                except Exception as e:
                    st.error(f"Failed to start: {e}")
            st.rerun()

        if stop_btn and s.state == TraderState.WATCHING:
            at.stop()
            st.info("AutoTrader stopped.")
            st.rerun()

        # Status panel
        state_color = {
            TraderState.IDLE:     "gray",
            TraderState.WATCHING: "green",
            TraderState.SOLD:     "blue",
            TraderState.STOPPED:  "orange",
            TraderState.ERROR:    "red",
        }
        st.markdown(f"**Status:** :{state_color[s.state]}[{s.state.value.upper()}]")

        if s.state in (TraderState.WATCHING, TraderState.SOLD, TraderState.STOPPED):
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Symbol",      s.symbol)
            m2.metric("Entry",       f"${s.entry_price:.2f}")
            m3.metric("Peak",        f"${s.peak_price:.2f}")
            m4.metric("Current",     f"${s.current_price:.2f}")
            m5.metric("Drawdown",    f"{s.drawdown_pct:.2f}%",
                      delta=f"Stop @ {s.threshold_pct}%", delta_color="inverse")

            pnl_color = "green" if s.pnl >= 0 else "red"
            st.markdown(f"**P&L:** :{pnl_color}[${s.pnl:,.2f}]")

            # Progress bar: drawdown vs threshold
            pct = min(s.drawdown_pct / s.threshold_pct, 1.0) if s.threshold_pct else 0
            st.progress(pct, text=f"Drawdown {s.drawdown_pct:.2f}% / {s.threshold_pct}% threshold")

        # Activity log
        if s.log:
            st.subheader("Activity Log")
            log_data = [{"Time": e.timestamp.strftime("%H:%M:%S"),
                         "Action": e.action,
                         "Price": f"${e.price:.2f}",
                         "Note": e.note} for e in reversed(s.log)]
            st.dataframe(pd.DataFrame(log_data), use_container_width=True, hide_index=True)

        # Auto-refresh while watching
        if s.state == TraderState.WATCHING:
            time.sleep(at._poll_interval)
            st.rerun()

    # ── Page: Scanner ────────────────────────────────────────────────────────
    elif page == "Scanner":
        st.subheader("Position Scanner")
        st.caption("Scans ~60 liquid US stocks and ETFs, applies technical filters, proposes the top 10.")

        col_a, col_b = st.columns([1, 3])
        top_n   = col_a.number_input("Top N results", min_value=1, max_value=30, value=10)
        run_scan = col_b.button("Run Scan", type="primary")

        with st.expander("Filters applied"):
            st.markdown("""
| Filter | Condition |
|--------|-----------|
| Price  | > SMA20 and > SMA50 (uptrend) |
| RSI(14)| 40 – 65 (momentum, not overbought) |
| Volume | > 1.5× 20-day average |
| Liquidity | Price > $5, ADV > $5M |
| Momentum | 5-day return > 0% |
| Score | Weighted: 5d return × 2, 20d return × 0.5, RSI quality, MACD histogram |
""")

        if run_scan:
            progress_bar = st.progress(0, text="Scanning…")
            status_text  = st.empty()

            def on_progress(done, total):
                progress_bar.progress(done / total, text=f"Scanning {done}/{total}…")

            with st.spinner("Running scan…"):
                results = scan(data_client, top_n=int(top_n), progress_cb=on_progress)

            progress_bar.empty()

            if results.empty:
                st.warning("No symbols passed all filters. Try again during market hours.")
            else:
                st.success(f"Found {len(results)} candidates.")
                st.dataframe(results, use_container_width=True)

                # Bar chart: 5d return
                fig_scan = go.Figure(go.Bar(
                    x=results.index,
                    y=results["5d Ret%"],
                    marker_color=["green" if v >= 0 else "red" for v in results["5d Ret%"]],
                    text=[f"{v:.2f}%" for v in results["5d Ret%"]],
                    textposition="outside",
                ))
                fig_scan.update_layout(title="5-Day Return % — Top Candidates",
                                       yaxis_title="5d Return %", height=350)
                st.plotly_chart(fig_scan, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# IBKR DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
else:
    from ib_async import Stock, MarketOrder, LimitOrder, util

    if not ibkr_user or not ibkr_pass:
        st.warning("Enter IBKR credentials in the sidebar.")
        st.stop()

    gw = get_gateway()
    ib = get_ib()

    api_port = 4002 if trading_mode == "paper" else 4001

    # ── Gateway control panel ─────────────────────────────────────────────────
    st.title(f"Portfolio Dashboard (IBKR {'Paper' if trading_mode == 'paper' else 'Live'})")

    with st.container(border=True):
        st.subheader("Gateway")
        gw_running  = gw.is_running()
        api_open    = gw.api_port_open()
        ib_connected = ib.isConnected()

        s1, s2, s3 = st.columns(3)
        s1.metric("Process",    "Running" if gw_running  else "Stopped",
                  delta_color="normal" if gw_running  else "inverse")
        s2.metric("API Port",   "Open"    if api_open    else "Closed",
                  delta_color="normal" if api_open    else "inverse")
        s3.metric("IB Session", "Connected" if ib_connected else "Disconnected",
                  delta_color="normal" if ib_connected else "inverse")

        c1, c2, c3, c4 = st.columns(4)

        if c1.button("Start Gateway", disabled=gw_running):
            with st.spinner("Starting IB Gateway via IBC…"):
                gw.start()
            with st.spinner("Waiting for API port (up to 90s)…"):
                ready = gw.wait_for_api(timeout=90)
            if ready:
                st.success("Gateway ready.")
            else:
                st.error("Timed out. Check logs below.")
            st.rerun()

        if c2.button("Connect", disabled=(not api_open or ib_connected)):
            try:
                ib.connect("127.0.0.1", api_port, clientId=int(ibkr_client_id))
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

    # ── Account summary ───────────────────────────────────────────────────────
    summary = ib.accountSummary()
    tags = {v.tag: v.value for v in summary if v.currency in ("USD", "")}

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Net Liquidation",  f"${float(tags.get('NetLiquidation', 0)):,.2f}")
    col2.metric("Total Cash",       f"${float(tags.get('TotalCashValue', 0)):,.2f}")
    col3.metric("Buying Power",     f"${float(tags.get('BuyingPower', 0)):,.2f}")
    col4.metric("Unrealized P&L",   f"${float(tags.get('UnrealizedPnL', 0)):,.2f}")

    st.divider()

    # ── Positions ─────────────────────────────────────────────────────────────
    st.subheader("Open Positions")
    positions = ib.positions()
    if positions:
        pos_data = [{
            "Symbol":   p.contract.symbol,
            "SecType":  p.contract.secType,
            "Exchange": p.contract.exchange,
            "Qty":      p.position,
            "Avg Cost": f"${p.avgCost:.2f}",
        } for p in positions]
        st.dataframe(pd.DataFrame(pos_data), use_container_width=True, hide_index=True)

        fig = go.Figure(go.Bar(
            x=[p.contract.symbol for p in positions],
            y=[p.position for p in positions],
            text=[str(p.position) for p in positions],
            textposition="outside",
        ))
        fig.update_layout(title="Position Sizes", yaxis_title="Qty", height=350)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No open positions.")

    st.divider()

    # ── Place Order ───────────────────────────────────────────────────────────
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

    # ── Open Orders ───────────────────────────────────────────────────────────
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
        } for t in open_trades]), use_container_width=True, hide_index=True)

        if st.button("Cancel All Orders", type="secondary"):
            for t in open_trades:
                ib.cancelOrder(t.order)
            st.success("All open orders cancelled.")
            st.rerun()
    else:
        st.info("No open orders.")
