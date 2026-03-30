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

### ~~23. Allow realized loss to exceed trailing-stop value~~ ✓ fixed in 0.35.1
Investigate scenarios where the actual realized loss on a trade can be larger than the configured trailing-stop threshold (e.g. gap-down opens, illiquid fills, scale-in entries where stop is calculated from first fill only). Document the cases and decide whether to add a hard max-loss guard per position.

### ~~24. Installer deploys even when already up to date~~ ✓ fixed in 0.34.1
When the installer reports "Already up to date", it still proceeds to "Deploying updated production files…" and runs dependency updates unnecessarily. The deploy + pip-install steps should be skipped entirely when no new version was fetched.

### ~~25. Test Mode: "Clear paper account" button with confirmation~~ ✓ fixed in 0.35.4
Add a **Clear paper account** button to the Test Mode page that resets the simulated `MultiTrader` (drops all open positions and resets the session). Guard the action with an "Are you sure?" confirmation step (e.g. `st.checkbox` or a two-click pattern) so it can't be triggered accidentally.

### ~~27. Test/simulation mode: pick historical start time and accelerate clock~~ ✓ fixed in 0.35.6
In Test Mode, allow the user to select a historical date + time of day to begin the simulation from, and provide a time-acceleration multiplier (e.g. 2×, 5×, 10×) so sessions can run faster than real time. Useful for verifying stop/take-profit logic against known intraday price sequences without waiting in real time.

### ~~26. Increase international position coverage (Swiss universe)~~ ✓ fixed in 0.35.4
Expanded `UNIVERSE_CH` from 9 to ~50 Swiss ADRs + US-listed equities, covering all SMI blue chips and SMIM mid-caps with US OTC ADRs.

