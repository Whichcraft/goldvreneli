"""
Test Mode — runs AutoTrader logic against live OR historical prices without placing real orders.
Buy/sell are simulated: fills are recorded at the polled price but no broker order is submitted.

Live mode   — uses real-time bid/ask; runs indefinitely.
Replay mode — replays Alpaca historical 1-min bars at a configurable speed multiplier;
              each symbol gets its own ReplayPriceFeed created on first use.
"""
import threading
from datetime import datetime, timedelta, time as dtime

import streamlit as st

from autotrader import MultiTrader
from replay import ReplayPriceFeed
import pages.autotrader_page as autotrader_page

_TEST_MT_KEY      = "test_mode_multitrader"
_TEST_FEED_KEY    = "test_mode_replay_dispatcher"
_TEST_CFG_KEY     = "test_mode_replay_cfg"    # tracks last-used replay config for change detection


# ── Replay dispatcher ─────────────────────────────────────────────────────────

class _ReplayDispatcher:
    """
    Per-symbol ReplayPriceFeed factory used as the `get_price` callable for
    MultiTrader in replay mode.  Each symbol's feed is created lazily on first
    call and advances independently.
    """

    def __init__(self, data_client, replay_date: str, speed: float,
                 start_time=None, end_time=None, duration_hours=None):
        self._data_client     = data_client
        self.replay_date      = replay_date
        self.speed            = speed
        self._start_time      = start_time
        self._end_time        = end_time
        self._duration_hours  = duration_hours
        self._feeds: dict     = {}
        self._errors: dict    = {}
        self._lock            = threading.Lock()

    @property
    def recommended_poll_interval(self) -> float:
        return max(0.05, 60.0 / self.speed)

    def get_price(self, symbol: str) -> float:
        with self._lock:
            if symbol in self._errors:
                return 0.0
            if symbol not in self._feeds:
                try:
                    self._feeds[symbol] = ReplayPriceFeed(
                        self._data_client,
                        symbol,
                        self.replay_date,
                        speed          = self.speed,
                        start_time     = self._start_time,
                        end_time       = self._end_time,
                        duration_hours = self._duration_hours,
                    )
                except Exception as exc:
                    self._errors[symbol] = str(exc)
                    return 0.0
            return self._feeds[symbol].get_price(symbol)

    def progress_for(self, symbol: str) -> tuple[float, int, int]:
        """Returns (fraction, current_bar, total_bars) for a symbol, or (0,0,0)."""
        f = self._feeds.get(symbol)
        if f is None:
            return 0.0, 0, 0
        return f.progress, f.current_bar, f.bar_count

    def exhausted_for(self, symbol: str) -> bool:
        f = self._feeds.get(symbol)
        return f.exhausted if f else False

    def current_time_for(self, symbol: str) -> str:
        f = self._feeds.get(symbol)
        return f.current_time if f else ""


# ── Page ──────────────────────────────────────────────────────────────────────

