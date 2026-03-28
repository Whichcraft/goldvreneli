# Goldvreneli Trading Dashboard

![Version](https://img.shields.io/badge/version-0.10.0-blue)

A Streamlit-based trading dashboard supporting **Alpaca Paper Trading** and **Interactive Brokers (IBKR)** via IB Gateway, with automated trading and position scanning.

---

## Features

- **Alpaca paper trading** — portfolio, positions, candlestick charts, order placement
- **IBKR live/paper trading** — IB Gateway managed directly from the app (no Docker)
- **AutoTrader** — trailing-stop position manager: holds as long as price rises, sells when it drops below a configurable threshold
- **Position Scanner** — scans ~60 liquid US stocks/ETFs with technical filters and proposes the top 10 candidates
- IB Gateway auto-start via IBC + Xvfb
- Market and limit orders, cancel all
- Semantic versioning + changelog

---

## Requirements

- Linux (Debian/Ubuntu, Fedora, or Arch)
- Python 3.10+
- Internet connection (first-time install)
- Alpaca account (free, no funding needed for paper trading)
- IBKR account with paper trading enabled (for IBKR mode)

---

## Installation

```bash
git clone git@github.com:Whichcraft/goldvreneli.git
cd goldvreneli
./goldvreneli-install.sh
```

The installer sets up:
- Python virtual environment + all dependencies
- IB Gateway (stable offline installer)
- IBC (IB Controller for headless auto-login)
- Xvfb (virtual display)
- `.env` credentials template

### Flags

```bash
./goldvreneli-install.sh --skip-gateway   # skip IB Gateway install
./goldvreneli-install.sh --skip-ibc       # skip IBC install
./goldvreneli-install.sh --help
```

---

## Configuration

Fill in `.env` after install:

```env
# Alpaca Paper Trading
ALPACA_PAPER_API_KEY=
ALPACA_PAPER_SECRET_KEY=

# IBKR
IBKR_USERNAME=
IBKR_PASSWORD=

# Paths (auto-detected by installer)
IBC_PATH=~/goldvreneli/ibc
GATEWAY_PATH=~/goldvreneli/Jts/ibgateway
```

Get Alpaca paper API keys at [alpaca.markets](https://alpaca.markets) → Paper Trading → API Keys.

---

## Running

```bash
source venv/bin/activate
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Tabs (Alpaca Mode)

### Portfolio
- Account overview: portfolio value, cash, buying power, equity
- Open positions table + unrealized P&L bar chart
- Candlestick price chart (1D / 1W / 1M / 3M)
- Place market or limit orders
- Open orders table with cancel all

### AutoTrader
Trailing-stop automated position manager.

| Setting | Default | Description |
|---------|---------|-------------|
| Symbol | AAPL | Stock to trade |
| Qty | 1 | Number of shares |
| Trailing Stop % | 0.5% | Sell when price drops this % below peak |
| Poll interval | 5s | Price check frequency |

- Buys on start, tracks peak price in real time
- Sells automatically when drawdown ≥ threshold
- Live status: entry, peak, current price, drawdown progress bar, P&L
- Full activity log (BUY / PEAK / SELL / STOP / ERROR)

### Scanner
Scans ~60 liquid US stocks and ETFs. Filters applied:

| Filter | Condition |
|--------|-----------|
| Trend | Price > SMA20 and SMA50 |
| RSI(14) | 40–65 |
| Volume | > 1.5× 20-day average |
| Liquidity | Price > $5, ADV > $5M |
| Momentum | 5-day return > 0% |

Returns top N candidates ranked by composite score with a 5-day return bar chart.

---

## IBKR Setup

1. Select **IBKR** in the sidebar and enter credentials
2. Click **Start Gateway** — launches headlessly via IBC + Xvfb (30–90s startup)
3. Click **Connect** once the API port is open
4. Use port `4002` for paper, `4001` for live

### Ports

| Mode  | App        | Port |
|-------|------------|------|
| Paper | IB Gateway | 4002 |
| Paper | TWS        | 7497 |
| Live  | IB Gateway | 4001 |
| Live  | TWS        | 7496 |

### Two-Factor Authentication

IBC supports IBKR Mobile soft token (push notification — approve once at startup). Hardware tokens require one manual login per day at `AUTO_RESTART_TIME` (default: 11:59 PM).

---

## Versioning

```bash
./bump.sh patch   # 0.3.0 → 0.3.1
./bump.sh minor   # 0.3.0 → 0.4.0
./bump.sh major   # 0.3.0 → 1.0.0
git push && git push --tags
```

---

## Project Structure

```
goldvreneli/
├── app.py              # Streamlit dashboard (Portfolio, AutoTrader, Scanner)
├── autotrader.py       # Trailing-stop AutoTrader logic
├── scanner.py          # Technical position scanner
├── gateway_manager.py  # IB Gateway lifecycle (IBC + Xvfb)
├── version.py          # Single version source of truth
├── bump.sh             # Version bump script
├── goldvreneli-install.sh          # One-command installer
├── requirements.txt    # Python dependencies
├── .env                # Credentials (gitignored)
└── venv/               # Python virtual environment (gitignored)
```

---

## Tech Stack

| Component | Library |
|-----------|---------|
| Dashboard | [Streamlit](https://streamlit.io) |
| Charts | [Plotly](https://plotly.com) |
| Technical indicators | [pandas-ta](https://github.com/twopirllc/pandas-ta) |
| Alpaca API | [alpaca-py](https://github.com/alpacahq/alpaca-py) |
| IBKR API | [ib_async](https://github.com/ib-api-reloaded/ib_async) |
| Gateway automation | [IBC](https://github.com/IbcAlpha/IBC) |
