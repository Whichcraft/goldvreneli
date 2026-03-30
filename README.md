# Goldvreneli Trading Dashboard

![Version](https://img.shields.io/badge/version-0.34.2-blue)

A Streamlit-based trading dashboard supporting **Alpaca Paper and Live Trading** and **Interactive Brokers (IBKR)** via IB Gateway, with automated trailing-stop trading, technical scanning, portfolio automation, and offline backtesting.

---

## Features

- **Alpaca paper and live trading** — toggle between modes in the sidebar; live mode requires confirmation and shows a red warning banner
- **IBKR live/paper trading** — IB Gateway managed directly from the app (no Docker); full page parity with Alpaca: Scanner, AutoTrader, Portfolio Mode, and Backtest all work with IBKR
- **AutoTrader** — trailing-stop position manager: holds as long as price rises, sells when it drops below a configurable threshold; supports PCT and ATR stops, limit/scale entry, take-profit, breakeven, time stop, and multi-symbol queuing
- **Portfolio Mode** — fully automated: maintains up to N concurrent positions from scanner picks, each sized at a fixed % of equity; on exit, rescans and opens the next best candidate
- **Position Scanner** — scans liquid stocks, ETFs, and ADRs across four selectable universes (US ~593, INTL small ~62, INTL full ~125, All ~718) with technical filters (RSI, SMA, volume, relative strength vs SPY); **🧪 Test mode** in the sidebar replays as of any past date
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

The sidebar shows an **Alpaca** broker selector with a **Live Trading** toggle. Below the version heading the active account (Paper/Live) is shown at all times.

| Mode | Keys used | Orders |
|------|-----------|--------|
| Paper (default) | `ALPACA_PAPER_*` | Simulated — no real money |
| Live | `ALPACA_LIVE_*` | **Real orders on your funded account** |

Switching to Live requires a confirmation step and displays a persistent red warning banner. If live API keys are not yet configured, an inline credential form appears before proceeding.

---

## Pages (Alpaca Mode)

### 💼 Portfolio
- Account overview: portfolio value, cash, buying power, equity, day P&L with delta %
- Open positions table + unrealized P&L bar chart
- Candlestick price chart (1D / 1W / 1M / 3M) — symbol remembered across page switches
- Place market or limit orders
- Open orders table with cancel all

### 🤖 AutoTrader

AutoTrader manages **one position at a time**. You tell it the symbol, size, and stop settings; it buys immediately, then watches the price in a background thread. As long as the price keeps rising it adjusts the stop floor upward (trailing stop). The moment the price drops below the stop, it sells everything and reports the P&L.

Multiple AutoTrader instances run in parallel under a single **MultiTrader** session. You can start a new position for any symbol while others are still running.

**Typical flow**
1. Run the Scanner, select the best candidates, click *Quick Invest* (or *Configure & Queue*)
2. Set dollar amount and stop % — click **Start**
3. Watch the positions table; each position shows current price, peak, stop floor, and P&L live

**Stop modes**

| Mode | Description |
|------|-------------|
| PCT | Sell when price drops N% below peak (e.g. 0.5%) |
| ATR | Sell when price drops N × ATR(14) dollars below peak — adapts to volatility |

**Entry modes**

| Mode | Description |
|------|-------------|
| Market | Buy immediately at market price |
| Limit | Place limit order; cancel and re-enter at market after timeout |
| Scale | Buy in N equal tranches spaced by interval (dollar-cost averages into position) |

**Optional exit rules** (stack on top of the trailing stop)

| Setting | Description |
|---------|-------------|
| Take-profit % | Sell a fraction of the position when up this % — let the rest trail |
| Breakeven % | Once up this %, move stop floor to entry price (locks in break-even) |
| Time stop | Exit after this many minutes regardless of price |

**Qty sizing**

| Mode | Description |
|------|-------------|
| Shares | Fixed number of shares |
| Dollar amount | Converts to shares at current price |
| Risk % | Sizes so a full stop-out costs exactly N% of your account equity |

**Daily loss limit** — set in Settings; blocks new entries once cumulative realized losses for the session reach the limit.

**Symbol queue** — configure and start one symbol; the next in your selection pre-fills the form automatically.

### 📈 Portfolio Mode

Portfolio Mode is **fully autonomous**. You configure it once and it runs indefinitely: scanning for the best stocks, opening positions, managing each with a trailing stop, and replacing positions as they close — without any manual intervention.

**How it works**

1. Click **Start All** (or Start Sequential) — triggers a scanner run across ~600 symbols
2. The top-ranked candidates are opened immediately, each sized at the configured dollar amount (e.g. $3,000) or % of equity
3. Every position is independently managed by AutoTrader with the trailing stop you configured
4. When a position closes (stop hit), Portfolio Mode immediately opens the next-best scanner pick
5. Candidates older than 30 minutes are automatically refreshed with a new scan

**When to use Start All vs Start Sequential**

| Button | When to use |
|--------|-------------|
| Start All | Normal use — opens all N slots at the same time |
| Start Sequential | Cautious entry — fills one slot at a time as each prior one closes |

**Configuration**

| Setting | Default | Description |
|---------|---------|-------------|
| Target slots | 10 | Maximum simultaneous positions |
| Slot sizing | % of equity | Switch to "Fixed $ per slot" to invest e.g. $3,000 per position |
| Stop mode | PCT | PCT or ATR trailing stop applied to every position |
| Trailing stop value | 0.5% | % drop from peak (PCT) or ATR multiplier |
| Poll interval | 5s | How often each position checks the price |
| Daily loss limit | off | Halts new entries after this cumulative realized loss |

**Candidate list** — scanned fresh at startup and re-scanned automatically when older than 30 minutes. Already-open symbols are skipped; the next-best is chosen instead.

**📥 Monitor existing positions** — if the app restarts while positions are still open in your account, use the *Monitor existing account positions* expander at the bottom of the Portfolio Mode page. It lists positions not yet being tracked and lets you attach a trailing-stop monitor to them without placing any new orders.

### 🔍 Scanner

Scans liquid stocks, ETFs, and ADRs using daily Alpaca bars and pandas-ta indicators. Choose market scope with the **Market** radio at the top of the page:

| Selection | Universe |
|-----------|----------|
| 🇺🇸 US | ~593 US-incorporated equities and US-focused ETFs |
| 🌍 INTL (small) | ~62 flagship foreign ADRs + broad country/regional ETFs |
| 🌍 INTL (full) | ~125 comprehensive international ADRs (superset of small) |
| 🌐 All | Full combined universe (~718 symbols) |

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

**Test mode** — enable **🧪 Test mode (historic data)** in the sidebar to scan as of a past date using data up to that close. The "As-of date" picker appears in the sidebar when enabled.

**Symbol list** — expand to choose specific symbols or scan the full ~600-symbol universe. Pre-populated from your watchlist in Settings.

**Auto-rescan** — if results are more than 30 minutes old, the scanner automatically re-runs with the current filter settings. A warning is shown while the rescan is in progress.

**⚡ Quick Invest** — the fastest path to investing: set a dollar amount, trailing stop %, and number of top positions, then click *Invest Now*. A fill summary appears showing each symbol, quantity, approximate fill price, amount invested, and status. Click *Go to AutoTrader* to navigate once you've reviewed the results. Uses your current row selection, or falls back to the top N by score if nothing is selected.

**Configure & Queue** — select rows, click *Configure & Queue* to send them to AutoTrader where you can review and adjust settings for each before starting.

### ⚙️ Settings

All settings saved to `.env` and persist across restarts. See configuration section above for all keys.

---

## Testing

### Unit tests

Business logic is fully decoupled from the UI. Run the test suite with:

```bash
venv/bin/python -m pytest tests/ -v
```

Covers `size_from_risk`, `_calc_atr`, `SyntheticPriceFeed`, `MockBroker`, `AutoTrader` full lifecycle (market/limit/scale entry, trailing stop, take-profit, breakeven, time stop, error state), and `score_symbol` with synthetic fixture DataFrames.

### 🧪 Test mode (Scanner historic data)

Enable **Test mode (historic data)** in the sidebar to run the Scanner as of any past date. An "As-of date" picker appears; all scanner fetches use closing data up to that date. Portfolio and trading pages are unaffected — this is a read-only, risk-free way to evaluate what the scanner would have surfaced on a given day.

### 🧪 Backtest

Test AutoTrader logic offline — no real orders placed.

**Replay feed** — fetches real Alpaca 1-minute bars for a symbol and date, plays them back at configurable speed. Supports full day, duration (start time + N hours), or custom time range (ET).

**Synthetic feed** — geometric random walk. Configurable start price, volatility, drift, and random seed for reproducibility.

After the run:
- Live status shows state, entry/current/peak/stop prices, P&L, drawdown bar, replay progress
- Post-run summary shows final P&L (green/red) and fill counts
- Session history table shows all past runs; expand any session to see individual fills

---

## IBKR Setup

**Typical workflow**

1. Enter your IBKR credentials in **⚙️ Settings** (username + password)
2. Select **IBKR** in the sidebar broker selector
3. Click **Start Gateway** on the Settings page — launches IB Gateway headlessly via IBC + Xvfb (allow 30–90 s)
4. Once the API port shows *Open*, click **Connect**
5. Approve the login on **IBKR Mobile** (push notification) — required once per session
6. Use any page normally — Scanner, AutoTrader, Portfolio Mode, and Backtest all work with IBKR data and orders

**Ports**

| Mode  | Port |
|-------|------|
| Paper | 4002 |
| Live  | 4001 |

**Authentication** — IBC supports IBKR Mobile push notifications (approve once at startup). Hardware tokens require one manual login per day.

**Note** — Scanner scans one symbol at a time with IBKR historical data; expect slower scan times than Alpaca.

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
├── goldvreneli.py               # Streamlit entry point: sidebar, broker setup, page dispatch
├── pages/
│   ├── settings_page.py         # ⚙️ Settings page
│   ├── help_page.py             # ❓ Help page
│   ├── portfolio_page.py        # 💼 Portfolio page (Alpaca + IBKR)
│   ├── autotrader_page.py       # 🤖 AutoTrader page
│   ├── portfolio_mode_page.py   # 📈 Portfolio Mode page
│   ├── scanner_page.py          # 🔍 Scanner page
│   └── backtest_page.py         # 🧪 Backtest page
├── core.py                      # Framework-agnostic core: credentials, client cache, session factories, LiveFillLogger
├── autotrader.py                # AutoTrader + MultiTrader logic
├── portfolio.py                 # PortfolioManager: automated multi-position manager
├── scanner.py                   # Technical position scanner
├── replay.py                    # ReplayPriceFeed, SyntheticPriceFeed, MockBroker
├── ibkr_data.py                 # IBKRDataClient: Alpaca data client interface shim for IBKR
├── gateway_manager.py           # IB Gateway lifecycle (IBC + Xvfb)
├── version.py                   # Single version source of truth
├── bump.sh                      # Version bump script
├── goldvreneli-install.sh       # One-command installer + updater
├── tests/
│   ├── test_autotrader.py       # Unit tests: size_from_risk, _calc_atr, AutoTrader lifecycle
│   └── test_scanner.py          # Unit tests: score_symbol with fixture DataFrames
├── requirements.txt             # Python dependencies
├── .env                         # Credentials (gitignored)
└── venv/                        # Python virtual environment (gitignored)
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
