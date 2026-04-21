import streamlit as st
import pandas as pd

from autotrader import TraderState, TraderConfig, StopMode, EntryMode, size_from_risk
from core import env_get


def render(mt, ctx, trading_client, ib):
    st.subheader("AutoTrader — Multi-Position Manager")
    st.caption("Enters positions and exits automatically via trailing stop, take-profit, breakeven, or time stop.")

    # ── Multi-symbol prefill from Scanner ──────────────────────────────────
    _prefill_list   = st.session_state.pop("at_prefill_list", None)
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

    # ── Qty mode (outside form so radio changes update inputs immediately) ──
    qty_mode = st.radio("Qty mode", ["Shares", "Dollar amount", "Risk %"],
                        horizontal=True, label_visibility="collapsed", key="at_qty_mode")

    _account_equity = 10000.0
    if ctx.name == "Alpaca" and trading_client is not None:
        try:
            _account_equity = float(trading_client.get_account().equity)
        except Exception:
            pass
    elif ctx.name == "IBKR" and ib is not None and ib.isConnected():
        try:
            _account_equity = ctx.get_equity()
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
                                         value=_account_equity, step=500.0, key="at_equity")
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

    # ── Position configuration form ─────────────────────────────────────────
    with st.form("at_config"):
        st.markdown("**New Position**")
        c1, c2, c3 = st.columns(3)
        at_symbol    = c1.text_input("Symbol", value=_default_symbol).upper()
        at_stop_mode = c2.selectbox("Stop Mode", ["PCT", "ATR"],
                                    help="PCT = fixed %; ATR = N × ATR(14) dollars")
        at_stop_val  = c3.number_input(
            "Trailing Stop %",
            min_value=0.1, max_value=20.0,
            value=float(env_get("AT_THRESHOLD", "0.5")), step=0.1,
            help="For PCT: % drop from peak triggers sell. For ATR: multiplier × ATR(14).",
        )

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
            xc1, xc2     = st.columns(2)
            at_tp_pct    = xc1.number_input(
                "Take-profit trigger (%)", min_value=0.0,
                value=float(env_get("AT_TP_TRIGGER", "1.5")), step=0.1,
                help="Sell at_tp_fraction of position when up this %. 0 = disabled.",
            )
            at_tp_frac   = xc2.slider("Fraction to sell at take-profit", min_value=0.1,
                                       max_value=1.0, value=0.5, step=0.1)
            xc3, xc4     = st.columns(2)
            at_be_pct    = xc3.number_input("Breakeven trigger (%)", min_value=0.0, value=0.0, step=0.1,
                                             help="0 = disabled. Once up this %, move stop floor to entry price.")
            at_time_stop = xc4.number_input("Time stop (minutes)", min_value=0, value=0, step=5,
                                             help="0 = disabled. Exit after this many minutes.")
            xc5, _       = st.columns(2)
            at_max_loss_pct = xc5.number_input(
                "Max loss from entry (%)", min_value=0.0, value=0.0, step=0.5,
                help="0 = disabled. Hard exit if price drops this % below entry.",
            )

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
                poll_interval         = float(env_get("AT_POLL", "5")),
                entry_mode            = EntryMode(at_entry_mode.lower()),
                limit_price           = at_limit_price,
                limit_timeout_s       = float(at_limit_timeout),
                scale_tranches        = at_scale_n,
                scale_interval_s      = float(at_scale_ivl),
                tp_trigger_pct        = at_tp_pct,
                tp_qty_fraction       = at_tp_frac,
                breakeven_trigger_pct = at_be_pct,
                time_stop_minutes     = float(at_time_stop),
                max_loss_pct          = at_max_loss_pct,
            )
            try:
                mt.start(at_symbol, int(at_qty), config=cfg)
                queue = st.session_state.pop("at_queue", [])
                if queue:
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

    # ── Quick P&L summary ───────────────────────────────────────────────────
    statuses = mt.statuses()
    if statuses:
        active_count = sum(
            1 for s in statuses.values()
            if s.state in (TraderState.ENTERING, TraderState.WATCHING)
        )
        st.divider()
        dl1, dl2, dl3 = st.columns(3)
        dl1.metric("Active positions",        str(active_count))
        dl2.metric("Unrealized P&L (active)", f"${mt.unrealized_pnl():+,.2f}")
        dl3.metric("Realized P&L today",      f"${mt.realized_losses():+,.2f}")
        if active_count:
            st.info("Go to **📊 Positions** to see live cards and activity logs.")
