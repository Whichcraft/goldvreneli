# Goldvreneli
Streamlit trading dashboard. `streamlit run goldvreneli.py`
Use `qmd search "query"` before reading files.

## Files
`goldvreneli.py` UI · `core.py` env/clients · `autotrader.py` AutoTrader/MultiTrader · `portfolio.py` PortfolioManager · `scanner.py` scan/ScanFilters/UNIVERSE_US/INTL · `replay.py` backtest · `gateway_manager.py` IB Gateway/IBC · `version.py`

## Key API
- `AutoTrader.start(sym,qty,cfg)` buy+monitor · `.attach(sym,qty,entry,cfg)` monitor only · `.stop()` halt
- States: IDLE→ENTERING→WATCHING→SOLD/STOPPED/ERROR
- `MultiTrader` — dict of AutoTraders, optional daily loss limit
- `PortfolioManager.start()` sequential · `.start_all()` parallel · refills slots on close
- `TraderConfig` — stop(PCT/ATR), entry(MARKET/LIMIT/SCALE), take-profit, breakeven, time-stop
- Alpaca fns shared across pages: `alpaca_get_price/buy/sell/get_bars`
- `st.session_state.scan_results` — scan results persist across reruns
- Broker scope: IBKR = Portfolio/Settings/Help only; Alpaca = all pages

## Versioning
Before every commit, bump `version.py`:
- **Patch** (0.x.Y) — bug fixes, small UI tweaks, copy changes (default)
- **Minor** (0.X.0) — new features, new pages, significant behaviour changes — ask user first
- **Major** (X.0.0) — breaking changes or full rewrites — ask user first

## Env vars
`ALPACA_PAPER/LIVE_API_KEY/SECRET_KEY` · `IBKR_USERNAME/PASSWORD/MODE` · `IBC_PATH` · `GATEWAY_PATH`
`AT_SYMBOL/THRESHOLD/POLL/DAILY_LOSS_LIMIT` · `SCAN_TOP_N/RSI_LO/RSI_HI/VOL_MULT/MIN_PRICE/MIN_ADV_M/SMA20_TOL/MIN_RET5D/WATCHLIST`
`PM_TARGET_SLOTS/SLOT_PCT/SLOT_DOLLAR`
