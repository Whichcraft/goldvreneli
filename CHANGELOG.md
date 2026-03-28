# Changelog

All notable changes to this project will be documented here.

---

## [Unreleased]

---

## [0.10.0] — 2026-03-28

---

## [0.9.0] — 2026-03-28

---

## [0.8.0] — 2026-03-28

---

## [0.7.1] — 2026-03-28

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
- Scanner results are now selectable (single-row); a "Send to AutoTrader" button pre-fills the AutoTrader symbol and navigates to the AutoTrader page automatically.

---

## [0.5.1] — 2026-03-28

---

## [0.5.0] — 2026-03-28

---

## [0.4.0] — 2026-03-28

### Added
- `autotrader.py` — trailing-stop AutoTrader: buys on start, tracks peak price, sells when drawdown exceeds configurable threshold (default 0.5%)
- `scanner.py` — position scanner across ~60 liquid US stocks/ETFs using SMA, RSI, volume, momentum, and MACD filters; proposes top N candidates
- **AutoTrader tab** in Alpaca dashboard: configurable symbol, qty, trailing stop %, poll interval; live status panel with drawdown progress bar and activity log
- **Scanner tab** in Alpaca dashboard: run-on-demand scan, results table, 5-day return bar chart
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
- Gateway log viewer (expander)
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
