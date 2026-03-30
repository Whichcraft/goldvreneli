import os
import streamlit as st
from core import INSTALL_DIR, env_get, env_save, clear_alpaca_cache


def render():
    st.title("Settings")

    # Show post-save messages (survive the rerun that follows saving)
    if "_settings_key_msgs" in st.session_state:
        st.success("Settings saved to .env")
        for kind, msg in st.session_state.pop("_settings_key_msgs"):
            (st.success if kind == "ok" else st.error)(msg)

    with st.form("settings_form"):

        # ── Alpaca Paper ──────────────────────────────────────────────────────
        st.subheader("Alpaca Paper Trading")
        c1, c2 = st.columns(2)
        f_alpaca_key    = c1.text_input("API Key",    value=env_get("ALPACA_PAPER_API_KEY"),    type="password")
        f_alpaca_secret = c2.text_input("Secret Key", value=env_get("ALPACA_PAPER_SECRET_KEY"), type="password")

        # ── Alpaca Live ───────────────────────────────────────────────────────
        st.subheader("Alpaca Live Trading")
        st.caption("Get live API keys at alpaca.markets → Live Trading → API Keys.")
        lc1, lc2 = st.columns(2)
        f_alpaca_live_key    = lc1.text_input("Live API Key",    value=env_get("ALPACA_LIVE_API_KEY"),    type="password")
        f_alpaca_live_secret = lc2.text_input("Live Secret Key", value=env_get("ALPACA_LIVE_SECRET_KEY"), type="password")

        st.divider()

        # ── IBKR ──────────────────────────────────────────────────────────────
        st.subheader("IBKR")
        c1, c2, c3 = st.columns(3)
        f_ibkr_user    = c1.text_input("Username",     value=env_get("IBKR_USERNAME"))
        f_ibkr_pass    = c2.text_input("Password",     value=env_get("IBKR_PASSWORD"),  type="password")
        f_ibkr_mode    = c3.selectbox("Trading Mode",  ["paper", "live"],
                                       index=0 if env_get("IBKR_MODE", "paper") == "paper" else 1)
        c4, c5 = st.columns(2)
        f_ibc_path     = c4.text_input("IBC Path",     value=env_get("IBC_PATH",     os.path.join(INSTALL_DIR, "ibc")))
        f_gateway_path = c5.text_input("Gateway Path", value=env_get("GATEWAY_PATH", os.path.join(INSTALL_DIR, "Jts", "ibgateway")))

        st.divider()

        # ── AutoTrader defaults ───────────────────────────────────────────────
        st.subheader("AutoTrader Defaults")
        c1, c2, c3, c4 = st.columns(4)
        f_at_symbol    = c1.text_input("Default Symbol",         value=env_get("AT_SYMBOL",    ""))
        f_at_threshold = c2.number_input("Trailing Stop %",      min_value=0.1, max_value=10.0,
                                          value=float(env_get("AT_THRESHOLD", "0.5")), step=0.1)
        f_at_poll      = c3.number_input("Poll Interval (s)",    min_value=1,
                                          value=int(env_get("AT_POLL", "5")),           step=1)
        f_at_loss_lim  = c4.number_input("Daily Loss Limit ($)", min_value=0.0,
                                          value=float(env_get("AT_DAILY_LOSS_LIMIT", "0")), step=100.0,
                                          help="Stop new trades when realized losses reach this amount. 0 = disabled.")

        st.divider()

        # ── Scanner defaults ──────────────────────────────────────────────────
        st.subheader("Scanner Filters")
        c1, c2, c3, c4 = st.columns(4)
        f_scan_n          = c1.number_input("Max scan results",     min_value=1,   max_value=50,
                                             value=int(env_get("SCAN_TOP_N",        "10")))
        f_scan_rsi_lo     = c2.number_input("RSI min",             min_value=1,   max_value=99,
                                             value=int(env_get("SCAN_RSI_LO",       "35")))
        f_scan_rsi_hi     = c3.number_input("RSI max",             min_value=1,   max_value=99,
                                             value=int(env_get("SCAN_RSI_HI",       "72")))
        f_scan_vol_mult   = c4.number_input("Volume multiplier",   min_value=0.0, max_value=10.0,
                                             value=float(env_get("SCAN_VOL_MULT",   "1.0")), step=0.1)
        c1, c2, c3, c4 = st.columns(4)
        f_scan_min_price  = c1.number_input("Min price ($)",       min_value=0.0,
                                             value=float(env_get("SCAN_MIN_PRICE",  "5.0")), step=1.0)
        f_scan_min_adv    = c2.number_input("Min ADV ($M)",        min_value=0.0,
                                             value=float(env_get("SCAN_MIN_ADV_M",  "5.0")), step=1.0)
        f_scan_sma20_tol  = c3.number_input("SMA20 tolerance (%)", min_value=0.0, max_value=20.0,
                                             value=float(env_get("SCAN_SMA20_TOL",  "3.0")), step=0.5,
                                             help="Allow price this % below SMA20")
        f_scan_min_ret5d  = c4.number_input("Min 5d return (%)",   min_value=-20.0, max_value=20.0,
                                             value=float(env_get("SCAN_MIN_RET5D",  "-1.0")), step=0.5)
        f_scan_watchlist  = st.text_area(
            "Default watchlist (comma-separated — used as pre-selection in Scanner)",
            value=env_get("SCAN_WATCHLIST", ""),
            height=80,
            placeholder="AAPL, MSFT, NVDA, …  (leave blank to start with full universe)",
        )

        st.divider()

        # ── Portfolio Mode defaults ────────────────────────────────────────────
        st.subheader("Portfolio Mode Defaults")
        pmc1, pmc2 = st.columns(2)
        f_pm_slots     = pmc1.number_input("Target slots", min_value=1, max_value=20,
                                            value=int(env_get("PM_TARGET_SLOTS", "10")))
        f_pm_slot_pct  = pmc2.number_input("% of equity per slot", min_value=1.0,
                                            max_value=50.0, step=1.0,
                                            value=float(env_get("PM_SLOT_PCT", "10.0")))
        f_pm_slot_dollar = st.number_input("Fixed $ per slot (0 = use % above)", min_value=0.0,
                                            step=100.0, value=float(env_get("PM_SLOT_DOLLAR", "0")))

        st.divider()
        saved = st.form_submit_button("Save Settings", type="primary")

    if saved:
        env_save({
            "ALPACA_PAPER_API_KEY":    f_alpaca_key,
            "ALPACA_PAPER_SECRET_KEY": f_alpaca_secret,
            "ALPACA_LIVE_API_KEY":     f_alpaca_live_key,
            "ALPACA_LIVE_SECRET_KEY":  f_alpaca_live_secret,
            "IBKR_USERNAME":           f_ibkr_user,
            "IBKR_PASSWORD":           f_ibkr_pass,
            "IBKR_MODE":               f_ibkr_mode,
            "IBC_PATH":                f_ibc_path,
            "GATEWAY_PATH":            f_gateway_path,
            "AT_SYMBOL":               f_at_symbol,
            "AT_THRESHOLD":            str(f_at_threshold),
            "AT_POLL":                 str(f_at_poll),
            "AT_DAILY_LOSS_LIMIT":     str(f_at_loss_lim),
            "SCAN_TOP_N":              str(f_scan_n),
            "SCAN_RSI_LO":             str(f_scan_rsi_lo),
            "SCAN_RSI_HI":             str(f_scan_rsi_hi),
            "SCAN_VOL_MULT":           str(f_scan_vol_mult),
            "SCAN_MIN_PRICE":          str(f_scan_min_price),
            "SCAN_MIN_ADV_M":          str(f_scan_min_adv),
            "SCAN_SMA20_TOL":          str(f_scan_sma20_tol),
            "SCAN_MIN_RET5D":          str(f_scan_min_ret5d),
            "SCAN_WATCHLIST":          f_scan_watchlist,
            "PM_TARGET_SLOTS":         str(f_pm_slots),
            "PM_SLOT_PCT":             str(f_pm_slot_pct),
            "PM_SLOT_DOLLAR":          str(f_pm_slot_dollar),
        })
        # Clear cached clients so they reconnect with new keys
        clear_alpaca_cache()
        # Reset IBKR auto-start flags so gateway restarts with new credentials
        st.session_state.pop("gw_start_attempted", None)
        st.session_state.pop("ib_connect_attempted", None)
        if "gateway" in st.session_state:
            del st.session_state["gateway"]
        # ── Validate Alpaca credentials (results survive rerun via session_state) ──
        key_msgs = []
        def _check_alpaca(key: str, secret: str, paper: bool, label: str):
            if not key or not secret:
                return
            try:
                from alpaca.trading.client import TradingClient
                acct = TradingClient(api_key=key, secret_key=secret, paper=paper).get_account()
                key_msgs.append(("ok", f"✅ {label} keys OK — account {str(acct.id)[:8]}… ({acct.status})"))
            except Exception as _e:
                key_msgs.append(("err", f"❌ {label} keys invalid: {_e}"))

        _check_alpaca(f_alpaca_key,      f_alpaca_secret,      paper=True,  label="Paper")
        _check_alpaca(f_alpaca_live_key, f_alpaca_live_secret, paper=False, label="Live")
        st.session_state["_settings_key_msgs"] = key_msgs

        st.rerun()

    # ── Test Connection (outside form — uses currently saved .env values) ──────
    st.divider()
    st.subheader("Test Connection")
    st.caption("Tests the API keys currently saved in .env (save first if you just changed them).")
    tc1, tc2 = st.columns(2)
    if tc1.button("Test Alpaca Paper", use_container_width=True):
        key    = env_get("ALPACA_PAPER_API_KEY")
        secret = env_get("ALPACA_PAPER_SECRET_KEY")
        if not key or not secret:
            st.error("No Alpaca Paper keys saved yet.")
        else:
            try:
                from alpaca.trading.client import TradingClient
                acct = TradingClient(api_key=key, secret_key=secret, paper=True).get_account()
                st.success(f"✅ Paper keys OK — account {str(acct.id)[:8]}… ({acct.status})")
            except Exception as _e:
                st.error(f"❌ Paper keys invalid: {_e}")
    if tc2.button("Test Alpaca Live", use_container_width=True):
        key    = env_get("ALPACA_LIVE_API_KEY")
        secret = env_get("ALPACA_LIVE_SECRET_KEY")
        if not key or not secret:
            st.error("No Alpaca Live keys saved yet.")
        else:
            try:
                from alpaca.trading.client import TradingClient
                acct = TradingClient(api_key=key, secret_key=secret, paper=False).get_account()
                st.success(f"✅ Live keys OK — account {str(acct.id)[:8]}… ({acct.status})")
            except Exception as _e:
                st.error(f"❌ Live keys invalid: {_e}")

    st.divider()
    st.subheader("Test IBKR Gateway")
    st.caption("Checks the gateway connection that is currently active in this session.")
    if st.button("Test IBKR Gateway", use_container_width=True):
        _ib = st.session_state.get("ib")
        if _ib is None:
            st.error("No IBKR session active — switch broker to IBKR and start the gateway first.")
        elif not _ib.isConnected():
            st.error("❌ Gateway not connected.")
        else:
            try:
                _summary = _ib.accountSummary()
                _tags    = {v.tag: v.value for v in _summary if v.currency in ("USD", "")}
                _nlv     = float(_tags.get("NetLiquidation", 0))
                st.success(f"✅ IBKR connected — Net Liquidation: ${_nlv:,.2f}")
            except Exception as _e:
                st.error(f"❌ IBKR query failed: {_e}")
