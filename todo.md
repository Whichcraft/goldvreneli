# Goldvreneli — Improvement Backlog

---

## Reliability

### ~~1. Silent AutoTrader thread death~~ ✓ fixed in 0.29.0
`_run()` daemon thread exits silently on unexpected exceptions. The position row freezes at stale prices with no stop and no alert — open positions are left unmanaged.
- Wrap `_run()` body in `try/except`; on exception set state to `ERROR`, call `_on_close(pnl=0)`, log the traceback
- Surface `ERROR` state visually in the AutoTrader table

### ~~2. Daily loss limit bypassed by broker switch~~ ✓ fixed in 0.29.0
Switching brokers or toggling IBKR paper↔live clears `multitrader` from session state, resetting `_realized_loss` to zero. A user can bypass their loss limit by flipping a toggle.
- Persist cumulative realized loss for the calendar day in `.env` or a flat file keyed by date
- `MultiTrader` should load the persisted value on construction and add to it, not start from 0

### ~~3. IBKR gateway crash recovery~~ ✓ fixed in 0.29.0
If the gateway crashes mid-session, `gw_start_attempted` and `ib_connect_attempted` flags block any auto-retry. No heartbeat or reconnect path exists.
- Settings page should detect a dead gateway (`gw.is_running() == False`) and clear both flags automatically
- Add a visible "Gateway lost — click to reconnect" warning when connection drops

---

## Observability

### ~~4. No persistent live trade log~~ ✓ fixed in 0.30.0
Backtest fills are written to `backtest_fills.json` but live trades have no equivalent. All fill history is lost on Streamlit restart.
- Write a `live_fills.json` (same format as `backtest_fills.json`) from `alpaca_buy/sell` and `ibkr_buy/sell`
- Surface a session history table on the AutoTrader page (mirrors the Backtest page UI)

### ~~5. Realized P&L resets on session clear~~ ✓ fixed in 0.29.0 (via #2)
`MultiTrader._realized_loss` lives in session state. Any broker switch or accidental page close loses the day's P&L history, even though it's shown prominently in the UI.
- Tie to the same persistence mechanism as #2 above

---

## UX

### ~~6. Auto-refresh interrupts form input~~ ✓ fixed in 0.32.0
The 5-second `st.rerun()` loop resets unfocused form inputs while the user is typing symbols or adjusting sliders.
- Wrap the auto-refreshed status tables in `st.fragment` (Streamlit ≥ 1.37) so they refresh independently without rerunning the whole page
- No logic changes needed — purely a rendering restructure

### ~~7. Scanner stale warning but no background refresh~~ ✓ fixed in 0.32.0
Results go stale after 30 minutes with a warning, but the user must re-scan manually. Portfolio Mode already auto-rescans internally.
- When results are stale and no scan is in progress, trigger a background rescan automatically (same logic as `PortfolioManager._candidates_stale()`)

### ~~8. Quick Invest gives no fill price confirmation~~ ✓ fixed in 0.32.0
After *Invest Now*, the page navigates away immediately. Per-symbol errors are briefly shown but lost on navigation.
- Show a post-invest summary (symbol, qty, approx fill price, any errors) before navigating
- Use `st.success` / `st.error` per position or a small results table

---

## Architecture

### ~~9. Split `goldvreneli.py` into page modules~~ ✓ fixed in 0.31.0
The file is 2000+ lines and growing. Streamlit's multipage file structure supports per-page modules natively.
- Move each page into `pages/portfolio.py`, `pages/autotrader.py`, `pages/portfolio_mode.py`, `pages/scanner.py`, `pages/backtest.py`, `pages/settings.py`, `pages/help.py`
- Shared broker callables and session setup stay in a `ui_core.py` or similar
- `_IbkrDataClient` shim moves to its own module (e.g. `ibkr_data.py`)

