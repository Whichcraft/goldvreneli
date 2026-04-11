"""
activity_tracker — reusable Activity Log renderer for MultiTrader.

Usage:
    from activity_tracker import render_log, render_sidebar_log
    render_log(mt)                # full table (AutoTrader page)
    render_sidebar_log(mt)        # compact last-N panel (sidebar)
"""
import streamlit as st
import pandas as pd
from autotrader import MultiTrader


def render_log(mt: MultiTrader, max_rows: int | None = None) -> None:
    """Render the full Activity Log table for a MultiTrader instance."""
    all_logs = mt.all_logs()
    if not all_logs:
        return
    st.subheader("Activity Log")
    entries = list(reversed(all_logs))
    if max_rows:
        entries = entries[:max_rows]
    log_data = [
        {
            "Time":   e.timestamp.strftime("%H:%M:%S"),
            "Symbol": e.symbol or "—",
            "Action": e.action,
            "Price":  f"${e.price:.2f}" if e.price else "—",
            "Note":   e.note,
        }
        for e in entries
    ]
    df = pd.DataFrame(log_data)
    st.dataframe(df, width="stretch", hide_index=True)
    st.download_button(
        "⬇ Export CSV", df.to_csv(index=False),
        "activity_log.csv", "text/csv", key="at_log_export_csv",
    )


def render_sidebar_log(mt: MultiTrader, max_rows: int = 8) -> None:
    """Render a compact Activity Log panel in the sidebar."""
    all_logs = mt.all_logs()
    if not all_logs:
        return
    entries = list(reversed(all_logs))[:max_rows]
    with st.expander("📋 Activity Log", expanded=False):
        for e in entries:
            sym  = e.symbol or "—"
            time = e.timestamp.strftime("%H:%M:%S")
            price = f" ${e.price:.2f}" if e.price else ""
            st.caption(f"`{time}` **{sym}** {e.action}{price}")
            if e.note:
                st.caption(f"  _{e.note}_")
