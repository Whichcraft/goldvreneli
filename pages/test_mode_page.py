"""
Test Mode — runs AutoTrader logic against live prices without placing real orders.
Buy/sell are simulated: fills are recorded at the current bid/ask but no broker
order is submitted.
"""
import streamlit as st
from autotrader import MultiTrader
import pages.autotrader_page as autotrader_page

_TEST_MT_KEY = "test_mode_multitrader"


def render(data_client, get_price_fn, get_bars_fn) -> None:
    st.subheader("🎮 Test Mode — Simulated Trading")
    st.info(
        "Orders are **not** sent to your broker. "
        "Buys and sells are recorded at the live bid/ask price so you can test "
        "AutoTrader strategies without risking real money.",
        icon="ℹ️",
    )

    # Simulated buy/sell — no broker call, just pass through
    def sim_buy(symbol: str, qty: int) -> None:
        pass  # AutoTrader records the fill itself at current price

    def sim_sell(symbol: str, qty: int) -> None:
        pass

    if _TEST_MT_KEY not in st.session_state:
        st.session_state[_TEST_MT_KEY] = MultiTrader(
            get_price  = get_price_fn,
            place_buy  = sim_buy,
            place_sell = sim_sell,
            get_bars   = get_bars_fn,
        )
    mt = st.session_state[_TEST_MT_KEY]

    autotrader_page.render(
        mt, get_price_fn, sim_buy, sim_sell, get_bars_fn,
        get_equity_fn=None,
        broker="Test Mode",
        trading_client=None,
        ib=None,
    )
