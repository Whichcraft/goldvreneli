import streamlit as st


def render():
    st.title("Help & Documentation")

    with st.expander("Quick Start", expanded=True):
        st.markdown("""
### Setup (one time)
1. Go to **⚙️ Settings** → enter your Alpaca paper API keys (free at [alpaca.markets](https://alpaca.markets))
2. Select **Alpaca (Paper)** in the sidebar

### Recommended workflow
**Option A — Fully automated (recommended)**
1. Go to **📈 Portfolio Mode**
2. Set *target slots* (e.g. 5) and *$ per slot* (e.g. $3,000)
3. Click **▶ Start All** — it scans, picks the best stocks, invests, and reinvests automatically

**Option B — Manual with scanner guidance**
1. Go to **🔍 Scanner** → click **Run Scan**
2. Review the ranked results
3. Click **⚡ Invest Now** — set dollar amount and stop %, done
4. Watch live in **🤖 AutoTrader**

**Option C — Full manual**
- Use **💼 Portfolio** to view account, place orders, see open positions
- Use **🤖 AutoTrader** to enter a symbol manually with trailing stop

### Other pages
- **🎮 Test Mode** — run AutoTrader logic against live or historical prices without placing real orders
- **⚙️ Settings** — API keys, scanner filter defaults, AutoTrader defaults
""")

    with st.expander("💼 Portfolio"):
        st.markdown("""
**Account metrics** — Portfolio value, cash, buying power, equity, and day P&L (with % delta).

**Open positions** — table of current holdings with avg entry, current price, market value, unrealized P&L in dollars and percent.

**Price chart** — candlestick chart for any symbol over 1D / 1W / 1M / 3M. The symbol you type is remembered across page switches.

**Place order** — market or limit orders. Symbol is validated before submit.

**Open orders** — lists pending orders with fill status. "Cancel All" cancels everything in one click.
""")

    with st.expander("🤖 AutoTrader"):
        st.markdown("""
AutoTrader buys on start and manages the position using a trailing stop.

**Symbol & qty**

| Field | Description |
|-------|-------------|
| Symbol | Ticker to trade (blank = use Settings default) |
| Qty mode | **Shares** — fixed share count; **Dollar amount** — converts to shares at current price; **Risk %** — sizes position so a full-stop loss equals N% of equity |
| Stop mode | **PCT** — trailing stop as % below peak; **ATR** — trailing stop as a multiple of the 14-day ATR |
| Stop value | PCT: e.g. `0.5` = sell when price drops 0.5% from peak. ATR: e.g. `2.0` = 2× ATR. |
| Poll interval | Seconds between price checks (default 5s) |

**Entry modes** (expand *Entry mode*)

| Mode | Behaviour |
|------|-----------|
| Market | Buy immediately at market |
| Limit | Place limit order; cancel and fall back to market after timeout |
| Scale | Buy in N tranches, spaced by interval (dollar-cost averaging into a position) |

**Exit targets** (expand *Exit targets*)

| Setting | Description |
|---------|-------------|
| Take-profit trigger % | When up this %, sell the configured fraction. 0 = disabled. |
| Fraction to sell | Portion to sell at take-profit (e.g. 0.5 = sell half, trail the rest) |
| Breakeven trigger % | Once up this %, move stop floor to entry price (lock in breakeven). 0 = disabled. |
| Time stop (minutes) | Exit after this many minutes regardless of price. 0 = disabled. |

**Multi-symbol queue** — send multiple symbols from Scanner; they load one at a time. After starting each, the next symbol pre-fills the form automatically.

**Positions table** — shows all active/completed positions with state, prices, drawdown, P&L.

**Daily summary** — unrealized P&L across all watching positions, plus cumulative realized losses (used to enforce the daily loss limit).
""")

    with st.expander("🔍 Scanner"):
        st.markdown("""
Scans ~600 liquid US stocks, ETFs, and ADRs using daily bar data and technical indicators.

**Controls**

| Control | Description |
|---------|-------------|
| Top N | Number of candidates to return |
| Historical date | Tick to scan as of a past date (uses closing data up to that date) |
| Symbol list | Expand to choose individual symbols or scan the full universe. Pre-populated from your watchlist in Settings. |

**Hard filters** (candidates must pass all of these)

| Filter | Default | Meaning |
|--------|---------|---------|
| Min price | $5 | Excludes penny stocks |
| Min ADV | $5M/day | Minimum daily dollar volume |
| RSI(14) | 35–72 | Avoids overbought and deeply oversold |
| Volume | ≥ 1× 20-day avg | Requires above-average volume |
| SMA20 tolerance | 3% | Price may be up to 3% below SMA20 |
| Min 5d return | −1% | Filters out stocks in sharp downtrends |
| Above SMA50 | required | Intermediate-term trend filter |

**Scoring** — candidates are ranked by a composite score:

- Relative strength vs SPY (weight 3×) — most important signal
- 1-day, 5-day, 10-day, 20-day returns
- SMA20 slope (upward momentum)
- ATR% penalty (discounts high-volatility names)

**Sending to AutoTrader** — select one or more rows in the results table, then click *Send N symbol(s) to AutoTrader*. Symbols are queued; configure and start each in turn.

Filter thresholds (RSI, price, ADV, volume, SMA20 tolerance, 5d return) are adjustable inline in the **Filters** expander on the Scanner page. Click *Save as defaults* to persist them to Settings.
""")

    with st.expander("🎮 Test Mode"):
        st.markdown("""
Run AutoTrader logic against live or historical prices without placing real orders — buys and sells are simulated.

**Live** — uses real-time prices from the configured broker; runs indefinitely.

**Replay** — fetches real Alpaca 1-minute bars for the chosen symbol and date, then replays them at configurable speed. Each symbol gets its own independent replay feed.

| Setting | Description |
|---------|-------------|
| Symbol | Ticker to trade |
| Date | Trading day to replay |
| Speed | 200 = 200× real time. Poll interval is set automatically. |
| Full day | Replay the entire trading session |
| Duration | Start at a time, replay for N hours |
| Custom range | Specify exact start and end time (ET) |

**Reset simulated account** — clears all open simulated positions and resets the session. Guarded by a confirmation checkbox.
""")

    with st.expander("⚙️ Settings"):
        st.markdown("""
All settings are saved to `.env` in the install directory and persist across restarts.

**Alpaca** — API key and secret for paper trading. Get them at alpaca.markets → Paper Trading → API Keys.

**IBKR** — username, password, trading mode (paper/live), and paths to IBC and IB Gateway. These are auto-detected by the installer; only change them if you installed to a custom location.

**AutoTrader Defaults** — pre-fill values for the AutoTrader form.

| Setting | Description |
|---------|-------------|
| Default Symbol | Pre-fills the symbol field |
| Trailing Stop % | Default PCT stop value |
| Poll Interval | Default price-check frequency |
| Daily Loss Limit | Halt new trades when realized losses reach this amount. 0 = disabled. |

**Scanner Filters** — defaults for all hard-filter thresholds. Override per-run using the controls on the Scanner page.

**Watchlist** — comma-separated symbols pre-selected in the Scanner symbol list. Leave blank to start with the full universe.
""")

    with st.expander("IBKR Setup"):
        st.markdown("""
1. Select **IBKR** in the sidebar and enter credentials in **⚙️ Settings**.
2. On the Portfolio page, click **Start Gateway** — IB Gateway launches headlessly via IBC + Xvfb (30–90s startup time).
3. Click **Connect** once the API port shows as *Open*.
4. Use port `4002` for paper trading, `4001` for live.

**Authentication** — IBC supports IBKR Mobile push notifications (approve once at startup). Hardware tokens require one manual login per day.

**Gateway status panel** — shows process state, API port, and IB session status. Use Stop Gateway / Disconnect to cleanly shut down.
""")

    with st.expander("Tips"):
        st.markdown("""
- **Scanner → AutoTrader workflow**: Run Scanner, select top candidates in the table (multi-row), click *Send to AutoTrader*. Configure stop/qty for the first symbol and start; the next symbol pre-fills automatically.
- **Test before live**: Use 🎮 Test Mode with Replay to validate your stop settings on recent historical data before using AutoTrader during market hours.
- **Risk % sizing**: Set qty mode to *Risk %* so that a full stop-out always costs the same fraction of your equity, regardless of the stock's price or volatility.
- **Breakeven + take-profit together**: Set take-profit to sell half at +1%, and breakeven at +0.5%. You lock in profit on half the position and can never lose money on the other half.
- **Stale scan warning**: If scan results are more than 30 minutes old, a warning appears. Re-run the scan before sending symbols to AutoTrader.
- **Daily loss limit**: Set a dollar amount in Settings to automatically block new AutoTrader entries after you've lost that much in realized P&L for the day.
""")
