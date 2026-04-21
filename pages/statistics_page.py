"""statistics_page — price chart and live trade history."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta

from core import LIVE_FILLS_FILE
from replay import load_sessions


def render(data_client, broker, trading_client, ib, alpaca_is_live):
    st.subheader("Statistics")

    # ── Price Chart ───────────────────────────────────────────────────────
    st.markdown("#### Price Chart")
    chart_symbol = st.text_input(
        "Symbol", value=st.session_state.get("_chart_sym", "AAPL")
    ).upper()
    st.session_state["_chart_sym"] = chart_symbol

    if broker == "Alpaca":
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        timeframe_opt = st.selectbox("Timeframe", ["1D", "1W", "1M", "3M"], index=2,
                                     key="stats_tf")
        tf_map = {
            "1D": (1,  TimeFrame.Hour),
            "1W": (7,  TimeFrame.Hour),
            "1M": (30, TimeFrame.Day),
            "3M": (90, TimeFrame.Day),
        }
        days, tf = tf_map[timeframe_opt]
        if chart_symbol:
            try:
                bars = data_client.get_stock_bars(StockBarsRequest(
                    symbol_or_symbols=chart_symbol, timeframe=tf,
                    start=datetime.now() - timedelta(days=days),
                )).df
                if not bars.empty:
                    bars = bars.reset_index()
                    fig = go.Figure(go.Candlestick(
                        x=bars["timestamp"],
                        open=bars["open"], high=bars["high"],
                        low=bars["low"],   close=bars["close"],
                    ))
                    fig.update_layout(title=f"{chart_symbol} — {timeframe_opt}",
                                      xaxis_rangeslider_visible=False, height=400)
                    st.plotly_chart(fig, width="stretch")
                else:
                    st.info("No data returned for this symbol/timeframe.")
            except Exception as e:
                st.error(f"Chart error: {e}")
    else:
        # IBKR
        if chart_symbol and ib and ib.isConnected():
            try:
                from ib_async import Stock, util
                contract = Stock(chart_symbol, "SMART", "USD")
                bars_raw = ib.reqHistoricalData(
                    contract, endDateTime="", durationStr="30 D",
                    barSizeSetting="1 day", whatToShow="TRADES",
                    useRTH=True, formatDate=1, keepUpToDate=False,
                )
                if bars_raw:
                    df = util.df(bars_raw)
                    df.index = pd.to_datetime(df.index)
                    df = df.reset_index()
                    fig = go.Figure(go.Candlestick(
                        x=df["date"],
                        open=df["open"], high=df["high"],
                        low=df["low"],   close=df["close"],
                    ))
                    fig.update_layout(title=f"{chart_symbol} — 30D",
                                      xaxis_rangeslider_visible=False, height=400)
                    st.plotly_chart(fig, width="stretch")
                else:
                    st.info("No data returned.")
            except Exception as e:
                st.error(f"Chart error: {e}")
        elif not (ib and ib.isConnected()):
            st.info("Connect to IB Gateway to view charts.")

    st.divider()

    # ── Trade History ─────────────────────────────────────────────────────
    st.markdown("#### Trade History")
    live_sessions = load_sessions(LIVE_FILLS_FILE)
    if live_sessions:
        hist_rows = []
        for s in live_sessions:
            fills = s.get("fills", [])
            buys  = [f for f in fills if f["action"] == "BUY"]
            sells = [f for f in fills if f["action"] == "SELL"]
            hist_rows.append({
                "Started": s.get("started_at", "")[:19],
                "Closed":  s.get("closed_at", "")[:19] if s.get("closed_at") else "open",
                "Symbol":  s.get("meta", {}).get("symbol", "—"),
                "Buys":    len(buys),
                "Sells":   len(sells),
                "P&L":     f"${s['pnl']:+,.2f}" if s.get("pnl") is not None else "—",
            })
        st.dataframe(pd.DataFrame(hist_rows), width="stretch", hide_index=True)

        all_fills = []
        for s in live_sessions:
            sym = s.get("meta", {}).get("symbol", "")
            for f in s.get("fills", []):
                all_fills.append({**f, "symbol": f.get("symbol") or sym,
                                  "session_pnl": s.get("pnl")})
        if all_fills:
            csv_bytes = pd.DataFrame(all_fills).to_csv(index=False).encode()
            st.download_button("⬇ Download fills CSV", data=csv_bytes,
                               file_name="live_fills.csv", mime="text/csv")

        for s in live_sessions[:5]:
            fills = s.get("fills", [])
            if not fills:
                continue
            sym     = s.get("meta", {}).get("symbol", "?")
            pnl_str = f"${s['pnl']:+,.2f}" if s.get("pnl") is not None else "open"
            with st.expander(f"{sym}  {s.get('started_at','')[:10]}  P&L {pnl_str}"):
                st.dataframe(pd.DataFrame(fills), width="stretch", hide_index=True)
    else:
        st.caption("No live trades recorded yet.")
