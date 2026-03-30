import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

from scanner import scan, ScanFilters, UNIVERSE, UNIVERSE_US, UNIVERSE_INTL, UNIVERSE_INTL_FULL, UNIVERSE_CH
from autotrader import TraderConfig
from core import env_get, env_save


def render(data_client, get_price_fn, buy_fn, sell_fn, mt, use_hist, as_of_date, broker):
    st.subheader("🔍 Position Scanner — Start Here")
    st.caption(
        "Scans liquid stocks, ETFs, and ADRs using technical filters and ranks them by performance. "
        "Choose **🇺🇸 US**, **🌍 International**, or **🌐 All** markets below. "
        "**Run a scan → use ⚡ Quick Invest to open positions in one click, "
        "or send to 📈 Portfolio Mode for fully automated hands-off investing.**"
    )
    if broker == "IBKR":
        st.info(
            "**IBKR broker:** ETFs in the scan results may not support ATR-based stops — "
            "IBKR may not provide intraday high/low bars for ETFs. "
            "If ATR stop mode is selected for an ETF, AutoTrader will fall back to PCT mode.",
            icon="ℹ️",
        )

    top_n = st.number_input("How many top candidates to return", min_value=1, max_value=50,
                            value=int(env_get("SCAN_TOP_N", "10")))

    # ── Market selector ────────────────────────────────────────────────────
    market_choice = st.radio(
        "Market",
        ["🇺🇸 US", "🇨🇭 Swiss", "🌍 INTL (small)", "🌍 INTL (full)", "🌐 All"],
        horizontal=True,
        index=0,
        key="scan_market",
        help="🇺🇸 US: ~500 US equities and ETFs  |  🇨🇭 Swiss: Swiss ADRs & US-listed equities (~94)  |  🌍 INTL (small): flagship ADRs + broad country ETFs  |  🌍 INTL (full): comprehensive international ADRs  |  🌐 All: full combined universe",
    )
    if market_choice == "🇺🇸 US":
        _base_universe = UNIVERSE_US
    elif market_choice == "🇨🇭 Swiss":
        _base_universe = UNIVERSE_CH
    elif market_choice == "🌍 INTL (small)":
        _base_universe = UNIVERSE_INTL
    elif market_choice == "🌍 INTL (full)":
        _base_universe = UNIVERSE_INTL_FULL
    else:
        _base_universe = UNIVERSE

    # ── Symbol selection ──────────────────────────────────────────────────
    _watchlist_raw = env_get("SCAN_WATCHLIST", "")
    _watchlist = [s.strip().upper() for s in _watchlist_raw.replace(",", " ").split() if s.strip()]
    _watchlist_valid = [s for s in _watchlist if s in _base_universe]
    _watchlist_excluded = [s for s in _watchlist if s and s not in _base_universe]
    if _watchlist_excluded:
        st.warning(
            f"Watchlist symbols not in the **{market_choice}** universe (hidden): "
            f"{', '.join(_watchlist_excluded)}. Switch to 🌐 All or adjust your watchlist."
        )

    # Reset "scan full universe" checkbox when market changes so stale session
    # state doesn't leave the multiselect disabled unexpectedly.
    _prev_market = st.session_state.get("_scan_market_prev")
    if _prev_market != market_choice:
        st.session_state["scan_sel_all"] = len(_watchlist_valid) == 0
        st.session_state["_scan_market_prev"] = market_choice

    _default_all = len(_watchlist_valid) == 0
    _market_label = {"🇺🇸 US": "US", "🇨🇭 Swiss": "Swiss", "🌍 INTL (small)": "INTL (small)", "🌍 INTL (full)": "INTL (full)", "🌐 All": "All"}[market_choice]
    with st.expander(
        f"Symbol list — {f'{_market_label} universe' if _default_all else f'{len(_watchlist_valid)} from watchlist'} ({len(_base_universe)} available)",
        expanded=False,
    ):
        sel_all = st.checkbox(f"Scan full {_market_label} universe", value=_default_all, key="scan_sel_all")
        selected_syms = st.multiselect(
            "Symbols to scan",
            options=sorted(_base_universe),
            default=_watchlist_valid,
            disabled=sel_all,
            placeholder="Type to search…",
            label_visibility="collapsed",
        )
    scan_symbols = list(_base_universe) if sel_all else (selected_syms or None)

    # ── Live filter controls ───────────────────────────────────────────────
    with st.expander("Filters", expanded=True):
        fc1, fc2, fc3, fc4 = st.columns(4)
        f_min_price  = fc1.number_input("Min price ($)",       min_value=0.0, step=1.0,
                                         value=float(env_get("SCAN_MIN_PRICE",  "5.0")))
        f_min_adv    = fc2.number_input("Min ADV ($M)",        min_value=0.0, step=1.0,
                                         value=float(env_get("SCAN_MIN_ADV_M",  "5.0")))
        f_vol_mult   = fc3.number_input("Volume ≥ N× avg",     min_value=0.0, step=0.1,
                                         value=float(env_get("SCAN_VOL_MULT",   "1.0")))
        f_sma20_tol  = fc4.number_input("SMA20 tolerance (%)", min_value=0.0, max_value=20.0, step=0.5,
                                         value=float(env_get("SCAN_SMA20_TOL",  "3.0")),
                                         help="Allow price up to this % below SMA20")
        fc5, fc6, fc7, _ = st.columns(4)
        f_rsi_lo     = fc5.number_input("RSI min",             min_value=1, max_value=98,
                                         value=int(float(env_get("SCAN_RSI_LO", "35"))))
        f_rsi_hi     = fc6.number_input("RSI max",             min_value=2, max_value=99,
                                         value=int(float(env_get("SCAN_RSI_HI", "72"))))
        f_min_ret5d  = fc7.number_input("Min 5d return (%)",   min_value=-20.0, max_value=20.0, step=0.5,
                                         value=float(env_get("SCAN_MIN_RET5D",  "-1.0")))

        save_filters = st.button("Save as defaults", help="Persist these values to ⚙️ Settings")
        if save_filters:
            env_save({
                "SCAN_MIN_PRICE": str(f_min_price),
                "SCAN_MIN_ADV_M": str(f_min_adv),
                "SCAN_VOL_MULT":  str(f_vol_mult),
                "SCAN_SMA20_TOL": str(f_sma20_tol),
                "SCAN_RSI_LO":    str(f_rsi_lo),
                "SCAN_RSI_HI":    str(f_rsi_hi),
                "SCAN_MIN_RET5D": str(f_min_ret5d),
            })
            st.success("Filter defaults saved.")

    # ── Build filters from controls ────────────────────────────────────────
    try:
        scan_filters = ScanFilters(
            min_price     = f_min_price,
            min_adv_m     = f_min_adv,
            rsi_lo        = float(f_rsi_lo),
            rsi_hi        = float(f_rsi_hi),
            vol_mult      = f_vol_mult,
            sma20_tol_pct = f_sma20_tol,
            min_ret_5d    = f_min_ret5d,
        )
    except ValueError as e:
        st.error(f"Invalid filter values: {e}")
        st.stop()

    run_scan = st.button("Run Scan", type="primary")
    auto_trigger = st.session_state.pop("scan_auto_trigger", False)

    if run_scan or auto_trigger:
        progress_bar = st.progress(0, text="Scanning…")

        def on_progress(done, total):
            progress_bar.progress(done / total, text=f"Scanning {done}/{total}…")

        as_of_dt = datetime.combine(as_of_date, datetime.max.time()) if use_hist else None
        with st.spinner("Running scan…"):
            (st.session_state.scan_results,
             st.session_state.scan_skipped,
             st.session_state.scan_no_data) = scan(
                data_client, top_n=int(top_n),
                progress_cb=on_progress, as_of=as_of_dt,
                filters=scan_filters, symbols=scan_symbols)
        st.session_state.scan_ts = datetime.now()
        progress_bar.empty()

        # Append to scan history
        history = st.session_state.get("scan_history", [])
        history.append({
            "Time":    st.session_state.scan_ts.strftime("%H:%M:%S"),
            "Market":  market_choice,
            "Max":     int(top_n),
            "Results": len(st.session_state.scan_results),
            "Skipped": st.session_state.scan_skipped,
            "RSI":     f"{f_rsi_lo}–{f_rsi_hi}",
            "MinPx":   f"${f_min_price:.0f}",
            "VolMult": f"{f_vol_mult:.1f}×",
        })
        st.session_state.scan_history = history[-10:]  # keep last 10

    results = st.session_state.get("scan_results", pd.DataFrame())

    scan_ran = st.session_state.get("scan_ts") is not None
    skipped  = st.session_state.get("scan_skipped", 0)
    no_data  = st.session_state.get("scan_no_data", 0)
    if results.empty and scan_ran:
        st.warning(
            "📉 **Not a good time to invest.** "
            "Stock exchanges are not doing well right now — "
            "no candidates passed the quality filters. "
            "Try again later or loosen the filter thresholds."
        )
    if scan_ran and (skipped or no_data):
        parts = []
        if skipped:
            parts.append(f"{skipped} skipped (< 52 bars)")
        if no_data:
            parts.append(f"{no_data} unavailable (no data)")
        st.caption("Symbols excluded: " + "  |  ".join(parts) + ".")

    if not results.empty:
        scan_ts = st.session_state.get("scan_ts")
        if scan_ts:
            age_s = (datetime.now() - scan_ts).total_seconds()
            age_str = f"{int(age_s / 60)}m ago" if age_s >= 60 else f"{int(age_s)}s ago"
            stale = age_s > 1800  # 30 min
            msg = f"Last scan: {scan_ts.strftime('%H:%M:%S')} ({age_str})"
            if stale:
                st.warning(f"Results may be stale — {msg} — rescanning…")
                if not st.session_state.get("scan_auto_trigger"):
                    st.session_state.scan_auto_trigger = True
                    st.rerun()
            else:
                st.caption(msg)
        # Warn about already-open positions in the results
        if mt is not None:
            open_syms = set(mt.active_symbols()) if hasattr(mt, "active_symbols") else set()
            already_open = [s for s in results.index if s in open_syms]
            if already_open:
                st.info(
                    f"Already open: **{', '.join(already_open)}** — "
                    "Quick Invest will skip these symbols.",
                    icon="ℹ️",
                )

        st.success(f"Found {len(results)} candidates. Select rows then send to AutoTrader.")

        # Sort controls — applied before rendering so Quick Invest order matches what's visible
        _sortable_cols = [c for c in results.columns if c != "Symbol"]
        _sort_col = st.session_state.get("scan_sort_col", results.columns[0] if not results.empty else None)
        if _sort_col not in results.columns:
            _sort_col = results.columns[0]
        _sort_asc = st.session_state.get("scan_sort_asc", False)
        sc1, sc2 = st.columns([3, 1])
        _sort_col = sc1.selectbox("Sort by", results.columns.tolist(), index=results.columns.tolist().index(_sort_col),
                                   key="scan_sort_col", label_visibility="collapsed")
        _sort_asc = sc2.checkbox("Ascending", value=_sort_asc, key="scan_sort_asc")
        results = results.sort_values(_sort_col, ascending=_sort_asc)

        selection = st.dataframe(
            results,
            width="stretch",
            on_select="rerun",
            selection_mode="multi-row",
            key="scanner_table",
        )

        # Multi-select → actions
        rows = selection.selection.get("rows", [])
        selected_symbols = [results.index[r] for r in rows if r < len(results)]
        n_selected = len(selected_symbols)

        # ── Quick Invest ──────────────────────────────────────────────
        with st.expander("⚡ Quick Invest", expanded=True):
            qi1, qi2, qi3 = st.columns(3)
            qi_dollar = qi1.number_input(
                "$ per position", min_value=100.0, step=100.0,
                value=max(100.0, float(env_get("PM_SLOT_DOLLAR", "3000"))),
                key="qi_dollar",
            )
            qi_stop = qi2.number_input(
                "Trailing stop %", min_value=0.1, max_value=20.0, step=0.1,
                value=float(env_get("AT_THRESHOLD", "0.5")),
                key="qi_stop",
            )
            max_n = len(results)
            qi_default_n = n_selected if n_selected else min(5, max_n)
            qi_n = qi3.number_input(
                "Positions to open", min_value=1, max_value=max_n,
                value=qi_default_n, key="qi_n",
                help="If rows are selected in the table, those symbols are used. Otherwise the top N by score.",
            )

            syms_to_invest = (
                selected_symbols[:int(qi_n)] if n_selected
                else list(results.index[:int(qi_n)])
            )
            total_invest = qi_dollar * len(syms_to_invest)
            st.caption(
                f"**{', '.join(syms_to_invest)}**  —  "
                f"${qi_dollar:,.0f} each  =  **${total_invest:,.0f} total**"
            )

            btn_col1, btn_col2 = st.columns(2)
            invest_now = btn_col1.button("⚡ Invest Now", type="primary", key="qi_invest")
            invest_all = btn_col2.button(
                f"⚡ Invest All ({len(results)} stocks)",
                key="qi_invest_all",
                help="Invest in every scan result using the settings above, ignoring the positions-to-open limit.",
            )

            def _run_invest(syms):
                st.session_state.pop("qi_summary", None)
                _open = set(mt.active_symbols()) if mt and hasattr(mt, "active_symbols") else set()
                summary_rows = []
                for sym in syms:
                    if sym in _open:
                        summary_rows.append({"Symbol": sym, "Qty": "—", "Price": "—",
                                             "Amount": "—", "Status": "⏭ already open — skipped"})
                        continue
                    try:
                        price = get_price_fn(sym)
                        qty   = max(1, int(qi_dollar / price))
                        cfg   = TraderConfig(
                            stop_value    = float(qi_stop),
                            poll_interval = float(env_get("AT_POLL", "5")),
                        )
                        mt.start(sym, qty, config=cfg)
                        summary_rows.append({
                            "Symbol": sym, "Qty": qty,
                            "Fill ~": f"${price:.2f}",
                            "Invested": f"${qty * price:,.0f}",
                            "Status": "✓ Opened",
                        })
                    except Exception as e:
                        summary_rows.append({
                            "Symbol": sym, "Qty": "—",
                            "Fill ~": "—", "Invested": "—",
                            "Status": f"✗ {e}",
                        })
                st.session_state.qi_summary = summary_rows

            if invest_now:
                _run_invest(syms_to_invest)
            if invest_all:
                _run_invest(list(results.index))

            if st.session_state.get("qi_summary"):
                summary = st.session_state.qi_summary
                st.dataframe(pd.DataFrame(summary), hide_index=True)
                opened = [r["Symbol"] for r in summary if r["Status"].startswith("✓")]
                errors = [r["Status"][2:] for r in summary if r["Status"].startswith("✗")]
                if errors:
                    failed = [r for r in summary if r["Status"].startswith("✗")]
                    st.error("Errors: " + "; ".join(f"{r['Symbol']}: {r['Status'][2:]}" for r in failed))
                if opened:
                    if st.button("▶ Go to AutoTrader →", type="primary", key="qi_goto"):
                        st.session_state.nav_page = "AutoTrader"
                        st.session_state.pop("qi_summary", None)
                        st.rerun()

        # ── Send to AutoTrader queue ──────────────────────────────────
        if n_selected:
            if st.button(f"▶ Configure & queue {n_selected} symbol(s) in AutoTrader"):
                st.session_state.at_prefill_list = selected_symbols
                st.session_state.nav_page        = "AutoTrader"
                st.rerun()

        chart_col = "RS vs SPY" if "RS vs SPY" in results.columns else "5d Ret%"
        fig_scan = go.Figure(go.Bar(
            x=results.index,
            y=results[chart_col],
            marker_color=["green" if v >= 0 else "red" for v in results[chart_col]],
            text=[f"{v:+.2f}%" for v in results[chart_col]],
            textposition="outside",
        ))
        fig_scan.update_layout(title=f"{chart_col} — Top Candidates",
                               yaxis_title=chart_col, height=350)
        st.plotly_chart(fig_scan, width="stretch")
    elif not scan_ran:
        st.info("Run a scan to see candidates.")

    # ── Scan history ──────────────────────────────────────────────────────
    history = st.session_state.get("scan_history", [])
    if len(history) > 1:
        with st.expander(f"Scan history ({len(history)} runs this session)", expanded=False):
            st.dataframe(pd.DataFrame(list(reversed(history))), hide_index=True)
