import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

from core import env_get, get_alpaca_clients
from scanner import UNIVERSE


def render(broker, trading_client, data_client, account, ib, gw, alpaca_is_live, ibkr_is_live,
           get_bars_fn):
    if broker == "Alpaca":
        _render_alpaca(trading_client, data_client, account, ib, alpaca_is_live)
    else:
        _render_ibkr(ib, gw, ibkr_is_live)


def _render_alpaca(trading_client, data_client, account, ib, alpaca_is_live):
    from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, GetOrdersRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    _mode_label = "Live" if alpaca_is_live else "Paper"

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

    # ── Quick actions: ticker strip + cash-out (#48 / #49) ────────────────────
    try:
        _all_pos = trading_client.get_all_positions()
    except Exception:
        _all_pos = []

    if _all_pos:
        _sorted_pos = sorted(_all_pos, key=lambda p: float(p.unrealized_plpc), reverse=True)
        _top3       = _sorted_pos[:3]
        _bot3       = _sorted_pos[-3:][::-1]   # worst → best within losers

        # Session-scoped dismissed-symbol set — prune symbols no longer open
        _open_syms = {p.symbol for p in _all_pos}
        _dismissed = st.session_state.setdefault("_portfolio_dismissed", set())
        _dismissed &= _open_syms

        def _ticker_card(col, p, action_label, *, sell_fn):
            plpc  = float(p.unrealized_plpc) * 100
            color = "green" if plpc >= 0 else "red"
            col.markdown(f"**{p.symbol}**  :{color}[{plpc:+.1f}%]")
            if action_label == "Keep":
                if col.button("Keep", key=f"keep_{p.symbol}", use_container_width=True):
                    _dismissed.add(p.symbol)
                    st.rerun()
            else:
                confirmed = col.checkbox("Confirm", key=f"sell_confirm_{p.symbol}")
                if col.button("Sell", key=f"sell_{p.symbol}", use_container_width=True,
                              disabled=not confirmed):
                    sell_fn(p)
                    st.rerun()

        def _do_sell(p):
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce
            trading_client.submit_order(MarketOrderRequest(
                symbol=p.symbol, qty=abs(float(p.qty)),
                side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
            ))

        # Winners strip
        winner_cols = st.columns(3)
        shown_winners = [p for p in _top3
                         if p.symbol not in _dismissed and float(p.unrealized_plpc) > 0]
        for col, p in zip(winner_cols, shown_winners):
            with col.container(border=True):
                _ticker_card(col, p, "Keep", sell_fn=_do_sell)

        # Losers strip
        loser_cols = st.columns(3)
        shown_losers = [p for p in _bot3
                        if p.symbol not in _dismissed and float(p.unrealized_plpc) < 0]
        for col, p in zip(loser_cols, shown_losers):
            with col.container(border=True):
                _ticker_card(col, p, "Sell", sell_fn=_do_sell)

        # Cash-out all panel
        with st.expander("☢️ Cash out all positions"):
            st.warning(
                f"This will immediately sell all **{len(_all_pos)} open positions** "
                "using market orders. This cannot be undone.",
                icon="⚠️",
            )
            _confirmed_all = st.checkbox("I understand — sell everything", key="_cashout_all_confirm")
            if st.button("Cash Out All", type="primary", disabled=not _confirmed_all):
                _errors = []
                for _p in _all_pos:
                    try:
                        _do_sell(_p)
                    except Exception as _e:
                        _errors.append(f"{_p.symbol}: {_e}")
                if _errors:
                    st.error("Some orders failed:\n" + "\n".join(_errors))
                else:
                    st.success(f"Sell orders submitted for {len(_all_pos)} positions.")
                st.rerun()

    st.divider()

    st.subheader("Open Positions")

    def _render_alpaca_positions(tc, label):
        try:
            pos = tc.get_all_positions()
        except Exception as _e:
            st.caption(f"{label}: could not fetch — {_e}")
            return
        st.caption(f"**{label}**")
        if pos:
            pos_data = [{
                "Symbol":       p.symbol,
                "Shares":       float(p.qty),
                "Avg Entry":    f"${float(p.avg_entry_price):.2f}",
                "Current":      f"${float(p.current_price):.2f}",
                "Market Value": f"${float(p.market_value):,.2f}",
                "P&L ($)":      f"${float(p.unrealized_pl):,.2f}",
                "P&L (%)":      f"{float(p.unrealized_plpc)*100:.2f}%",
            } for p in pos]
            st.dataframe(pd.DataFrame(pos_data), width='stretch', hide_index=True)
            fig = go.Figure(go.Bar(
                x=[p.symbol for p in pos],
                y=[float(p.unrealized_pl) for p in pos],
                marker_color=["green" if float(p.unrealized_pl) >= 0 else "red" for p in pos],
                text=[f"${float(p.unrealized_pl):,.2f}" for p in pos],
                textposition="outside",
            ))
            fig.update_layout(title=f"Unrealized P&L — {label}", yaxis_title="P&L ($)", height=300)
            st.plotly_chart(fig, width='stretch')
        else:
            st.info(f"No open positions in {label}. Go to **🔍 Scanner** to find the best stocks and invest with one click.")

    # Current Alpaca account
    _render_alpaca_positions(trading_client, f"Alpaca {_mode_label}")

    # Other Alpaca account (if keys configured)
    _other_key    = env_get("ALPACA_LIVE_API_KEY"    if not alpaca_is_live else "ALPACA_PAPER_API_KEY")
    _other_secret = env_get("ALPACA_LIVE_SECRET_KEY" if not alpaca_is_live else "ALPACA_PAPER_SECRET_KEY")
    if _other_key and _other_secret:
        try:
            _other_tc, _ = get_alpaca_clients(_other_key, _other_secret, paper=alpaca_is_live)
            _render_alpaca_positions(_other_tc, f"Alpaca {'Paper' if alpaca_is_live else 'Live'}")
        except Exception:
            pass

    # IBKR positions if connected
    try:
        if ib and ib.isConnected():
            _ib_pos = ib.positions()
            st.caption("**IBKR**")
            if _ib_pos:
                st.dataframe(pd.DataFrame([{
                    "Symbol":   p.contract.symbol,
                    "SecType":  p.contract.secType,
                    "Qty":      p.position,
                    "Avg Cost": f"${p.avgCost:.2f}",
                } for p in _ib_pos]), width='stretch', hide_index=True)
            else:
                st.info("No open positions in IBKR.")
    except Exception:
        pass

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
    _universe_opts = sorted(set(UNIVERSE))
    _default_sym   = st.session_state.get("_order_sym", "AAPL")
    _default_idx   = _universe_opts.index(_default_sym) if _default_sym in _universe_opts else 0
    with st.form("order_form"):
        c1, c2, c3, c4, c5 = st.columns(5)
        sym        = c1.selectbox("Symbol", _universe_opts, index=_default_idx,
                                   help="Start typing to filter — pick any stock or ETF from the universe").upper()
        side       = c2.selectbox("Side", ["BUY", "SELL"])
        order_type = c3.selectbox("Type", ["Market", "Limit"])
        qty        = c4.number_input("Shares", min_value=1.0, value=1.0, step=1.0)
        limit_px   = c5.number_input("Limit Price", min_value=0.0, value=0.0, step=0.01,
                                      disabled=(order_type == "Market"))
        submitted  = st.form_submit_button("Submit Order", type="primary")
    if submitted:
        st.session_state["_order_sym"] = sym
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


def _render_ibkr(ib, gw, ibkr_is_live):
    from ib_async import Stock, MarketOrder, LimitOrder

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
    _ib_universe_opts = sorted(set(UNIVERSE))
    _ib_default_sym   = st.session_state.get("_ibkr_order_sym", "AAPL")
    _ib_default_idx   = _ib_universe_opts.index(_ib_default_sym) if _ib_default_sym in _ib_universe_opts else 0
    with st.form("ibkr_order_form"):
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        sym        = c1.selectbox("Symbol", _ib_universe_opts, index=_ib_default_idx,
                                   help="Start typing to filter symbols").upper()
        exchange   = c2.text_input("Exchange", value="SMART")
        currency   = c3.text_input("Currency", value="USD")
        side       = c4.selectbox("Side", ["BUY", "SELL"])
        order_type = c5.selectbox("Type", ["Market", "Limit"])
        qty        = c6.number_input("Qty", min_value=1, value=1, step=1)
        limit_px   = st.number_input("Limit Price", min_value=0.0, value=0.0, step=0.01,
                                      disabled=(order_type == "Market"))
        submitted  = st.form_submit_button("Submit Order", type="primary")
    if submitted:
        st.session_state["_ibkr_order_sym"] = sym
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
