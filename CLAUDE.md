# Goldvreneli
Streamlit trading dashboard. `streamlit run goldvreneli.py`
Use `qmd search "query"` before reading files.

## Files
`goldvreneli.py` entry point (sidebar + dispatch) · `core.py` env/clients · `autotrader.py` AutoTrader/MultiTrader · `portfolio.py` PortfolioManager · `scanner.py` scan/ScanFilters/UNIVERSE_US/INTL · `replay.py` replay feeds (used by Test Mode) · `activity_tracker.py` log renderer · `gateway_manager.py` IB Gateway/IBC · `ibkr_data.py` IBKRDataClient · `version.py`

### Page modules (`pages/`)
`autotrader_page.py` · `scanner_page.py` · `portfolio_page.py` · `portfolio_mode_page.py` · `test_mode_page.py` · `settings_page.py` · `help_page.py`
Each exports a single `render(...)` function. Pages must not import each other.

### Tests (`tests/`)
`test_autotrader.py` · `test_scanner.py`
Run with `venv/bin/python -m pytest tests/ -v`

## Key API
- `AutoTrader.start(sym,qty,cfg)` buy+monitor · `.attach(sym,qty,entry,cfg)` monitor only · `.stop()` halt
- States: IDLE→ENTERING→WATCHING→SOLD/STOPPED/ERROR
- `MultiTrader` — dict of AutoTraders, optional daily loss limit
- `PortfolioManager.start()` sequential · `.start_all()` parallel · refills slots on close
- `TraderConfig` — stop(PCT/ATR), entry(MARKET/LIMIT/SCALE), take-profit, breakeven, time-stop
- Broker callables injected per page: `get_price_fn/buy_fn/sell_fn/get_bars_fn/get_equity_fn` — both Alpaca and IBKR support all pages
- IBKR caveat: ETF ATR stops may fall back to PCT stops (no intraday high/low bars)
- `st.session_state.scan_results` — scan results persist across reruns

## Branching
Always develop on the `dev` branch. Never commit directly to `main`. After a release, fast-forward `dev` to `main` so all branches stay in sync.

## Versioning
Before every commit, bump `version.py`:
- **Patch** (0.x.Y) — bug fixes, small UI tweaks, copy changes (default)
- **Minor** (0.X.0) — new features, new pages, significant behaviour changes — ask user first
- **Major** (X.0.0) — breaking changes or full rewrites — ask user first

On every version bump, also update `README.md` and `CHANGELOG.md`:
- `README.md` — update the version badge and any feature/page descriptions affected by the changes
- `CHANGELOG.md` — add a new `## [x.y.z] — YYYY-MM-DD` entry describing what changed

## Env vars
`ALPACA_PAPER/LIVE_API_KEY/SECRET_KEY` · `IBKR_USERNAME/PASSWORD/MODE` · `IBC_PATH` · `GATEWAY_PATH`
`AT_SYMBOL/THRESHOLD/POLL/DAILY_LOSS_LIMIT` · `SCAN_TOP_N/RSI_LO/RSI_HI/VOL_MULT/MIN_PRICE/MIN_ADV_M/SMA20_TOL/MIN_RET5D/WATCHLIST`
`PM_TARGET_SLOTS/SLOT_PCT/SLOT_DOLLAR`