### ~~28. Group Test Mode and Historic Mode together under the Testing sidebar section~~ ✓ fixed in 1.3.0
Move Test Mode and Historic Mode (the historical simulation from #27) into the same collapsible "Testing" sidebar group so all simulation/dry-run pages are co-located.

---

## Reliability

### ~~29. AutoTraderStatus thread-safety: add a status lock~~ ✓ fixed in 1.3.0
`AutoTraderStatus` fields (`current_price`, `pnl`, `state`, `stop_floor`, etc.) are written by the AutoTrader daemon thread and read concurrently by the Streamlit UI thread — with no synchronisation. In CPython this rarely causes corruption due to the GIL, but composite updates (e.g. setting `pnl` and `state` together) can be observed half-updated by the UI. Fixed by making `MultiTrader.statuses()` return snapshot copies taken under the lock.

### ~~30. TraderConfig validation~~ ✓ fixed in 1.1.0
`TraderConfig` silently accepts nonsensical values that cause wrong or undefined behaviour at runtime:
- `stop_value ≤ 0` → stop floor is never below entry; position is never sold
- `scale_tranches < 1` → division by zero in `_do_scale_entry`
- `tp_qty_fraction > 1.0` → attempts to sell more shares than held
- `max_loss_pct < 0` → guard fires immediately on entry
Add a `__post_init__` validator that raises `ValueError` on invalid combinations.

### ~~31. `daily_loss.json` non-atomic write~~ ✓ fixed in 1.1.0
`daily_loss.json` is written with a plain `write_text()` call. A crash mid-write leaves a truncated/corrupt file, and the next session fails to load the loss limit, bypassing the daily guard. Use the same atomic write pattern already used in `MockBroker` (write to `.tmp` → `rename`).

### ~~32. Scale entry partial-fill inconsistency~~ ✓ fixed in 1.1.0
If `place_buy` raises an exception on tranche 2+ (broker rejection, network error), `_do_scale_entry` breaks out of the loop. `status.qty_remaining` is set to `total_filled` (correct) but `status.qty` is also updated to `total_filled` — however if the exception propagates instead of being caught, the method returns `False` and `_run()` treats the entry as failed, leaving an orphaned partial position with no stop. Wrap each `place_buy` call in a try/except; on failure log the error, break cleanly, and if at least one tranche filled proceed to WATCHING rather than aborting.

### ~~33. Scanner per-symbol fetch timeout~~ ✓ fixed in 1.3.0
`scan()` has no per-symbol timeout. A single slow or hanging Alpaca API call blocks the entire scan thread indefinitely. Wrap each `fetch_bars()` call with a timeout (e.g. via `concurrent.futures.ThreadPoolExecutor` with a per-task timeout), and count timed-out symbols in the `skipped` report alongside "insufficient history" entries.

### ~~34. AutoTrader heartbeat timestamp~~ ✓ fixed in 1.1.0
`AutoTraderStatus` has no "last-polled-at" timestamp. If the polling thread stalls (e.g. `get_price` hangs waiting on a broker API with no timeout), the UI table shows a frozen price with no indication that monitoring has stopped. Add `last_poll_at: Optional[datetime]` to `AutoTraderStatus` and update it on every price fetch. Surface a warning in the AutoTrader table when `now − last_poll_at > 3 × poll_interval`.

---

## Testing

### ~~35. MultiTrader unit tests~~ ✓ fixed in 1.1.0
`MultiTrader` has zero test coverage despite being the central coordinator for all live trading. Tests needed:
- Slot limit is respected (target_slots cap)
- `start()` / `stop_all()` lifecycle
- Daily loss limit blocks new entries after threshold exceeded
- Daily loss persists across MultiTrader reconstructions (via `daily_loss.json`)
- `statuses` dict reflects correct states after trade close

### ~~36. Scale entry lifecycle test~~ ✓ fixed in 1.1.0
`_do_scale_entry` is untested. Add tests:
- 3-tranche scale produces correct average entry price
- Stop fires at correct floor after scale completion
- Stop() mid-scale leaves no dangling position (STOPPED state, no sell)

### ~~37. ATR stop full-lifecycle test~~ ✓ fixed in 1.1.0
`_calc_atr` is unit-tested but ATR stop mode through the full `AutoTrader._run()` loop is not. Add a test that wires a `SyntheticPriceFeed` + a mock `get_bars` returning a fixed DataFrame, starts with `StopMode.ATR`, drives price above peak then below stop floor, and verifies the sell fires.

### ~~38. Partial take-profit test (tp_qty_fraction < 1.0)~~ ✓ fixed in 1.1.0
`tp_qty_fraction` (sell only a fraction on take-profit, let the rest trail) is used in production but has no test. Add tests:
- When `tp_qty_fraction=0.5`, only half of qty is sold at take-profit
- Remaining qty continues trailing; trailing stop fires for the second half
- `realized_pnl` and `qty_remaining` are updated correctly after partial exit

### ~~39. ReplayPriceFeed unit tests~~ ✓ fixed in 1.1.0
`ReplayPriceFeed` is untested. Tests:
- `get_price` returns bars in sequence
- `exhausted` flag set after last bar
- `recommended_poll_interval` = `60 / speed`
- `start_time` / `end_time` filter applied correctly on fixture data (no Alpaca API call needed — inject a pre-built DataFrame via monkeypatching `_fetch`)
- `reset()` restarts from first bar
- Raises `ValueError` on empty result after filtering

### ~~40. PortfolioManager smoke tests~~ ✓ fixed in 1.3.0
`PortfolioManager` has zero test coverage. At minimum:
- `start_all()` opens N positions up to `target_slots`
- Closed positions trigger a refill from the candidate list
- `daily_loss_limit` propagates to underlying `MultiTrader`
Use `MockBroker`-style stubs for `place_buy`, `place_sell`, and `get_price`; inject a fixed candidate list to avoid scanner network calls.

---

## UX

### ~~41. Restart AutoTrader from ERROR state~~ ✓ fixed in 1.3.0
Once an `AutoTrader` enters `ERROR` state the user has no way to restart it for the same symbol short of clearing the whole `MultiTrader`. Add a **Restart** button in the AutoTrader positions table (shown only for ERROR-state rows) that calls `at.stop()` then re-queues the symbol with the original config. Confirm before restarting to avoid double-buying.

### ~~42. Scanner excludes already-open positions~~ ✓ fixed in 1.1.0
The scanner can recommend a symbol that is already held as an open position in the current `MultiTrader` session. Add a filter: when `mt` is available, subtract `mt.open_symbols()` from the candidate list before ranking so Quick Invest never tries to buy a duplicate.

### ~~43. Settings page: test API connection button~~ ✓ fixed in 1.3.0
API keys are saved to `.env` without any validation. Add a **Test connection** button next to the Alpaca key fields that makes a lightweight API call (e.g. `get_account()`) and shows a green checkmark or error inline, without navigating away.

### ~~44. Export trade history to CSV~~ ✓ fixed in 1.1.0
`live_fills.json` and `backtest_fills.json` can only be inspected in-app. Add a **Download CSV** button on the AutoTrader and Backtest pages that converts the current session's fills to CSV and triggers a browser download via `st.download_button`.

### ~~49. Portfolio top/bottom ticker strip with keep/sell quick actions~~ ✓ fixed in 1.3.0
Add a compact strip or card row at the top of the Portfolio page showing the best and worst performing open positions (e.g. top 3 winners and top 3 losers by unrealised P&L %). Each card shows symbol, current P&L %, and two quick-action buttons — **Keep** (dismisses the card until next rerun) and **Sell** (closes the position immediately, with a brief confirmation). Makes it trivial to act on outliers without scrolling through the full table.

### ~~48. Cash-out panel: liquidate everything or highlight best holdings~~ ✓ fixed in 1.3.0
Add a prominent panel (e.g. top of Portfolio or AutoTrader page) with two quick actions:
- **Cash out all** — one-click button (with confirmation) that sells every open position immediately
- **Best holdings highlight** — sort open positions by unrealised P&L and visually surface the top performers (e.g. coloured badges or a pinned top-N table) so the user can decide at a glance which ones to realise
The goal is making the exit decision fast and visible rather than buried in the positions table.

### ~~51. [IMPORTANT] Fix scan: always returns "not a good time to invest"~~ ✓ fixed in 1.2.0
Root cause: `days=60` (calendar) ≈ 42 trading days < 52 required by `score_symbol`. All symbols silently skipped. Fixed by raising to `days=80`.

### ~~50. Remove backtest completely~~ ✓ fixed in 1.2.0
Removed `pages/backtest_page.py` and all nav/dispatch references. `replay.py` retained (used by Test Mode and tests).

### ~~57. Highlight active broker/mode in the sidebar~~ ✓ fixed in 1.4.0
The sidebar header currently says "Alpaca Paper and Live Trading" and "Interactive Brokers (IBKR)" but gives no visual indication of which broker and mode is actually active. Replaced plain captions with `🟢 Active: Alpaca · Live` / `🟡 Active: Alpaca · Paper` badges.

---

## Reliability

### ~~58. Scanner: unhandled TimeoutError and per-future exceptions in `scan()`~~ ✓ fixed in 1.4.0
`as_completed(futs, timeout=120)` raises `concurrent.futures.TimeoutError` if not all futures complete within 120 s. Fixed: loop wrapped in `try/except TimeoutError`; individual chunk failures caught and skipped.

### ~~59. AutoTrader: live trailing-stop adjustment per position~~ ✓ fixed in 1.4.0
`AutoTrader.set_threshold(pct)` already mutates `stop_value` and `threshold_pct` live, but it is never exposed in the UI. Added number input in each WATCHING position card; calls `mt.set_threshold(sym, new_pct)` on change.

### ~~60. Portfolio Mode: pause button (halt new opens, keep monitoring existing)~~ ✓ fixed in 1.4.0
Added `pm.pause()` / `pm.resume()` API and ⏸ Pause / ▶ Resume buttons. `_open_one_slot` returns immediately when `_paused=True`.

### ~~61. Settings: IBKR gateway test button~~ ✓ fixed in 1.4.0
Added "Test IBKR Gateway" button that checks `ib.isConnected()` and queries `accountSummary()`, showing net liquidation on success.

---

## UX

### ~~62. Portfolio ticker strip: stale dismissed-symbol set~~ ✓ fixed in 1.4.0
The `_portfolio_dismissed` set in `st.session_state` accumulates symbols across reruns but is never pruned. Fixed: `_dismissed &= _open_syms` on every render.

### ~~63. Portfolio Mode: force-rescan button~~ ✓ fixed in 1.4.0
Added **🔄 Rescan** button next to the scan-age caption that triggers `pm._rescan()` in a background thread.

### ~~64. Scanner results: user-controlled sort column~~ ✓ fixed in 1.4.0
Added sort-column selectbox + ascending checkbox above the results table. Sort applied to `results` DataFrame before both rendering and Quick Invest, so top-N picks always match the visible order.

---

## Small wins

### ~~45. Surface unavailable OTC symbols separately in scanner skipped count~~ ✓ fixed in 1.1.0
With ~94 Swiss symbols (many OTC), a significant fraction will fail data fetch entirely (no Alpaca coverage) rather than fail the 52-bar check. Currently both are lumped into the same "skipped" count. Split into `skipped_no_data` vs `skipped_insufficient_history` and show both in the scanner caption.

### ~~52. Replace "(N)" quantity notation with a meaningful label~~ ✓ fixed in 1.3.1

Throughout the UI, quantities are shown as bare numbers like "(3)" or "Top N" with no unit. Replace with a human-readable label — e.g. "3 positions", "5 stocks", or similar — so users immediately understand what the number refers to.

### ~~46. Scanner: warn on ETF in ATR-stop mode~~ ✓ fixed in 1.3.0
ATR stop needs `get_bars` to return a DataFrame with `high`/`low`/`close`. For ETFs and OTC ADRs, some brokers (esp. IBKR) do not return intraday bars with `high`/`low`. Surface a one-time warning if the selected universe contains ETFs and the stop mode is ATR.

### ~~47. Lock `TraderConfig` after `start()` / `attach()`~~ ✓ fixed in 1.3.0
`set_threshold()` mutates `status.config.stop_value` live, which is intentional. But other config fields (entry mode, scale tranches, tp fraction) can also be mutated in-flight from the UI with no safety guard, potentially leaving the trader in an inconsistent mid-entry state. Mark config fields that must not change after entry as read-only (e.g. with `frozen=True` on a sub-dataclass) or document the invariant and guard mutations with a state check.

### ~~53. Clarify meaning of `side: long` in open positions~~ ✓ fixed in 1.3.1
Open positions include a `side: long` field — investigate what this means and whether it is needed. Is it ever anything other than `long`? If not, it may be dead data that can be removed. Confirmed always "long" (long-only strategy) — removed column.

### ~~54. Autocomplete symbol name on place order~~ ✓ fixed in 1.3.1
When entering a ticker symbol in the place-order input, provide autocomplete suggestions (e.g. from the scanner universe or a broker symbol search) so users don't have to remember exact symbols.

### ~~55. Verify positions are re-filled on sell with a good candidate~~ ✓ verified in 1.3.0
Confirm that when a position closes, `PortfolioManager` correctly refills the slot from the candidate list — specifically that a fresh scan candidate is used and the slot count stays at target. Covered by `test_refill_on_close` in `tests/test_portfolio.py`.

### ~~56. Verify top price is recalculated on price changes~~ ✓ verified in 1.3.1
Check whether the trailing-stop peak price (`status.top_price`) is updated on every price poll or only on entry. Confirmed: `autotrader.py:556` updates `peak_price` on every poll iteration, and `_update_stop_floor()` is called immediately. ATR stop tests cover this implicitly.

---

## Small wins

### ~~11. Reduce `fetch_bars()` lookback from 90 to 60 days~~ ✓ fixed in 0.34.0
Most indicators use ≤ 20 days of data; `score_symbol()` requires only 52 bars. Fetching 90 days wastes bandwidth and slows scans.

### ~~12. Surface "insufficient history" reason in scanner~~ ✓ fixed in 0.34.0
Stocks with < 52 bars silently drop from results with no explanation. Add a count or expandable list of symbols skipped for insufficient history.

### ~~13. Warn on corrupted `MockBroker` JSON~~ ✓ fixed in 0.34.0
Currently falls back to an empty session list silently. Should log a visible warning so users know backtest history was lost.
