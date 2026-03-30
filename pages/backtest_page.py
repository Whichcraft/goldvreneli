import os
import time
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, time as dtime

from replay import ReplayPriceFeed, SyntheticPriceFeed, MockBroker, load_sessions
from autotrader import AutoTrader, TraderConfig, TraderState, StopMode, EntryMode
from core import INSTALL_DIR, env_get


def render(data_client, broker):
    st.subheader("Backtest / Test Mode")
    st.caption("Replay historical data or generate synthetic prices to test AutoTrader logic outside market hours.")

    DEFAULT_FILLS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backtest_fills.json")

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
                from alpaca.data.requests import StockBarsRequest
                from alpaca.data.timeframe import TimeFrame
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

            bt_broker_obj = MockBroker(
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

            if bt_stop_mode == "ATR":
                from alpaca.data.requests import StockBarsRequest
                from alpaca.data.timeframe import TimeFrame
                _get_bars_for_atr = (lambda sym: data_client.get_stock_bars(
                    StockBarsRequest(symbol_or_symbols=sym,
                                     timeframe=TimeFrame.Day,
                                     start=datetime.now() - timedelta(days=30))
                ).df.reset_index(level=0, drop=True))
            else:
                _get_bars_for_atr = None

            at = AutoTrader(
                get_price  = bt_broker_obj.get_price,
                place_buy  = bt_broker_obj.buy,
                place_sell = bt_broker_obj.sell,
                get_bars   = _get_bars_for_atr,
            )
            at._on_close = lambda pnl: bt_broker_obj.close(pnl)
            at.start(bt_symbol, int(bt_qty), config=cfg)

            st.session_state.bt_at     = at
            st.session_state.bt_broker = bt_broker_obj
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

        # ── CSV export ────────────────────────────────────────────────────────
        all_fills = []
        for s in sessions:
            sym = s.get("meta", {}).get("symbol", "")
            for f in s.get("fills", []):
                all_fills.append({**f, "symbol": f.get("symbol") or sym,
                                  "session_id": s.get("id"),
                                  "session_pnl": s.get("pnl")})
        if all_fills:
            csv_bytes = pd.DataFrame(all_fills).to_csv(index=False).encode()
            st.download_button("⬇ Download fills CSV", data=csv_bytes,
                               file_name="backtest_fills.csv", mime="text/csv")

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
