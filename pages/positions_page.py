"""positions_page — live position cards with per-symbol activity log."""
import time
from datetime import datetime

import pandas as pd
import streamlit as st

from autotrader import TraderState
from activity_tracker import render_symbol_log


def render(mt):
    st.subheader("Positions")
    st.caption("Live view of all AutoTrader positions. Refreshes every 5 s while active.")

    @st.fragment
    def _live_view():
        statuses = mt.statuses()

        if not statuses:
            st.info(
                "💡 No active positions. "
                "Go to **🔍 Scanner → ⚡ Quick Invest** or open a position on the **🤖 AutoTrader** page."
            )
            return

        # ── Summary table ──────────────────────────────────────────────────
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

        # ── WATCHING position cards ────────────────────────────────────────
        active = [(sym, s) for sym, s in statuses.items()
                  if s.state == TraderState.WATCHING]
        if active:
            st.divider()
            for sym, s in active:
                with st.container(border=True):
                    mc1, mc2, mc3, mc4, mc5 = st.columns([2, 2, 2, 2, 1])
                    mc1.metric("Symbol",  sym)
                    mc2.metric("Current", f"${s.current_price:.2f}",
                               delta=f"Entry ${s.entry_price:.2f}")
                    mc3.metric("Peak",    f"${s.peak_price:.2f}")
                    mc4.metric("Stop",    f"${s.stop_floor:.2f}")
                    if mc5.button("Stop", key=f"pos_stop_{sym}"):
                        mt.stop(sym)
                        st.rerun()

                    pnl_color = "green" if s.pnl >= 0 else "red"
                    st.markdown(f"**P&L:** :{pnl_color}[${s.pnl:+,.2f}]")
                    pct = min(s.drawdown_pct / s.threshold_pct, 1.0) if s.threshold_pct else 0.0
                    st.progress(pct, text=f"Drawdown {s.drawdown_pct:.2f}% / {s.threshold_pct:.2f}%")

                    if s.config.stop_mode.value == "pct":
                        new_stop = st.number_input(
                            "Trailing stop %", min_value=0.1, max_value=50.0, step=0.1,
                            value=float(s.config.stop_value),
                            key=f"pos_thresh_{sym}",
                            label_visibility="collapsed",
                        )
                        if abs(new_stop - s.config.stop_value) > 0.001:
                            mt.set_threshold(sym, new_stop)

                    if s.last_poll_at is not None:
                        lag = (datetime.now() - s.last_poll_at).total_seconds()
                        if lag > 3 * s.config.poll_interval:
                            st.warning(f"⚠️ Price feed may be stalled — last poll {lag:.0f}s ago")
                    if s.breakeven_active:
                        st.caption("Breakeven active — stop floor at entry")
                    if s.tp_executed:
                        st.caption("Take-profit executed — trailing remaining shares")

                    # Last 20 log entries for this position
                    if s.log:
                        with st.expander("Last 20 actions", expanded=False):
                            render_symbol_log(s.log, max_rows=20)

        # ── ERROR cards ───────────────────────────────────────────────────
        errored = [(sym, s) for sym, s in statuses.items()
                   if s.state == TraderState.ERROR]
        if errored:
            st.divider()
            st.markdown("**Errored positions**")
            for sym, s in errored:
                with st.container(border=True):
                    ec1, ec2 = st.columns([4, 1])
                    ec1.markdown(f":red[**{sym}**] — ERROR")
                    if s.entry_price:
                        ec1.caption(f"Entry ${s.entry_price:.2f}  ·  Qty {s.qty}")
                    confirmed = st.checkbox(f"Confirm restart {sym}", key=f"pos_err_confirm_{sym}")
                    if ec2.button("Restart", key=f"pos_restart_{sym}", disabled=not confirmed):
                        import dataclasses
                        mt.stop(sym)
                        mt.start(sym, s.qty, dataclasses.replace(s.config))
                        st.rerun()

        # ── Daily summary ─────────────────────────────────────────────────
        st.divider()
        dl1, dl2 = st.columns(2)
        dl1.metric("Unrealized P&L (active)", f"${mt.unrealized_pnl():+,.2f}")
        dl2.metric("Realized P&L today",      f"${mt.realized_losses():+,.2f}")

        # ── Full activity log ─────────────────────────────────────────────
        from activity_tracker import render_log
        render_log(mt)

        # Auto-refresh while any position is active
        has_active = any(
            s.state in (TraderState.ENTERING, TraderState.WATCHING)
            for s in statuses.values()
        )
        if has_active:
            time.sleep(5)
            st.rerun()

    _live_view()
