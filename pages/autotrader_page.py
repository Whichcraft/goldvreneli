import time
import streamlit as st
import pandas as pd

from autotrader import TraderState, TraderConfig, StopMode, EntryMode, size_from_risk
from replay import load_sessions
from core import LIVE_FILLS_FILE, env_get
from activity_tracker import render_log


def render(mt, get_price_fn, buy_fn, sell_fn, get_bars_fn, get_equity_fn, broker,
           trading_client, ib):
    st.subheader("AutoTrader — Multi-Position Manager")
    st.caption("Enters positions and exits automatically via trailing stop, take-profit, breakeven, or time stop.")

    # ── New position form ─────────────────────────────────────────────
    # Handle multi-symbol prefill from Scanner.
    # at_prefill_list / at_prefill are one-shot signals written by the
    # Scanner page. We immediately move their value into at_current_symbol
    # (which survives reruns) so the form stays filled on every rerender.
    _prefill_list = st.session_state.pop("at_prefill_list", None)
    _prefill_single = st.session_state.pop("at_prefill", None)
    if _prefill_list:
        st.session_state["at_current_symbol"] = _prefill_list[0]
        _queued = _prefill_list[1:]
        if _queued:
            st.session_state["at_queue"] = _queued
        else:
            st.session_state.pop("at_queue", None)
    elif _prefill_single:
        st.session_state["at_current_symbol"] = _prefill_single

    _default_symbol = st.session_state.get("at_current_symbol") or env_get("AT_SYMBOL", "")

    # Qty sizing — outside form so radio switches update inputs immediately
    qty_mode = st.radio("Qty mode", ["Shares", "Dollar amount", "Risk %"],
                        horizontal=True, label_visibility="collapsed", key="at_qty_mode")

    # Determine account equity for Risk % mode
    _account_equity = 10000.0
    if broker == "Alpaca" and trading_client is not None:
        try:
            _account_equity = float(trading_client.get_account().equity)
        except Exception:
            pass
    elif broker == "IBKR" and ib is not None and ib.isConnected():
        try:
            _account_equity = get_equity_fn()
        except Exception:
            pass

    if qty_mode == "Shares":
        at_qty = st.number_input("Qty (shares)", min_value=1, value=1, step=1, key="at_qty_shares")
    elif qty_mode == "Dollar amount":
        qc1, qc2 = st.columns(2)
        at_dollar_amt = qc1.number_input("$ amount to invest", min_value=1.0,
                                          value=1000.0, step=100.0, key="at_dollar_amt")
        at_price_est  = qc2.number_input("Est. price per share ($)", min_value=0.01,
                                          value=100.0, step=1.0, key="at_price_est")
        at_qty = max(1, int(at_dollar_amt / at_price_est))
        st.caption(f"≈ **{at_qty}** shares @ ${at_price_est:.2f} = ${at_qty * at_price_est:,.2f}")
    else:  # Risk %
        rc1, rc2, rc3, rc4 = st.columns(4)
        at_equity    = rc1.number_input("Account equity ($)", min_value=1.0,
                                         value=_account_equity,
                                         step=500.0, key="at_equity")
        at_risk_pct  = rc2.number_input("Risk per trade (%)", min_value=0.1,
                                         max_value=10.0, value=1.0, step=0.1, key="at_risk_pct")
        at_entry_est = rc3.number_input("Est. entry price ($)", min_value=0.01,
                                         value=100.0, step=1.0, key="at_entry_est")
        at_stop_est  = rc4.number_input("Est. stop %", min_value=0.1, max_value=20.0,
                                         value=float(env_get("AT_THRESHOLD", "0.5")), step=0.1,
                                         key="at_stop_est")
        stop_dist_est = at_entry_est * at_stop_est / 100
        at_qty = size_from_risk(at_equity, at_risk_pct, at_entry_est, stop_dist_est)
        st.caption(f"**{at_qty}** shares — risking "
                   f"${at_equity * at_risk_pct / 100:,.2f} @ ${stop_dist_est:.2f} stop dist")

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
                    # Advance to next symbol immediately so the form is ready
                    st.session_state["at_current_symbol"] = queue[0]
                    remaining = queue[1:]
                    if remaining:
                        st.session_state["at_queue"] = remaining
                    st.success(f"Started {at_symbol}. Next in queue: {queue[0]}")
                else:
                    st.session_state.pop("at_current_symbol", None)
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

    # ── Live positions (fragment — refreshes independently of the form above)
    @st.fragment
    def _live_view():
        statuses = mt.statuses()
        if not statuses:
            scan_done = st.session_state.get("scan_ts") is not None
            scan_has_results = not st.session_state.get("scan_results", pd.DataFrame()).empty
            if not scan_done:
                st.info(
                    "💡 **No positions yet.** "
                    "Go to **🔍 Scanner** first to find the best stocks, "
                    "then use **⚡ Quick Invest** to open positions in one click — "
                    "or configure a symbol manually in the form above."
                )
            elif scan_has_results:
                st.info(
                    "💡 **Scanner results are ready.** "
                    "Go to **🔍 Scanner → ⚡ Quick Invest** to open positions, "
                    "or fill in the symbol form above."
                )
            else:
                st.info("💡 Configure a symbol above and click **Start** to open a position.")
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
            dl1.metric("Unrealized P&L (active)", f"${mt.unrealized_pnl():+,.2f}")
            dl2.metric("Realized P&L today",     f"${mt.realized_losses():+,.2f}")

            # Combined log
            render_log(mt)

        # ── Live trade history ────────────────────────────────────────────────
        st.divider()
        st.subheader("Trade History")
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

        # Auto-refresh the fragment while any position is active, or once more
        # when the session count changes (catches auto-sell writing a new entry)
        session_count = len(live_sessions)
        prev_count = st.session_state.get("_hist_session_count", session_count)
        st.session_state["_hist_session_count"] = session_count
        has_active = any(s.state in (TraderState.ENTERING, TraderState.WATCHING)
                         for s in mt.statuses().values())
        if has_active or session_count != prev_count:
            time.sleep(5)
            st.rerun()

    _live_view()
