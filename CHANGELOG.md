# Changelog

All notable changes to this project will be documented here.

---

## [Unreleased]

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
