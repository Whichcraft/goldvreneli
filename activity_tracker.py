"""
activity_tracker — reusable Activity Log renderer for MultiTrader.

Usage:
    from activity_tracker import render_log, render_sidebar_log, render_symbol_log
"""
import streamlit as st
import pandas as pd
from autotrader import MultiTrader

_ACTION_COLOR = {
    "BUY":         "#2ecc71",   # green
    "SELL":        "#e74c3c",   # red
    "PEAK":        "#00b8d9",   # teal
    "BREAKEVEN":   "#f39c12",   # orange
    "TAKE_PROFIT": "#2ecc71",   # green
    "TIME_STOP":   "#f39c12",   # orange
    "INFO":        "#95a5a6",   # grey
    "ERROR":       "#e74c3c",   # red
    "CANCEL":      "#f39c12",   # orange
    "STOP":        "#f39c12",   # orange
}


def _log_html(entries) -> str:
    """Render a list of TradeLog entries as a monospace HTML table."""
    rows = []
    for e in entries:
        ts     = e.timestamp.strftime("%H:%M:%S")
        sym    = (e.symbol or "—")[:6]
        action = e.action
        price  = f"${e.price:.2f}" if e.price else "—"
        note   = e.note or ""
        color  = _ACTION_COLOR.get(action, "#cccccc")
        rows.append(
            f"<tr>"
            f'<td style="color:#888;padding:1px 10px 1px 0;white-space:nowrap">{ts}</td>'
            f'<td style="color:#ddd;font-weight:bold;padding:1px 10px 1px 0;white-space:nowrap">{sym}</td>'
            f'<td style="color:{color};font-weight:bold;padding:1px 10px 1px 0;white-space:nowrap">{action}</td>'
            f'<td style="color:#aaa;padding:1px 10px 1px 0;white-space:nowrap">{price}</td>'
            f'<td style="color:#888;padding:1px 0">{note}</td>'
            f"</tr>"
        )
    return (
        '<div style="font-family:\'Courier New\',monospace;font-size:0.82em;'
        'overflow-x:auto;line-height:1.55">'
        "<table style='border-collapse:collapse;width:100%'>"
        + "".join(rows)
        + "</table></div>"
    )


def _log_rows(entries) -> list[dict]:
    return [
        {
            "Time": e.timestamp.strftime("%H:%M:%S"),
            "Symbol": e.symbol or "—",
            "Action": e.action,
            "Price": f"${e.price:.2f}" if e.price else "—",
            "Note": e.note,
        }
        for e in entries
    ]


def render_log(mt: MultiTrader, max_rows: int | None = None) -> None:
    """Render the full Activity Log for a MultiTrader instance."""
    all_logs = mt.all_logs()
    if not all_logs:
        return
    st.subheader("Activity Log")
    entries = list(reversed(all_logs))
    if max_rows:
        entries = entries[:max_rows]
    df = pd.DataFrame(_log_rows(entries))
    st.dataframe(df, width="stretch", hide_index=True)
    st.download_button(
        "⬇ Export CSV", df.to_csv(index=False),
        "activity_log.csv", "text/csv", key="at_log_export_csv",
    )


def render_symbol_log(log_entries, max_rows: int = 20) -> None:
    """Render the log for a single symbol."""
    if not log_entries:
        return
    entries = list(reversed(log_entries))[:max_rows]
    st.markdown(_log_html(entries), unsafe_allow_html=True)


def render_sidebar_log(mt: MultiTrader, max_rows: int = 8) -> None:
    """Render a compact Activity Log panel in the sidebar."""
    all_logs = mt.all_logs()
    if not all_logs:
        return
    entries = list(reversed(all_logs))[:max_rows]
    with st.expander("📋 Activity Log", expanded=False):
        st.markdown(_log_html(entries), unsafe_allow_html=True)
