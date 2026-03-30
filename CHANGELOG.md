# Changelog

All notable changes to this project will be documented here.

---

## [Unreleased]

---

## [0.18.0] — 2026-03-30

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