def render(data_client, get_price_fn, get_bars_fn) -> None:
    st.subheader("🎮 Test Mode — Simulated Trading")
    st.info(
        "Orders are **not** sent to your broker. "
        "Buys and sells are recorded at the polled price so you can test "
        "AutoTrader strategies without risking real money.",
        icon="ℹ️",
    )

    # ── Price source selector ─────────────────────────────────────────────────
    source = st.radio(
        "Price source",
        ["⚡ Live (real-time)", "🕐 Replay (historical 1-min bars)"],
        horizontal=True,
        key="test_mode_source",
    )
    replay_mode = source.startswith("🕐")

    # ── Replay configuration ──────────────────────────────────────────────────
    replay_cfg = None
    if replay_mode:
        _today        = datetime.now().date()
        _default_date = _today - timedelta(days=[3, 1, 1, 1, 1, 1, 2][_today.weekday()])

        rc1, rc2, rc3 = st.columns(3)
        rp_date  = rc1.date_input("Date", value=_default_date,
                                  help="Must be a past trading day (Mon–Fri, non-holiday)",
                                  key="tm_rp_date")
        rp_speed = rc2.number_input("Speed (×)", min_value=1, max_value=10000, value=200, step=50,
                                    help="200 = 200× real-time. Each 1-min bar advances every 60/speed seconds.",
                                    key="tm_rp_speed")
        rp_poll  = round(60.0 / rp_speed, 3)

        tr_mode = rc3.selectbox("Time window (ET)",
                                ["Full day", "Duration", "Custom range"],
                                key="tm_tr_mode")

        rp_start_time = rp_end_time = rp_duration_h = None

        if tr_mode == "Duration":
            tw1, tw2 = st.columns(2)
            rp_start_time  = tw1.time_input("Start time (ET)", value=dtime(9, 30), key="tm_rp_st")
            rp_duration_h  = tw2.select_slider(
                "Duration", options=[0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 6.5],
                value=2.0, format_func=lambda x: f"{x:g}h", key="tm_rp_dur",
            )
            end_dt = datetime(2000, 1, 1, rp_start_time.hour, rp_start_time.minute) + timedelta(hours=rp_duration_h)
            st.caption(
                f"Replaying {rp_duration_h:g}h from {rp_start_time.strftime('%H:%M')} → "
                f"{end_dt.strftime('%H:%M')} ET  |  ≈{int(rp_duration_h*60)} bars  |  "
                f"recommended poll interval: **{rp_poll}s**"
            )
        elif tr_mode == "Custom range":
            tw1, tw2 = st.columns(2)
            rp_start_time = tw1.time_input("Start time (ET)", value=dtime(9, 30),  key="tm_rp_cst")
            rp_end_time   = tw2.time_input("End time (ET)",   value=dtime(11, 30), key="tm_rp_cet")
            dur_m = max(0, (datetime.combine(datetime.today(), rp_end_time)
                            - datetime.combine(datetime.today(), rp_start_time)).seconds // 60)
            st.caption(
                f"{rp_start_time.strftime('%H:%M')} → {rp_end_time.strftime('%H:%M')} ET  |  "
                f"≈{dur_m} bars  |  recommended poll interval: **{rp_poll}s**"
            )
        else:
            st.caption(f"Full trading day  |  recommended poll interval: **{rp_poll}s**")

        replay_cfg = {
            "date":           str(rp_date),
            "speed":          rp_speed,
            "start_time":     rp_start_time,
            "end_time":       rp_end_time,
            "duration_hours": rp_duration_h,
        }

    # ── Detect config changes → clear session when replay settings change ──────
    prev_cfg  = st.session_state.get(_TEST_CFG_KEY)
    cfg_changed = (replay_mode and replay_cfg != prev_cfg) or (not replay_mode and prev_cfg is not None)

    # ── Build or retrieve MultiTrader ─────────────────────────────────────────
    def _make_sim_fns():
        def sim_buy(symbol: str, qty: int) -> None:
            pass
        def sim_sell(symbol: str, qty: int) -> None:
            pass
        return sim_buy, sim_sell

    if cfg_changed or _TEST_MT_KEY not in st.session_state:
        # Stop existing traders before discarding
        _old_mt = st.session_state.get(_TEST_MT_KEY)
        if _old_mt is not None:
            for t in list(_old_mt._traders.values()):
                try:
                    t.stop()
                except Exception:
                    pass

        sim_buy, sim_sell = _make_sim_fns()

        if replay_mode:
            dispatcher = _ReplayDispatcher(
                data_client,
                replay_date    = replay_cfg["date"],
                speed          = replay_cfg["speed"],
                start_time     = replay_cfg["start_time"],
                end_time       = replay_cfg["end_time"],
                duration_hours = replay_cfg["duration_hours"],
            )
            st.session_state[_TEST_FEED_KEY] = dispatcher
            _get_price = dispatcher.get_price
        else:
            st.session_state.pop(_TEST_FEED_KEY, None)
            _get_price = get_price_fn

        st.session_state[_TEST_MT_KEY]  = MultiTrader(
            get_price  = _get_price,
            place_buy  = sim_buy,
            place_sell = sim_sell,
            get_bars   = get_bars_fn,
        )
        st.session_state[_TEST_CFG_KEY] = replay_cfg

    mt         = st.session_state[_TEST_MT_KEY]
    sim_buy, sim_sell = _make_sim_fns()
    dispatcher = st.session_state.get(_TEST_FEED_KEY)

    # ── Replay progress (per active symbol) ───────────────────────────────────
    if replay_mode and dispatcher:
        active_syms = [sym for sym, at in mt._traders.items()
                       if at.status.state.value in ("entering", "watching")]
        if active_syms:
            st.markdown("**Replay progress**")
            for sym in active_syms:
                frac, cur, total = dispatcher.progress_for(sym)
                ct = dispatcher.current_time_for(sym)
                label = f"{sym}  bar {cur}/{total}  {ct}" if total else sym
                st.progress(frac, text=label)
                if dispatcher.exhausted_for(sym):
                    st.warning(f"{sym}: all bars replayed — AutoTrader still watching at last price.")

    # ── Clear paper account ────────────────────────────────────────────────────
    with st.expander("⚠️ Reset simulated account", expanded=False):
        st.warning(
            "This will stop all running simulated positions and clear the entire "
            "Test Mode session, including P&L history. This cannot be undone.",
        )
        confirmed = st.checkbox("I understand — reset the paper account", key="test_mode_clear_confirm")
        if st.button("Clear paper account", disabled=not confirmed, type="primary", key="test_mode_clear_btn"):
            for trader in list(mt._traders.values()):
                try:
                    trader.stop()
                except Exception:
                    pass
            sim_buy2, sim_sell2 = _make_sim_fns()
            _get_price2 = (dispatcher.get_price
                           if replay_mode and dispatcher else get_price_fn)
            if replay_mode and replay_cfg:
                st.session_state[_TEST_FEED_KEY] = _ReplayDispatcher(
                    data_client,
                    replay_date    = replay_cfg["date"],
                    speed          = replay_cfg["speed"],
                    start_time     = replay_cfg["start_time"],
                    end_time       = replay_cfg["end_time"],
                    duration_hours = replay_cfg["duration_hours"],
                )
                _get_price2 = st.session_state[_TEST_FEED_KEY].get_price
            st.session_state[_TEST_MT_KEY] = MultiTrader(
                get_price  = _get_price2,
                place_buy  = sim_buy2,
                place_sell = sim_sell2,
                get_bars   = get_bars_fn,
            )
            st.session_state["test_mode_clear_confirm"] = False
            st.success("Paper account cleared.")
            st.rerun()

    autotrader_page.render(
        mt, (dispatcher.get_price if replay_mode and dispatcher else get_price_fn),
        sim_buy, sim_sell, get_bars_fn,
        get_equity_fn=None,
        broker="Test Mode",
        trading_client=None,
        ib=None,
    )
