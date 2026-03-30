# Changelog

All notable changes to this project will be documented here.

---

## [Unreleased]

---

## [1.1.0] — 2026-03-30

### Fixed
- **`daily_loss.json` atomic write** — replaced plain `open(...,"w")` with write-to-tmp + rename so a mid-write crash can no longer corrupt the daily loss guard (#31)
- **Scale entry partial-fill recovery** — each tranche buy is now wrapped in try/except; on failure an ERROR log entry is written and the trader proceeds to WATCHING with however many shares were filled rather than silently orphaning a partial position (#32)

### Added
- **`TraderConfig` validation** — `__post_init__` raises `ValueError` for nonsensical values: `stop_value ≤ 0`, `poll_interval ≤ 0`, `scale_tranches < 1`, `tp_qty_fraction` outside (0,1], `max_loss_pct < 0` (#30)
- **AutoTrader heartbeat** — `AutoTraderStatus.last_poll_at` updated on every price fetch; the per-position card in AutoTrader page warns when last poll was more than 3× poll_interval ago (#34)
- **Scanner: split skipped count** — `scan()` now returns a 3-tuple `(df, skipped_history, skipped_no_data)`. The scanner page shows both counts separately: "N skipped (< 52 bars) | M unavailable (no data)" (#45)
- **Scanner: warn on already-open positions** — Quick Invest shows an info banner for symbols already being tracked by the active MultiTrader, and skips them silently when investing (#42)
- **Export fills to CSV** — ⬇ Download fills CSV button on AutoTrader (live fills) and Backtest (backtest fills) pages via `st.download_button` (#44)

### Tests (76 total, up from 47)
- `TestTraderConfigValidation` — 9 tests for all `TraderConfig.__post_init__` constraints (#30)
- `TestScaleEntry` — average entry price, stop fires after all tranches, stop() mid-scale (#36)
- `TestPartialTakeProfit` — partial sell at take-profit, remainder continues trailing; full close (#38)
- `TestAtrStopLifecycle` — ATR stop fires via full `AutoTrader._run()` loop with mock `get_bars` (#37)
- `TestMultiTrader` — 6 tests: start, duplicate symbol, concurrent positions, stop_all, daily loss limit, statuses (#35)
- `TestReplayPriceFeed` — 8 tests: sequence, exhaustion, last price on exhaust, poll interval, progress, reset, bar_count, current_bar (#39)

---

## [1.0.0] — 2026-03-30

### Changed
- First stable release — all backlog items resolved, full feature parity across Alpaca and IBKR, comprehensive unit test suite, and complete documentation.

---

## [0.35.6] — 2026-03-30

### Added
- **Test Mode: Replay price source** — new "Price source" selector (Live / Replay). In Replay mode, pick a historical date, speed multiplier (1×–10000×), and optional time window (Full day / Duration / Custom range ET). Each symbol gets its own `ReplayPriceFeed` created lazily on first use so multiple simultaneous positions replay their own independent bar sequences. Per-symbol progress bars shown while positions are active. Switching replay config automatically resets the simulated account.

---

## [0.35.5] — 2026-03-30

### Added
- **Swiss universe extended to ~94 symbols** — added 46 more net: 5 Swiss-incorporated NYSE/NASDAQ names (GRMN, CB, TEL, RIG, WFRD), plus OTC ADRs/foreign shares covering watches (SWGAY), technology (Tecan, Sensirion, u-blox, Inficon, Comet, LEM, Feintool, Huber+Suhner, Belimo, Interroll, Burckhardt, Dätwyler, Autoneum, Montana Aerospace, Rieter), pharma/medtech (Medartis, BB Biotech, Siegfried, Galenica, Ypsomed), real estate (Swiss Prime Site, PSP Swiss Property, Mobimo), financial (Vontobel, BCV, Valiant, Cembra, HBM Healthcare), and industrials/other (SoftwareOne, Forbo, Zehnder, Gurit, Bossard, Meyer Burger, Flughafen Zürich, ALSO, Stadler Rail, Emmi, TX Group)

---

## [0.35.4] — 2026-03-30

### Added
- **Swiss universe expanded** — `UNIVERSE_CH` grows from 9 to ~50 symbols: added all SMI blue chips (Lonza, Sika, Zurich Insurance, Holcim, Swiss Re, Givaudan, Adecco, Kuehne+Nagel, Julius Baer, Swiss Life, Sonova, Swisscom, SGS, Partners Group), mid-caps (Helvetia, Baloise, Temenos, Clariant, Straumann, Lindt, Geberit, EMS-Chemie, Georg Fischer, Schindler, VAT Group, ams-OSRAM, OC Oerlikon, dormakaba, Barry Callebaut, Landis+Gyr, Glencore, Sulzer, SFS Group, Bucher Industries, Avolta, EFG International), plus Alcon and Sandoz (recent Novartis spin-offs on NYSE), and `HEWL` hedged ETF
- **Test Mode: Clear paper account** — new "Reset simulated account" expander with checkbox confirmation guard; stops all running simulated positions and resets the session

---

## [0.35.2] — 2026-03-30

### Fixed
- Hardened the max-loss guard with three improvements:
  1. Max-loss is now checked BEFORE the time-stop so it always takes priority when a position is deeply underwater at timer expiry
  2. Immediate max-loss check fires right after entry completes (catches gap-downs that occur during scale/limit entry intervals before the monitor loop starts)
  3. When max_loss_pct > 0, the monitor loop sleeps in 1 s sub-ticks and re-checks price at each sub-tick, preventing a fast-moving stock from blowing past the guard for a full poll_interval undetected
- Added unit test `test_max_loss_guard_beats_time_stop`

---

## [0.35.1] — 2026-03-30

### Added
- `max_loss_pct` field to `TraderConfig` — a hard per-position exit guard that fires when price drops ≥ N% below the entry price, regardless of the trailing-stop level. Catches gap-down opens and poll-interval slippage that can push realized loss past the configured trailing stop. Exposed as "Max loss from entry (%)" in the AutoTrader form. Added unit test `test_max_loss_guard_fires` (#23)

---

## [0.35.0] — 2026-03-30

### Added
- New "Testing" section in sidebar nav separates live-trading pages from Backtest and new Test Mode page. Test Mode runs AutoTrader logic against live prices without placing real broker orders (simulated buy/sell) (#20)

---

## [0.34.2] — 2026-03-30

### Added
- Activity Log rendering extracted into new `activity_tracker.py` module with `render_log()` and `render_sidebar_log()` functions; `autotrader_page.py` now calls `render_log(mt)` instead of inlining the table (#19)
- Activity Log now appears as a persistent collapsible panel in the left sidebar (visible from any page) when a MultiTrader session is active (#21)
- Scanner now records a scan history (last 10 runs) showing timestamp, market, top-N, result count, skipped count, and key filter settings; shown in an expander below results (#17)

---

## [0.34.1] — 2026-03-30

### Fixed
- Trade history now refreshes automatically when an auto-sell fires; fragment detects new session count (#16)
- Auto-generated Streamlit page-link nav hidden from top of sidebar via CSS (#22)
- Installer now skips deploy and pip-install when already up to date; both git-pull fast path and fallback clone path (#24)

---

## [0.34.0] — 2026-03-30

### Fixed
- Scanner: `fetch_bars()` lookback reduced from 90 to 60 days (saves bandwidth; most indicators only need ~52 bars) (#11)
- Scanner: now surfaces a count of symbols skipped for insufficient price history (< 52 bars) below the results (#12)
- Backtest: `load_sessions()` and `MockBroker._save_session()` in replay.py now log a visible warning when the fills JSON is corrupted instead of failing silently (#13)

### Changed
- Activity Log: table now includes a Symbol column (#14)
- AutoTrader: PEAK log note text changed from "stop floor $" to "new stop floor $" for clarity (#15)
- Portfolio: "Realized losses today" metric renamed to "Realized P&L today" with signed formatting (#18)

---

## [0.33.0] — 2026-03-30

_(in development)_

---

## [0.32.0] — 2026-03-30

### Changed
- **AutoTrader**: positions table and activity log wrapped in `@st.fragment` — auto-refreshes every 5 s independently of the form above, so typing symbols or adjusting sliders is no longer interrupted (#6)
- **Scanner**: stale results (> 30 min) now trigger an automatic background rescan instead of just showing a warning (#7)
- **Quick Invest**: clicking *Invest Now* now shows a per-symbol fill summary (symbol, qty, approx fill price, invested amount, status) before navigating — errors are visible and a *Go to AutoTrader* button controls navigation (#8)
- **Unit tests**: 45 tests added covering `size_from_risk`, `_calc_atr`, `SyntheticPriceFeed`, `MockBroker`, and `AutoTrader` full lifecycle (#10)

---

## [0.31.0] — 2026-03-30

### Changed
- **Modularized UI**: `goldvreneli.py` split from 2084 lines into page modules — each page is now its own module under `pages/` with a `render(...)` function; `goldvreneli.py` is reduced to ~450 lines (sidebar + broker setup + dispatch)
- **`ibkr_data.py`**: `_IBKRDataClient` inner class extracted to a standalone `IBKRDataClient` class used by both Scanner and Backtest pages
- Page modules: `pages/settings_page.py`, `pages/help_page.py`, `pages/portfolio_page.py`, `pages/autotrader_page.py`, `pages/portfolio_mode_page.py`, `pages/scanner_page.py`, `pages/backtest_page.py`
- No logic changes — purely structural reorganisation

---

## [0.30.0] — 2026-03-30

### Added
- **Persistent live trade log**: every live position opened via `MultiTrader` is now recorded to `live_fills.json` using the same session format as `backtest_fills.json`; fills survive Streamlit restarts and broker switches
- **Trade History table on AutoTrader page**: shows all past live sessions (symbol, entry time, close time, buy/sell count, P&L) with per-session fill detail in expandable rows — mirrors the Backtest session history UI
- **`LiveFillLogger` in `core.py`**: thread-safe fill logger with `open_session` / `record` / `close_session` methods; wired into `MultiTrader` via three new optional callbacks (`fill_open_fn`, `fill_record_fn`, `fill_close_fn`)

---

## [0.29.0] — 2026-03-30

### Fixed
- **AutoTrader thread crash**: unhandled exception in `_run()` now calls `_on_close` before exiting so `PortfolioManager` refills the slot and loss accounting is updated; previously positions silently froze in ERROR state
- **Daily loss limit reset on broker switch**: `MultiTrader` now accepts `initial_realized_loss` and `loss_persist_fn`; `core.get_multi_trader()` loads today's cumulative loss from `daily_loss.json` on construction and persists it on every realized loss — switching brokers or reloading the page no longer resets the counter
- **IBKR gateway crash recovery**: IBKR broker block now detects a dead gateway process (`gw_start_attempted` set but `gw.is_running()` False) and clears both attempt flags so auto-start retries on the next rerun; also detects dropped IB sessions (port still open, IB disconnected) and clears `ib_connect_attempted` to allow one reconnect

---

## [0.28.0] — 2026-03-30

### Changed
- README: added IBKR workflow description (step-by-step setup flow, mobile auth note, scanner speed caveat)
- README: moved Backtest into a new dedicated **Testing** section alongside Scanner Test mode; removed both from their previous locations

---

## [0.27.0] — 2026-03-30

### Changed
- Replace deprecated `use_container_width` with `width='stretch'` in Portfolio page dataframes and charts (Streamlit deprecation)

---

## [0.26.0] — 2026-03-30

### Added
- **IBKR: full page parity** — Scanner, AutoTrader, Portfolio Mode, and Backtest are now available when IBKR is selected as the broker
- **IBKR broker callables** — `ibkr_get_price` (live tick), `ibkr_buy/sell` (market orders), `ibkr_get_bars` (30-day daily history via `reqHistoricalData`)
- **`_IBKRDataClient` shim** — minimal implementation of the Alpaca data client interface so Scanner and Backtest work with IBKR historical data (note: IBKR scans one symbol at a time — expect slower scanning than Alpaca)
- **Broker-aware position monitoring** — Portfolio Mode "Monitor existing positions" panel now fetches open positions from IBKR when that broker is active
- **Broker switch reset** — switching between Alpaca and IBKR clears the MultiTrader and PortfolioManager session state so callables are always correct for the active broker

---

## [0.25.1] — 2026-03-30

### Fixed
- Scanner: chunk fetches are now parallelised with `ThreadPoolExecutor(max_workers=4)` instead of sequential — ~4× faster for large universes; default `chunk_size` raised from 100 → 250 (fewer round-trips for ~720-symbol All universe)

---

## [0.25.0] — 2026-03-30

### Added
- **Portfolio: combined positions view** — Open Positions section now fetches from all configured accounts: Alpaca Paper, Alpaca Live (if keys set), and IBKR (if Gateway connected); each shown in a labeled sub-section with its own table and P&L chart
- **AutoTrader: qty sizing outside form** — Qty mode radio and inputs moved outside `st.form` so switching between Shares / Dollar amount / Risk % updates the inputs immediately without requiring form submission; Risk % mode adds a standalone "Est. stop %" input

### Fixed
- Qty mode: switching back to "Shares" now correctly shows the shares input (was stuck on previous mode's inputs inside the form)

### Changed
- CLAUDE.md: docs update (README + CHANGELOG) required on every version bump

---

## [0.24.0] — 2026-03-30

### Added
- **Sidebar: 🧪 Test mode (historic data)** toggle
- Scanner: "Historical date" / "As-of date" moved from scanner page to sidebar toggle

### Changed
- Scanner: "Top N results" renamed to "How many top candidates to return"
- Sidebar: active account/mode shown below version heading
- Removed `Portfolio Dashboard` page title from Alpaca and IBKR pages

### Fixed
- `StreamlitValueBelowMinError` when `PM_SLOT_DOLLAR=0` written to `.env`

---

## [0.23.6] — 2026-03-30

### Added
- **Sidebar: 🧪 Test mode (historic data)** toggle — enables as-of-date scanning from the sidebar; date picker appears inline when on; caption explains the behaviour

### Changed
- Scanner: "Top N results" input renamed to "How many top candidates to return"
- Scanner: "Historical date" checkbox and "As-of date" picker removed from the scanner page; replaced by the sidebar Test mode toggle

---

## [0.23.5] — 2026-03-30

### Changed
- Removed `st.title("Portfolio Dashboard …")` heading from both the Alpaca and IBKR portfolio pages
- Sidebar: active account/mode (e.g. "Alpaca · Paper account") shown directly below the version heading; live warning moved to a caption

---

## [0.23.4] — 2026-03-30

### Fixed
- `StreamlitValueBelowMinError` crash on Portfolio and Scanner pages when `PM_SLOT_DOLLAR=0` was written to `.env` by the "% of equity" sizing mode; both `$ per slot` and `$ per position` inputs now clamp the loaded value to ≥ 100

---

## [0.23.3] — 2026-03-30

### Added
- **Scanner: INTL (full) universe** (~125 symbols) — superset of INTL (small) with additional European, Asian, Canadian, and Australian ADRs plus extended country ETFs
- Scanner market selector now has four options: 🇺🇸 US (~593), 🌍 INTL (small) (~62), 🌍 INTL (full) (~125), 🌐 All (~718)
- `UNIVERSE_INTL_FULL` exported from `scanner.py`; `UNIVERSE` (All) updated to `UNIVERSE_US + UNIVERSE_INTL_FULL`

### Fixed
- Scanner expander / checkbox labels now reflect the selected market choice (was always showing "full universe")

---

## [0.23.2] — 2026-03-30

### Fixed
- Settings API key validation: `acct.id` from Alpaca SDK is a `UUID` object — cast to `str` before slicing to fix `'UUID' object is not subscriptable`

---

## [0.23.1] — 2026-03-30

### Added
- Settings page: Alpaca API keys validated immediately on save; ✅/❌ feedback messages persist across `st.rerun()` via `session_state`
- Installer `--update`: fast path deploys from local dev tree when the local version is newer than the installed version, avoiding a stale GitHub clone
- CLAUDE.md: versioning rules documented (patch/minor/major thresholds and prompts)

---

## [0.23.0] — 2026-03-30

### Added
- `AutoTrader.attach(symbol, qty, entry_price, config)` — monitor an existing position without placing a buy order; useful after app restart
- `MultiTrader.attach(...)` — same in the multi-position context; wires `_on_close` for daily loss tracking

### Fixed
- `PortfolioManager`: on slot-sizing error, `_claimed.discard(sym)` now called so the symbol is not permanently blocked
- `AutoTrader._do_market_entry`: `self.status.qty` now set from `total_filled`

---

## [0.22.0] — 2026-03-30

### Added
- **Scanner: 🇺🇸 / 🌍 / 🌐 Market selector** — radio button on the Scanner page to choose US (~500 symbols), International (foreign ADRs + country ETFs), or All (combined); scanner symbol list and multiselect update accordingly
- `scanner.py`: `UNIVERSE_US` (US equities + US-focused ETFs) and `UNIVERSE_INTL` (foreign ADRs: ASML, TSM, STM, SHOP, MELI, SE, GRAB, BIDU, JD, PDD, AZN, NVO, SNY, GSK, BNTX, TM, HMC, STLA, RACE, NIO, XPEV, LI, ONON, BIRK, GOOS, BUD, BTI, BP, SHEL, SAN, HSBC, RY, TD, BHP, RIO, VALE, SAP, SONY, CNI, CP + all international ETFs); `UNIVERSE` remains combined for backward compat
- **Portfolio Mode: 📥 Monitor existing positions** — expander at the bottom of Portfolio Mode lists account positions not yet tracked by AutoTrader; *Start monitoring all* attaches a trailing-stop monitor to each without placing any buy orders (useful after app restart)
- `AutoTrader.attach(symbol, qty, entry_price, config)` — starts monitoring an existing position; skips the entry phase, begins watching from `entry_price`
- `MultiTrader.attach(...)` — same as above in the multi-position context

---

## [0.21.0] — 2026-03-30

### Changed
- Sidebar nav reordered: Scanner is now first (entry point), followed by Portfolio Mode, AutoTrader, Portfolio, Backtest, Settings, Help
- Scanner caption updated to say "Start Here" with a one-line summary of the quick path

### Added
- Sidebar: persistent 3-step "Suggested workflow" guide
- AutoTrader: empty-state hint guides to Scanner when no positions; adapts if scan results are already available
- Portfolio Mode: 3-step "how to start" hint shown when not running
- Portfolio: "no open positions" hint links to Scanner
- Help Quick Start: rewritten with three distinct workflows (A: fully automated, B: scanner + quick invest, C: full manual)

---

## [0.20.1] — 2026-03-30

### Added
- Scanner: when a completed scan returns zero candidates, show "📉 Not a good time to invest. Stock exchanges are not doing well right now — no candidates passed the quality filters."

---

## [0.20.0] — 2026-03-30

### Added
- **Scanner: ⚡ Quick Invest panel** — set $ per position + trailing stop % + N, click *Invest Now* to open positions immediately without going through the AutoTrader form; uses selected rows or falls back to top N by score
- *Configure & Queue* button replaces the old "Send to AutoTrader" for the manual-review flow

### Fixed
- **`PortfolioManager` parallel duplicate picks** — `_next_candidate()` had no atomicity between selection and open; all threads in *Start All* could grab the same symbol. Fixed with `_claimed` set: symbol is reserved atomically on selection and released once `_multi.start()` succeeds or fails.
- **`AutoTrader.start()` ENTERING guard** — only blocked on `WATCHING`; a second call during `ENTERING` would start a duplicate monitor thread. Now raises on both `ENTERING` and `WATCHING`.
- **`at_current_symbol` empty-string fallback** — `dict.get(key, default)` doesn't treat empty string as missing; swapped to `or` so an empty stored symbol correctly falls back to `AT_SYMBOL` env.
- **Duplicate broker function definitions** — `alpaca_get_price`, `alpaca_buy`, `alpaca_sell`, `alpaca_get_bars` were defined three times (AutoTrader, Portfolio Mode, Scanner). Moved to top-level Alpaca section; all pages now share one definition.

### Docs
- README: rewrote AutoTrader and Portfolio Mode sections — clearer explanation of what each does, typical flows, and when to use Start All vs Sequential

---

## [0.19.0] — 2026-03-30

### Added
- Portfolio Mode: **Start All** button opens all slots simultaneously in parallel threads
- Portfolio Mode: **Start Sequential** (renamed from Start) opens slots one at a time and replaces each on close — existing behaviour
- Portfolio Mode: **Fixed $ per slot** sizing mode — specify e.g. `$3000` per position instead of % of equity; total exposure hint shown in UI
- `PortfolioManager`: `slot_dollar` parameter; `start_all()` method; `_fill_empty_slots_parallel()` internal
- `PM_SLOT_DOLLAR` env key persisted to `.env` via Settings

---

## [0.18.1] — 2026-03-30

### Fixed
- Scanner → AutoTrader symbol prefill lost on page rerun: `at_prefill_list` was popped on the first render and every subsequent rerender fell back to `AT_SYMBOL` (AAPL). Symbol is now stored in `at_current_symbol` which survives reruns; advancing through the queue on position start no longer requires a round-trip through `at_prefill_list`.

---

## [0.18.0] — 2026-03-30

### Added
- Scanner page: filter controls are now editable inline — min price, ADV, RSI range, volume multiplier, SMA20 tolerance, and min 5d return can all be adjusted without leaving the page
- "Save as defaults" button in the Filters expander persists current values to `.env` / Settings

### Removed
- Static "Active filters" read-only table replaced by the live controls above

---

## [0.17.0] — 2026-03-30

### Added
- Settings page: Portfolio Mode defaults (`PM_TARGET_SLOTS`, `PM_SLOT_PCT`) persisted to `.env`

### Fixed
- Concurrent rescan protection in `PortfolioManager._rescan()` via `_scan_lock`: late callers wait and reuse results instead of triggering duplicate API requests
- AutoTrader page auto-refresh now triggers for `ENTERING` state as well as `WATCHING`
- `_fill_empty_slots()` loops `open_slot_count()` times instead of `target_slots` to respect pre-existing positions on restart
- `MultiTrader.daily_pnl()` renamed to `unrealized_pnl()` (now includes `ENTERING` positions); deprecated alias kept for compatibility
- Price feed falls back to last trade price when ask/bid quote returns 0 (after-hours / illiquid markets)
- Session objects (`multitrader`, `portfolio_manager`) invalidated when Paper/Live mode changes to prevent stale client reuse
- Installer `create_env_file()` now prompts for Alpaca Live keys interactively (default No)

### Docs
- CHANGELOG filled in for all versions v0.8.0–v0.16.0 (previously empty)
- README: added `PM_TARGET_SLOTS` / `PM_SLOT_PCT` to `.env` reference block

---

## [0.16.0] — 2026-03-30

### Added
- **Portfolio Mode** — auto-maintain up to N concurrent scanner-driven positions, each sized at a configurable % of account equity; on position close the manager rescans (if stale) and immediately opens the next highest-scoring scanner candidate
- `portfolio.py` — `PortfolioManager` class wrapping `MultiTrader`; concurrent-rescan protection via `_scan_lock`; `on_close` callback chain triggers automatic slot refill
- **Paper / Live trading toggle** — red badge in sidebar when live mode is active; requires separate live API keys (`ALPACA_LIVE_API_KEY`, `ALPACA_LIVE_SECRET_KEY`)
- Live mode confirmation dialog: "You're going to trade with your real money now!" must be acknowledged before trading begins
- `core.py` — framework-agnostic credential, client, and session management; `get_portfolio_manager()` factory
- Settings page: Alpaca Live key fields; Portfolio Mode defaults (`PM_TARGET_SLOTS`, `PM_SLOT_PCT`)
- Help page with usage guide

### Fixed
- Session objects (`multitrader`, `portfolio_manager`) invalidated when Paper/Live mode changes, preventing stale client reuse
- Price feed falls back to last trade price when ask/bid quote returns 0 (after-hours / illiquid markets)
- AutoTrader page auto-refresh now triggers for `ENTERING` state as well as `WATCHING`
- `_fill_empty_slots()` loops `open_slot_count()` times (not `target_slots`) to respect pre-existing positions on restart
- `MultiTrader.daily_pnl()` renamed to `unrealized_pnl()` and now includes `ENTERING` positions; deprecated alias kept
- `import os` missing in `goldvreneli.py` (crashed Settings and Backtest pages)
- P&L wrong after partial take-profit: `realized_pnl` accumulator added to `AutoTraderStatus`
- Shared `TraderConfig` mutation: `AutoTrader.start()` now shallow-copies config via `dataclasses.replace()`
- Installer `--update` failed with "Source file not found: app.py" — now reloads `PROD_FILES` from newly cloned script before deploying
- Installer `create_env_file()` now prompts for Alpaca Live keys interactively (default No)

---

## [0.15.0] — 2026-03-29

### Added
- Rename `app.py` → `goldvreneli.py`; all references updated
- UX improvements: scan timestamp display, backtest defaults, IBKR realized P&L, portfolio chart memory
- Multi-symbol send to AutoTrader
- Dollar-amount and risk-% qty sizing modes

---

## [0.14.0] — 2026-03-28

### Added
- Batch API fetch for scanner (single request per ~100 symbols vs one per symbol) — 5–10× faster scans
- Default watchlist used as pre-selected symbols in Scanner page

---

## [0.13.0] — 2026-03-28

### Added
- Scanner: multi-select symbols; run scan on selected subset instead of full universe
- Settings: configurable scanner filter thresholds (RSI range, price, ADV, volume multiplier, SMA tolerance, 5d return)

### Fixed
- Default AutoTrader symbol blank on first load instead of hard-coded AAPL

---

## [0.12.0] — 2026-03-28

### Added
- Improved scanner scoring and sidebar navigation
- Pages reorganised into cleaner sidebar menu

---

## [0.11.1] — 2026-03-28

### Fixed
- Nested f-string syntax error in backtest session label
- Suppress Streamlit deprecation warnings

---

## [0.11.0] — 2026-03-28

### Added
- Scanner universe expanded from ~60 to ~600 liquid US equities and ETFs
- Scanner historical mode: as-of date picker for replay/research

---

## [0.10.0] — 2026-03-28

### Added
- Backtest tab: replay historical bars through AutoTrader logic; synthetic price feed for unit testing
- Persistent fills log across backtest sessions
- Configurable time window for replay backtest

---

## [0.9.0] — 2026-03-28

### Fixed
- `--update` clone path: prevent downgrade, skip IB Gateway reinstall if not installed
- Default IBKR Gateway path corrected to `~/goldvreneli/Jts/ibgateway`

---

## [0.8.0] — 2026-03-28

### Fixed
- Installer `--update` now tries `git pull` first and falls back to clone
- Post-update restart instructions show correct venv activate path

---

## [0.7.1] — 2026-03-28

### Fixed
- Installer renamed `install.sh` → `goldvreneli-install.sh`
- README version badge and `bump.sh` kept in sync automatically

---

## [0.7.0] — 2026-03-28

### Added
- AutoTrader: ATR-based trailing stop (N × ATR(14) dollars, adapts to volatility)
- AutoTrader: take-profit target (sell configurable fraction when profit hits %)
- AutoTrader: breakeven stop (raise stop floor to entry once up X %)
- AutoTrader: time stop (exit after N minutes)
- AutoTrader: limit entry mode (wait for price ≤ target within timeout)
- AutoTrader: scale-in entry mode (buy in N tranches at configurable intervals)
- `size_from_risk()` helper to compute qty from account equity and risk %
- `MultiTrader`: manage multiple concurrent positions keyed by symbol
- `MultiTrader`: daily loss limit (halt new trades when realized losses exceed threshold)
- UI: positions table with per-symbol drawdown bars, stop buttons, P&L, ATR/BE/TP indicators
- UI: risk-based position sizing calculator in the AutoTrader form
- UI: daily P&L and realized-losses summary metrics
- Settings: Daily Loss Limit field (`AT_DAILY_LOSS_LIMIT`)

---

## [0.6.0] — 2026-03-28

### Added
- Scanner results are now selectable; a "Send to AutoTrader" button pre-fills the symbol and navigates automatically

---

## [0.5.1] — 2026-03-28

### Fixed
- Minor stability fixes

---

## [0.5.0] — 2026-03-28

### Added
- Scanner composite scoring: relative strength vs SPY, momentum (1d/5d/10d/20d), RSI quality, MACD histogram, trend consistency — results sorted best-first

---

## [0.4.0] — 2026-03-28

### Added
- `autotrader.py` — trailing-stop AutoTrader: buys on start, tracks peak price, sells when drawdown exceeds configurable threshold (default 0.5%)
- `scanner.py` — position scanner across ~60 liquid US stocks/ETFs; proposes top N candidates sorted by composite score
- AutoTrader tab: configurable symbol, qty, trailing stop %, poll interval; live status with drawdown bar and activity log
- Scanner tab: run-on-demand scan, results table, 5-day return bar chart
- `pandas-ta` dependency for technical indicators (SMA, RSI, ATR, MACD)

### Changed
- Alpaca dashboard restructured into three tabs: Portfolio / AutoTrader / Scanner

---

## [0.3.0] — 2026-03-28

### Added
- `goldvreneli-install.sh` — one-command installer for system deps, IB Gateway, IBC, Xvfb, and `.env` template
- `--skip-gateway` and `--skip-ibc` flags for the installer
- `version.py` — single source of truth for semantic version
- `bump.sh` — version bump script (major/minor/patch), updates CHANGELOG and creates git tag
- Version shown in browser tab title and sidebar
- `README.md` and `CHANGELOG.md`

---

## [0.2.0] — 2026-03-28

### Added
- IBKR broker support via `ib_async`
- `gateway_manager.py` — manages IB Gateway lifecycle using IBC + Xvfb subprocesses (no Docker)
- Gateway control panel in the Streamlit UI (Start / Connect / Disconnect / Stop)
- Live status indicators: process state, API port, IB session
- `python-dotenv` support — credentials loaded from `.env`
- Paper/live mode selector for IBKR
- IBKR account summary, positions, order placement, open orders

### Changed
- Broker selector in sidebar — switch between Alpaca Paper and IBKR

---

## [0.1.0] — 2026-03-28

### Added
- Streamlit trading dashboard for Alpaca paper trading
- Account overview: portfolio value, cash, buying power, equity
- Open positions table with unrealized P&L bar chart
- Candlestick price chart (1D / 1W / 1M / 3M) via Alpaca market data
- Order form: market and limit orders, buy/sell
- Open orders table with cancel all
- Python venv with `alpaca-py`, `streamlit`, `plotly`
- `requirements.txt` and `.gitignore`
