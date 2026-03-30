# Goldvreneli Trading Dashboard

![Version](https://img.shields.io/badge/version-0.18.1-blue)

A Streamlit-based trading dashboard supporting **Alpaca Paper and Live Trading** and **Interactive Brokers (IBKR)** via IB Gateway, with automated trailing-stop trading, technical scanning, portfolio automation, and offline backtesting.

---

## Features

- **Alpaca paper and live trading** — toggle between modes in the sidebar; live mode requires confirmation and shows a red warning banner
- **IBKR live/paper trading** — IB Gateway managed directly from the app (no Docker)
- **AutoTrader** — trailing-stop position manager: holds as long as price rises, sells when it drops below a configurable threshold; supports PCT and ATR stops, limit/scale entry, take-profit, breakeven, time stop, and multi-symbol queuing
- **Portfolio Mode** — fully automated: maintains up to N concurrent positions from scanner picks, each sized at a fixed % of equity; on exit, rescans and opens the next best candidate
- **Position Scanner** — scans ~600 liquid US stocks, ETFs, and ADRs with technical filters (RSI, SMA, volume, relative strength vs SPY) and proposes top candidates; historical mode supported
- **Backtest** — replay real Alpaca 1-minute bars or synthetic random-walk data to test AutoTrader settings offline
- IB Gateway auto-start via IBC + Xvfb (headless, no manual login on startup)
- Risk-% and dollar-amount position sizing
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

### Updating

```bash
./goldvreneli-install.sh --update
```

---

## Configuration

Fill in `.env` after install, or use the **⚙️ Settings** page in the app:

```env
# Alpaca Paper Trading
ALPACA_PAPER_API_KEY=
ALPACA_PAPER_SECRET_KEY=

# Alpaca Live Trading (required only for live mode)
ALPACA_LIVE_API_KEY=
ALPACA_LIVE_SECRET_KEY=

# IBKR
IBKR_USERNAME=
IBKR_PASSWORD=

# Paths (auto-detected by installer)
IBC_PATH=~/goldvreneli/ibc
GATEWAY_PATH=~/goldvreneli/Jts/ibgateway

# AutoTrader defaults
AT_SYMBOL=
AT_THRESHOLD=0.5
AT_POLL=5
AT_DAILY_LOSS_LIMIT=0

# Scanner defaults
SCAN_TOP_N=10
SCAN_MIN_PRICE=5.0
SCAN_MIN_ADV_M=5.0
SCAN_RSI_LO=35
SCAN_RSI_HI=72
SCAN_VOL_MULT=1.0
SCAN_SMA20_TOL=3.0
SCAN_MIN_RET5D=-1.0
SCAN_WATCHLIST=

# Portfolio Mode defaults
PM_TARGET_SLOTS=10
PM_SLOT_PCT=10.0
```

Get Alpaca paper API keys at [alpaca.markets](https://alpaca.markets) → Paper Trading → API Keys.
Get live API keys at alpaca.markets → Live Trading → API Keys (funded account required).

---

## Running

```bash
source venv/bin/activate
streamlit run goldvreneli.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Alpaca Paper vs Live

The sidebar shows an **Alpaca** broker selector with a **Live Trading** toggle.

| Mode | Keys used | Orders |
|------|-----------|--------|
| Paper (default) | `ALPACA_PAPER_*` | Simulated — no real money |
| Live | `ALPACA_LIVE_*` | **Real orders on your funded account** |

Switching to Live requires a confirmation step ("You're going to trade with your real money now!") and displays a persistent red warning banner. If live API keys are not yet configured, an inline credential form appears before proceeding.

---

## Pages (Alpaca Mode)

### 💼 Portfolio
- Account overview: portfolio value, cash, buying power, equity, day P&L with delta %
- Open positions table + unrealized P&L bar chart
- Candlestick price chart (1D / 1W / 1M / 3M) — symbol remembered across page switches
- Place market or limit orders
- Open orders table with cancel all

### 🤖 AutoTrader

Trailing-stop automated position manager. Buys on start, tracks peak price, sells when drawdown exceeds threshold.

**Stop modes**

| Mode | Description |
|------|-------------|
| PCT | Sell when price drops N% below peak |
| ATR | Sell when price drops N × ATR(14) below peak |

**Entry modes**

| Mode | Description |
|------|-------------|
| Market | Buy immediately at market price |
| Limit | Place limit order; cancel and re-enter at market after timeout |
| Scale | Buy in N tranches spaced by interval (dollar-cost average into position) |

**Exit targets**

| Setting | Description |
|---------|-------------|
| Take-profit trigger % | Sell a fraction of the position when up this % |
| Fraction to sell at TP | e.g. 0.5 = sell half, trail the rest |
| Breakeven trigger % | Once up this %, move stop floor to entry (lock in breakeven) |
| Time stop (minutes) | Exit after this many minutes regardless of price |

**Qty sizing**

| Mode | Description |
|------|-------------|
| Shares | Fixed number of shares |
| Dollar amount | Converts to shares at current price |
| Risk % | Sizes so a full stop-out = N% of equity |

**Daily loss limit** — set in Settings; blocks new entries once realized losses reach the threshold.

**Multi-symbol queue** — select multiple Scanner candidates and send them to AutoTrader. Symbols load one at a time; start each to advance the queue.

### 📈 Portfolio Mode

Fully automated multi-position manager. Runs the scanner, opens positions in the top picks, and replaces each position when it closes.

**How it works**

1. On start, scans for candidates and opens up to *target slots* positions simultaneously
2. Each position is sized at *slot %* of current account equity (default: 10 slots × 10%)
3. Every position is managed by AutoTrader with the configured trailing stop
4. When a position closes (stop triggered), the next scanner pick is opened automatically
5. If no qualifying candidates exist, the slot stays empty until the next rescan

**Configuration**

| Setting | Default | Description |
|---------|---------|-------------|
| Target slots | 10 | Maximum simultaneous positions |
| % of equity per slot | 10% | Position size as fraction of equity |
| Stop mode | PCT | PCT or ATR trailing stop |
| Trailing stop value | 0.5% | % drop from peak (PCT) or ATR multiplier |
| Poll interval | 5s | How often each position checks the price |
| Daily loss limit | off | Halts new entries after this cumulative loss |

**Candidate list** — scanned fresh at startup and refreshed automatically if more than 30 minutes old. Already-active symbols are skipped when picking the next candidate.

### 🔍 Scanner

Scans ~600 liquid US stocks, ETFs, and ADRs using daily Alpaca bars and pandas-ta indicators.

**Hard filters** (all must pass)

| Filter | Default | Meaning |
|--------|---------|---------|
| Min price | $5 | Excludes penny stocks |
| Min ADV | $5M/day | Minimum average daily dollar volume |
| RSI(14) | 35–72 | Avoids overbought and deeply oversold |
| Volume | ≥ 1× 20-day avg | Requires above-average volume |
| SMA20 tolerance | 3% | Price may be up to 3% below SMA20 |
| Min 5d return | −1% | Filters out stocks in sharp downtrend |
| Above SMA50 | required | Intermediate-term uptrend required |

**Scoring** — composite rank across:
- Relative strength vs SPY (weight 3×, dominant factor)
- 1-day, 5-day, 10-day, 20-day returns
- SMA20 slope
- ATR% penalty (discounts high-volatility names)

**Live filter controls** — the **Filters** expander lets you adjust all hard-filter thresholds (min price, ADV, RSI range, volume multiplier, SMA20 tolerance, min 5d return) directly on the page without going to Settings. Click *Save as defaults* to persist the current values.

**Historical mode** — tick "Historical date" to scan as of a past date using data up to that close.

**Symbol list** — expand to choose specific symbols or scan the full ~600-symbol universe. Pre-populated from your watchlist in Settings.

**Stale warning** — if results are more than 30 minutes old, a warning appears.

**Sending to AutoTrader** — select rows in the results table (multi-row), click *Send N symbol(s) to AutoTrader*. Symbols are queued.

### 🧪 Backtest

Test AutoTrader logic offline — no real orders placed.

**Replay feed** — fetches real Alpaca 1-minute bars for a symbol and date, plays them back at configurable speed. Supports full day, duration (start time + N hours), or custom time range (ET).

**Synthetic feed** — geometric random walk. Configurable start price, volatility, drift, and random seed for reproducibility.

After the run:
- Live status shows state, entry/current/peak/stop prices, P&L, drawdown bar, replay progress
- Post-run summary shows final P&L (green/red) and fill counts
- Session history table shows all past runs; expand any session to see individual fills

### ⚙️ Settings

All settings saved to `.env` and persist across restarts. See configuration section above for all keys.

---

## IBKR Setup

1. Select **IBKR** in the sidebar and enter credentials in **⚙️ Settings**
2. Click **Start Gateway** — launches headlessly via IBC + Xvfb (30–90s startup)
3. Click **Connect** once the API port shows as *Open*

**Ports**

| Mode  | Port |
|-------|------|
| Paper | 4002 |
| Live  | 4001 |

**Authentication** — IBC supports IBKR Mobile push notifications (approve once at startup). Hardware tokens require one manual login per day.

---

## Versioning

```bash
./bump.sh patch   # 0.15.0 → 0.15.1
./bump.sh minor   # 0.15.0 → 0.16.0
./bump.sh major   # 0.15.0 → 1.0.0
git push && git push --tags
```

---

## Project Structure

```
goldvreneli/
├── goldvreneli.py          # Streamlit UI (all pages)
├── core.py                 # Framework-agnostic core: credentials, client cache, session factories
├── autotrader.py           # AutoTrader + MultiTrader logic
├── portfolio.py            # PortfolioManager: automated multi-position manager
├── scanner.py              # Technical position scanner
├── replay.py               # ReplayPriceFeed, SyntheticPriceFeed, MockBroker
├── gateway_manager.py      # IB Gateway lifecycle (IBC + Xvfb)
├── version.py              # Single version source of truth
├── bump.sh                 # Version bump script
├── goldvreneli-install.sh  # One-command installer + updater
├── requirements.txt        # Python dependencies
├── .env                    # Credentials (gitignored)
└── venv/                   # Python virtual environment (gitignored)
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
