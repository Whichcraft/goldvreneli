import time
import streamlit as st
import pandas as pd

from autotrader import TraderState, TraderConfig, StopMode
from core import env_get, get_portfolio_manager


def render(mt, ctx, trading_client, ib):
    st.subheader("Portfolio Mode")
    st.caption(
        "Automatically maintains up to N positions from scanner picks. "
        "Each slot is sized at a fixed % of equity. On exit, the next best candidate is opened."
    )

    pm_exists = "portfolio_manager" in st.session_state
    pm_running = pm_exists and st.session_state["portfolio_manager"].running

    if not pm_running:
        st.info(
            "📈 **Fully automated investing in 3 steps:**  \n"
            "1. Set **target slots** (e.g. 5) and **$ per slot** (e.g. $3,000)  \n"
            "2. Click **▶ Start All** — scans for the best stocks and opens all positions at once  \n"
            "3. Walk away — positions are managed automatically; each one that closes is replaced with the next best pick"
        )

    # ── Configuration ─────────────────────────────────────────────────
    with st.expander("Configuration", expanded=not pm_running):
        pmc1, pmc2 = st.columns(2)
        pm_slots = pmc1.number_input("Target slots", min_value=1, max_value=20,
                                      value=int(env_get("PM_TARGET_SLOTS", "10")),
                                      disabled=pm_running)
        pm_size_mode = pmc2.radio("Slot sizing", ["% of equity", "Fixed $ per slot"],
                                  horizontal=True, disabled=pm_running)

        if pm_size_mode == "Fixed $ per slot":
            pm_slot_dollar = st.number_input(
                "$ per slot", min_value=100.0, step=100.0,
                value=max(100.0, float(env_get("PM_SLOT_DOLLAR", "3000"))),
                disabled=pm_running,
                help="Fixed dollar amount invested in each position regardless of account size.",
            )
            pm_slot_pct = 0.0
            st.caption(f"Total exposure: ~${pm_slot_dollar * pm_slots:,.0f} across {pm_slots} slots")
        else:
            pm_slot_pct = st.number_input(
                "% of equity per slot", min_value=1.0, max_value=50.0, step=1.0,
                value=float(env_get("PM_SLOT_PCT", "10.0")),
                disabled=pm_running,
            )
            pm_slot_dollar = 0.0

        pms1, pms2 = st.columns(2)
        pm_stop_mode = pms1.selectbox("Stop mode", ["PCT", "ATR"],
                                      disabled=pm_running)
        pm_stop_val  = pms2.number_input(
            "Trailing stop value",
            min_value=0.1, max_value=20.0, step=0.1,
            value=float(env_get("AT_THRESHOLD", "0.5")),
            help="PCT: % drop from peak; ATR: N × ATR(14)",
            disabled=pm_running,
        )
        pm_poll      = st.number_input("Poll interval (s)", min_value=1, max_value=60,
                                        value=int(env_get("AT_POLL", "5")),
                                        disabled=pm_running)
        pm_loss_limit = st.number_input(
            "Daily loss limit ($, 0 = off)", min_value=0.0, step=100.0,
            value=float(env_get("AT_DAILY_LOSS_LIMIT", "0")),
            disabled=pm_running,
        )

    # ── Start / Stop ──────────────────────────────────────────────────
    def _launch_pm(mode: str):
        st.session_state.pop("portfolio_manager", None)
        cfg = TraderConfig(
            stop_mode     = StopMode.PCT if pm_stop_mode == "PCT" else StopMode.ATR,
            stop_value    = pm_stop_val,
            poll_interval = float(pm_poll),
        )
        pm = get_portfolio_manager(
            st.session_state,
            ctx.data_client,
            ctx.get_price,
            ctx.buy,
            ctx.sell,
            ctx.get_bars,
            ctx.get_equity,
            target_slots      = int(pm_slots),
            slot_pct          = float(pm_slot_pct),
            slot_dollar       = float(pm_slot_dollar),
            trader_config     = cfg,
            daily_loss_limit  = float(pm_loss_limit),
        )
        if mode == "all":
            pm.start_all()
        else:
            pm.start()
        st.rerun()

    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns([1.4, 1, 1, 1])
    if btn_col1.button("▶ Start Sequential", type="primary", disabled=pm_running,
                       help="Open positions one at a time; replace each on close."):
        _launch_pm("sequential")
    if btn_col2.button("▶ Start All", type="primary", disabled=pm_running,
                       help="Open all slots simultaneously."):
        _launch_pm("all")
    _pm_obj    = st.session_state.get("portfolio_manager")
    _pm_paused = pm_exists and _pm_obj is not None and _pm_obj.paused
    if btn_col3.button("⏸ Pause" if not _pm_paused else "▶ Resume",
                       disabled=not pm_running,
                       help="Pause: keep monitoring existing positions but open no new ones. Resume to fill empty slots again."):
        if _pm_paused:
            _pm_obj.resume()
        else:
            _pm_obj.pause()
        st.rerun()
    if btn_col4.button("⏹  Stop", disabled=not pm_running):
        st.session_state["portfolio_manager"].stop()
        st.rerun()

    # ── Status ────────────────────────────────────────────────────────
    if pm_exists:
        pm = st.session_state["portfolio_manager"]
        st.divider()

        # Summary metrics
        sm1, sm2, sm3, sm4 = st.columns(4)
        sm1.metric("Active slots",    f"{pm.active_count()} / {pm._target_slots}")
        sm2.metric("Open slots",      str(pm.open_slot_count()))
        sm3.metric("Session P&L",     f"${pm.session_pnl():+,.2f}")
        sm4.metric("Realized losses", f"${pm.realized_losses():,.2f}")

        if pm.paused:
            st.info("⏸ **Paused** — existing positions are monitored; no new slots will open until resumed.")

        scan_age = pm.scan_age_s()
        if scan_age is not None:
            age_str = f"{int(scan_age // 60)}m {int(scan_age % 60)}s ago"
            sc1, sc2 = st.columns([4, 1])
            if scan_age > 1800:
                sc1.warning(f"Candidate list may be stale — last scan {age_str}")
            else:
                sc1.caption(f"Last scan: {age_str}")
            if sc2.button("🔄 Rescan", key="pm_rescan",
                          help="Force a fresh scan now instead of waiting for the 30-minute auto-refresh"):
                import threading
                threading.Thread(target=pm._rescan, daemon=True).start()
                st.rerun()

        # Active positions table
        statuses = pm.statuses()
        active_rows = []
        for sym, s in statuses.items():
            if s.state in (TraderState.ENTERING, TraderState.WATCHING):
                active_rows.append({
                    "Symbol":   sym,
                    "State":    s.state.value.upper(),
                    "Qty":      s.qty_remaining,
                    "Entry":    f"${s.entry_price:.2f}",
                    "Current":  f"${s.current_price:.2f}",
                    "Peak":     f"${s.peak_price:.2f}",
                    "Stop":     f"${s.stop_floor:.2f}",
                    "P&L":      f"${s.pnl:+,.2f}",
                    "Draw%":    f"{s.drawdown_pct:.2f}%",
                })
        closed_rows = [
            {
                "Symbol":  sym,
                "State":   s.state.value.upper(),
                "P&L":     f"${s.pnl:+,.2f}",
            }
            for sym, s in statuses.items()
            if s.state not in (TraderState.ENTERING, TraderState.WATCHING)
        ]

        if active_rows:
            st.subheader(f"Active positions ({len(active_rows)})")
            st.dataframe(pd.DataFrame(active_rows), width="stretch", hide_index=True)
        else:
            st.info("No active positions yet.")

        if closed_rows:
            with st.expander(f"Closed this session ({len(closed_rows)})"):
                st.dataframe(pd.DataFrame(closed_rows), width="stretch", hide_index=True)

        # Activity log
        log = pm.log_entries()
        if log:
            st.subheader("Activity Log")
            st.dataframe(
                pd.DataFrame(reversed(log)),
                width="stretch", hide_index=True,
            )

    # ── Monitor existing account positions ────────────────────────────
    st.divider()
    with st.expander("📥 Monitor existing account positions", expanded=False):
        st.caption(
            "Attach a trailing-stop monitor to positions already open in your account "
            "(e.g. after an app restart). No new orders are placed — AutoTrader watches "
            "from the current price and sells when the trailing stop is hit."
        )
        if ctx.name == "Alpaca":
            try:
                acct_positions = trading_client.get_all_positions()
            except Exception as _e:
                acct_positions = []
                st.error(f"Could not fetch positions: {_e}")
        else:
            try:
                _ib2 = ib
                _ibkr_pos = _ib2.positions() if (_ib2 and _ib2.isConnected()) else []
                class _IbkrPos:
                    def __init__(self, sym, qty, cost):
                        self.symbol = sym; self.qty = str(qty)
                        self.avg_entry_price = str(cost)
                        self.current_price = str(cost)
                        self.unrealized_pl = "0"
                acct_positions = [_IbkrPos(p.contract.symbol,
                    abs(int(p.position)), p.avgCost)
                    for p in _ibkr_pos if p.position > 0]
            except Exception as _e:
                acct_positions = []
                st.error(f"Could not fetch positions: {_e}")

        monitored_syms = set(mt.statuses().keys())
        unmonitored = [p for p in acct_positions if p.symbol not in monitored_syms]

        if not unmonitored:
            st.info("All open account positions are already being monitored.")
        else:
            attach_rows = [{
                "Symbol":      p.symbol,
                "Qty":         int(float(p.qty)),
                "Avg Entry":   f"${float(p.avg_entry_price):.2f}",
                "Current":     f"${float(p.current_price):.2f}",
                "P&L ($)":     f"${float(p.unrealized_pl):+,.2f}",
            } for p in unmonitored]
            st.dataframe(pd.DataFrame(attach_rows), width="stretch", hide_index=True)

            at1, at2, _ = st.columns([1, 1, 2])
            attach_stop = at1.number_input(
                "Trailing stop %", min_value=0.1, max_value=20.0, step=0.1,
                value=float(env_get("AT_THRESHOLD", "0.5")),
                key="attach_stop",
            )
            attach_poll = at2.number_input(
                "Poll interval (s)", min_value=1, max_value=60,
                value=int(env_get("AT_POLL", "5")),
                key="attach_poll",
            )
            if st.button("📥 Start monitoring all", key="attach_all"):
                attach_cfg = TraderConfig(
                    stop_value    = float(attach_stop),
                    poll_interval = float(attach_poll),
                )
                attach_errors, attach_ok = [], []
                for p in unmonitored:
                    try:
                        mt.attach(
                            p.symbol,
                            int(float(p.qty)),
                            float(p.avg_entry_price),
                            config=attach_cfg,
                        )
                        attach_ok.append(p.symbol)
                    except Exception as _e:
                        attach_errors.append(f"{p.symbol}: {_e}")
                if attach_ok:
                    st.success(f"Monitoring started for: {', '.join(attach_ok)}")
                if attach_errors:
                    st.error("Errors: " + "; ".join(attach_errors))
                st.rerun()

    # Auto-refresh while running
    if pm_running:
        time.sleep(5)
        st.rerun()
