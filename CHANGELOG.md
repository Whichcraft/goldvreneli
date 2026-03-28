# Changelog

All notable changes to this project will be documented here.

---

## [Unreleased]

---

## [0.3.0] — 2026-03-28

### Added
- `install.sh` — one-command installer for system deps, IB Gateway, IBC, Xvfb, and `.env` template
- `--skip-gateway` and `--skip-ibc` flags for the installer
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
