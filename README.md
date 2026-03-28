# Goldvreneli Trading Dashboard

A Streamlit-based trading dashboard supporting **Alpaca Paper Trading** and **Interactive Brokers (IBKR)** via IB Gateway.

---

## Features

- Alpaca paper trading — portfolio, positions, price charts, order placement
- IBKR live/paper trading — via IB Gateway managed directly from the app
- IB Gateway auto-start using IBC + Xvfb (no Docker required)
- Candlestick price charts (Plotly)
- Place market and limit orders
- Real-time account summary and open positions
- Cancel all orders with one click

---

## Requirements

- Linux (Debian/Ubuntu, Fedora, or Arch)
- Python 3.10+
- Internet connection (for first-time install)
- IBKR account with paper trading enabled (for IBKR mode)
- Alpaca account (for Alpaca mode)

---

## Installation

```bash
git clone git@github.com:Whichcraft/goldvreneli.git
cd goldvreneli
./install.sh
```

The installer sets up:
- Python virtual environment + all dependencies
- IB Gateway (stable offline installer)
- IBC (IB Controller for headless login)
- Xvfb (virtual display)
- `.env` template

### Flags

```bash
./install.sh --skip-gateway   # skip IB Gateway install
./install.sh --skip-ibc       # skip IBC install
./install.sh --help
```

---

## Configuration

Fill in your credentials in `.env` after install:

```env
# Alpaca Paper Trading
ALPACA_PAPER_API_KEY=
ALPACA_PAPER_SECRET_KEY=

# IBKR
IBKR_USERNAME=
IBKR_PASSWORD=

# Paths (auto-detected by installer)
IBC_PATH=~/ibc
GATEWAY_PATH=~/Jts/ibgateway
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

## IBKR Setup Notes

1. Select **IBKR** in the sidebar and enter credentials
2. Click **Start Gateway** — IB Gateway launches headlessly via IBC + Xvfb
3. Click **Connect** once the API port is open (30–90 seconds)
4. Use port `4002` for paper, `4001` for live

### Ports

| Mode  | App        | Port |
|-------|------------|------|
| Paper | TWS        | 7497 |
| Paper | IB Gateway | 4002 |
| Live  | TWS        | 7496 |
| Live  | IB Gateway | 4001 |

### Two-Factor Authentication

IBC supports IBKR Mobile soft token (push notification). Hardware tokens require one manual login per day at the scheduled `AUTO_RESTART_TIME` (default: 11:59 PM).

---

## Project Structure

```
goldvreneli/
├── app.py              # Streamlit dashboard
├── gateway_manager.py  # IB Gateway lifecycle (IBC + Xvfb)
├── install.sh          # One-command installer
├── requirements.txt    # Python dependencies
├── .env                # Credentials (gitignored)
└── venv/               # Python virtual environment (gitignored)
```

---

## Tech Stack

| Component | Library |
|-----------|---------|
| Dashboard | [Streamlit](https://streamlit.io) |
| Charts    | [Plotly](https://plotly.com) |
| IBKR API  | [ib_async](https://github.com/ib-api-reloaded/ib_async) |
| Alpaca API| [alpaca-py](https://github.com/alpacahq/alpaca-py) |
| Gateway automation | [IBC](https://github.com/IbcAlpha/IBC) |
