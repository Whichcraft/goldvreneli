import os
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Goldvreneli Trading", layout="wide")

API_KEY    = os.environ.get("ALPACA_PAPER_API_KEY", "")
SECRET_KEY = os.environ.get("ALPACA_PAPER_SECRET_KEY", "")

# ── Sidebar: credentials ──────────────────────────────────────────────────────
with st.sidebar:
    st.title("Goldvreneli")
    st.subheader("API Keys")
    api_key    = st.text_input("API Key",    value=API_KEY,    type="password")
    secret_key = st.text_input("Secret Key", value=SECRET_KEY, type="password")
    paper      = st.checkbox("Paper Trading", value=True)

    if not api_key or not secret_key:
        st.warning("Enter your Alpaca API keys to continue.")
        st.stop()

@st.cache_resource
def get_clients(api_key, secret_key, paper):
    trading = TradingClient(api_key=api_key, secret_key=secret_key, paper=paper)
    data    = StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)
    return trading, data

try:
    trading_client, data_client = get_clients(api_key, secret_key, paper)
except Exception as e:
    st.error(f"Connection failed: {e}")
    st.stop()

# ── Account overview ──────────────────────────────────────────────────────────
account = trading_client.get_account()

st.title("Portfolio Dashboard" + (" (Paper)" if paper else " (Live)"))

col1, col2, col3, col4 = st.columns(4)
col1.metric("Portfolio Value", f"${float(account.portfolio_value):,.2f}")
col2.metric("Cash",            f"${float(account.cash):,.2f}")
col3.metric("Buying Power",    f"${float(account.buying_power):,.2f}")
col4.metric("Equity",          f"${float(account.equity):,.2f}")

st.divider()

# ── Positions ─────────────────────────────────────────────────────────────────
st.subheader("Open Positions")
positions = trading_client.get_all_positions()

if positions:
    pos_data = [{
        "Symbol":      p.symbol,
        "Qty":         float(p.qty),
        "Avg Entry":   f"${float(p.avg_entry_price):.2f}",
        "Current":     f"${float(p.current_price):.2f}",
        "Market Value":f"${float(p.market_value):,.2f}",
        "P&L ($)":     f"${float(p.unrealized_pl):,.2f}",
        "P&L (%)":     f"{float(p.unrealized_plpc)*100:.2f}%",
        "Side":        p.side.value,
    } for p in positions]

    df_pos = pd.DataFrame(pos_data)
    st.dataframe(df_pos, use_container_width=True, hide_index=True)

    # P&L bar chart
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

# ── Price chart ───────────────────────────────────────────────────────────────
st.subheader("Price Chart")
chart_symbol = st.text_input("Symbol", value="AAPL").upper()
timeframe_opt = st.selectbox("Timeframe", ["1D", "1W", "1M", "3M"], index=2)

tf_map   = {"1D": (1,  TimeFrame.Hour),  "1W": (7,  TimeFrame.Hour),
            "1M": (30, TimeFrame.Day),   "3M": (90, TimeFrame.Day)}
days, tf = tf_map[timeframe_opt]

if chart_symbol:
    try:
        bars_req = StockBarsRequest(
            symbol_or_symbols=chart_symbol,
            timeframe=tf,
            start=datetime.now() - timedelta(days=days),
        )
        bars = data_client.get_stock_bars(bars_req).df

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
        else:
            st.warning("No data returned for that symbol/timeframe.")
    except Exception as e:
        st.error(f"Could not fetch chart data: {e}")

st.divider()

# ── Place Order ───────────────────────────────────────────────────────────────
st.subheader("Place Order")

with st.form("order_form"):
    c1, c2, c3, c4, c5 = st.columns(5)
    sym       = c1.text_input("Symbol", value="AAPL").upper()
    side      = c2.selectbox("Side", ["BUY", "SELL"])
    order_type= c3.selectbox("Type", ["Market", "Limit"])
    qty       = c4.number_input("Qty", min_value=0.0, value=1.0, step=1.0)
    limit_px  = c5.number_input("Limit Price", min_value=0.0, value=0.0, step=0.01,
                                 disabled=(order_type == "Market"))
    submitted = st.form_submit_button("Submit Order", type="primary")

if submitted:
    try:
        order_side = OrderSide.BUY if side == "BUY" else OrderSide.SELL
        if order_type == "Market":
            req = MarketOrderRequest(symbol=sym, qty=qty,
                                     side=order_side, time_in_force=TimeInForce.DAY)
        else:
            req = LimitOrderRequest(symbol=sym, qty=qty, limit_price=limit_px,
                                    side=order_side, time_in_force=TimeInForce.GTC)
        order = trading_client.submit_order(req)
        st.success(f"Order submitted — ID: {order.id} | Status: {order.status}")
    except Exception as e:
        st.error(f"Order failed: {e}")

st.divider()

# ── Open Orders ───────────────────────────────────────────────────────────────
st.subheader("Open Orders")
open_orders = trading_client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN))

if open_orders:
    ord_data = [{
        "ID":     str(o.id)[:8] + "…",
        "Symbol": o.symbol,
        "Side":   o.side.value,
        "Type":   o.order_type.value,
        "Qty":    float(o.qty),
        "Filled": float(o.filled_qty),
        "Limit":  f"${float(o.limit_price):.2f}" if o.limit_price else "—",
        "Status": o.status.value,
    } for o in open_orders]
    st.dataframe(pd.DataFrame(ord_data), use_container_width=True, hide_index=True)

    if st.button("Cancel All Orders", type="secondary"):
        trading_client.cancel_orders()
        st.success("All open orders cancelled.")
        st.rerun()
else:
    st.info("No open orders.")