### ~~10. Add unit tests~~ ✓ done (45 tests in tests/)
Business logic is already fully decoupled from the UI by design but has zero test coverage. Good candidates requiring no mocking:
- `size_from_risk`, `_calc_atr` (autotrader.py)
- `score_symbol`, `scan()` with fixture DataFrames (scanner.py)
- `SyntheticPriceFeed`, `MockBroker` (replay.py)
- `AutoTrader` full lifecycle with `SyntheticPriceFeed` + `MockBroker`

---

## Pending / New

### ~~14. Activity Log: add Symbol column~~ ✓ fixed in 0.34.0
Add a Symbol column to the Activity Log table so each entry shows which ticker the action relates to.

### ~~15. Activity Log: rename "New peak $ | stop floor $" column~~ ✓ fixed in 0.34.0
The label "stop floor $" is ambiguous — clarify to "new stop floor $" (or similar) so it's obvious this is the updated trailing stop floor, not the original stop.

### ~~16. Trade history: update on auto-sell~~ ✓ fixed in 0.34.1
The trade history table doesn't refresh when an AutoTrader sells automatically. Trigger a history update when an auto-sell fires so the table stays current without a manual rerun.

### ~~17. Scan history window~~ ✓ fixed in 0.34.2
Add a scan history view that shows previous scan runs (timestamp, filter settings used, number of results) so users can compare or replay past scans.

### ~~18. Rename "Realized losses today" → wins framing~~ ✓ fixed in 0.34.0
"Realized losses today" is discouraging. Rename to something positive, e.g. "Realized P&L today" or "Today's closed trades", so winning days feel rewarding rather than loss-focused.

### ~~19. Move Activity Log to a dedicated `activity_tracker` module~~ ✓ fixed in 0.34.2
Extract the activity-log logic (state, append, render) from page files into a new `activity_tracker.py` module to keep pages thin and the tracker reusable.

### ~~20. Group Backtest + Test Mode under a "Testing" section in the sidebar~~ ✓ fixed in 0.35.0
Move the Backtest page and Paper Trading / Test Mode into a dedicated "Testing" collapsible group in the left sidebar nav, separate from the live-trading pages. Test Mode should let users run AutoTrader logic against live prices without placing real orders (dry-run / paper mode).

### ~~21. Activity Log: persistent left-sidebar panel~~ ✓ fixed in 0.34.2
Surface the Activity Log as a persistent panel in the left sidebar so it's visible from any page, not just when scrolling down the AutoTrader page. Should show the last N entries and auto-refresh.

### ~~22. Remove default Streamlit page-link nav from top of sidebar~~ ✓ fixed in 0.34.1
The auto-generated page links Streamlit renders at the top of the sidebar duplicate the custom nav and clutter the UI. Hide them (e.g. via `st.set_page_config` options or CSS) so only the custom navigation is shown.

### 23. Allow realized loss to exceed trailing-stop value
Investigate scenarios where the actual realized loss on a trade can be larger than the configured trailing-stop threshold (e.g. gap-down opens, illiquid fills, scale-in entries where stop is calculated from first fill only). Document the cases and decide whether to add a hard max-loss guard per position.

### ~~24. Installer deploys even when already up to date~~ ✓ fixed in 0.34.1
When the installer reports "Already up to date", it still proceeds to "Deploying updated production files…" and runs dependency updates unnecessarily. The deploy + pip-install steps should be skipped entirely when no new version was fetched.

---

## Small wins

### ~~11. Reduce `fetch_bars()` lookback from 90 to 60 days~~ ✓ fixed in 0.34.0
Most indicators use ≤ 20 days of data; `score_symbol()` requires only 52 bars. Fetching 90 days wastes bandwidth and slows scans.

### ~~12. Surface "insufficient history" reason in scanner~~ ✓ fixed in 0.34.0
Stocks with < 52 bars silently drop from results with no explanation. Add a count or expandable list of symbols skipped for insufficient history.

### ~~13. Warn on corrupted `MockBroker` JSON~~ ✓ fixed in 0.34.0
Currently falls back to an empty session list silently. Should log a visible warning so users know backtest history was lost.
