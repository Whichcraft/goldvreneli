# Goldvreneli — Architecture Overview

Streamlit trading dashboard. `streamlit run goldvreneli.py`

---

## Layered Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Streamlit UI                                                │  web frontend
│  goldvreneli.py (sidebar + broker setup + dispatch)          │
│  pages/ (one render() fn per page)                          │
├──────────────────────────────────────────────────────────────┤
│  Broker Adapters (Alpaca / IBKR callables)                  │  broker abstraction
│  ibkr_data.IBKRDataClient                                   │
├──────────────────────────────────────────────────────────────┤
│  Business Logic (MultiTrader, Scanner, PortfolioManager)    │  domain logic
├──────────────────────────────────────────────────────────────┤
│  Core Session & Client Management (core.py)                 │  framework-agnostic core
│  core.LiveFillLogger                                        │
├──────────────────────────────────────────────────────────────┤
│  Broker APIs (alpaca-py, ib_async)                          │  third-party SDKs
└──────────────────────────────────────────────────────────────┘
```

**Key design principle:** `core.py` has zero UI dependencies. Business logic receives broker operations as callables, allowing any frontend (Streamlit, CLI, FastAPI) to wire in different brokers without changing trading code.

---

## Directory Structure

```
goldvreneli/
├── goldvreneli.py               # Streamlit entry point: sidebar, broker setup, page dispatch (~450 lines)
├── pages/
│   ├── __init__.py
│   ├── settings_page.py         # render() — ⚙️ Settings
│   ├── help_page.py             # render() — ❓ Help
│   ├── portfolio_page.py        # render(broker, trading_client, data_client, account, ib, gw, ...)
│   ├── autotrader_page.py       # render(mt, get_price_fn, buy_fn, sell_fn, get_bars_fn, ...)
│   ├── portfolio_mode_page.py   # render(mt, data_client, get_price_fn, buy_fn, sell_fn, ...)
│   ├── scanner_page.py          # render(data_client, get_price_fn, buy_fn, sell_fn, mt, ...)
│   ├── backtest_page.py         # render(data_client, broker)
│   └── test_mode_page.py        # render(data_client, get_price_fn, get_bars_fn)
├── core.py                      # Session store, API client caching, factory fns, LiveFillLogger
├── autotrader.py                # AutoTrader, MultiTrader, TraderConfig
├── portfolio.py                 # PortfolioManager
├── scanner.py                   # scan(), ScanFilters, universe lists
├── replay.py                    # ReplayPriceFeed, SyntheticPriceFeed, MockBroker, load_sessions
├── activity_tracker.py          # render_log(), render_sidebar_log() — reusable log renderer
├── ibkr_data.py                 # IBKRDataClient: Alpaca data client interface shim for IBKR
├── gateway_manager.py           # IB Gateway subprocess lifecycle
├── version.py                   # __version__ string
├── .env                         # credentials (created on first run)
├── tests/
│   ├── test_autotrader.py       # 76 tests: TraderConfig, AutoTrader lifecycle, scale entry,
│   │                            #   partial TP, ATR stop, MultiTrader, ReplayPriceFeed
│   └── test_scanner.py          # score_symbol with fixture DataFrames
├── daily_loss.json              # today's cumulative realized loss (auto-managed)
├── live_fills.json              # live trade fill history (auto-managed)
└── backtest_fills.json          # backtest session history (auto-managed)
```

### Page module conventions

Each page module in `pages/` exports a single public function `render(...)`. The signature lists every value the page needs from the broker setup (callables, clients, flags). Pages may define inner helper functions but should not import from each other.

| Module | render() signature | Key dependencies |
|---|---|---|
| `settings_page` | `render()` | `env_get`, `env_save`, `clear_alpaca_cache` |
| `help_page` | `render()` | none |
| `portfolio_page` | `render(broker, trading_client, data_client, account, ib, gw, alpaca_is_live, ibkr_is_live, get_bars_fn)` | plotly, alpaca data types |
| `autotrader_page` | `render(mt, get_price_fn, buy_fn, sell_fn, get_bars_fn, get_equity_fn, broker, trading_client, ib)` | `TraderState`, `TraderConfig`, `load_sessions`, `LIVE_FILLS_FILE` |
| `portfolio_mode_page` | `render(mt, data_client, get_price_fn, buy_fn, sell_fn, get_bars_fn, get_equity_fn, broker, trading_client, ib)` | `TraderState`, `ScanFilters`, `get_portfolio_manager` |
| `scanner_page` | `render(data_client, get_price_fn, buy_fn, sell_fn, mt, use_hist, as_of_date, broker)` | `scan`, `ScanFilters`, universe lists |
| `backtest_page` | `render(data_client, broker)` | `ReplayPriceFeed`, `SyntheticPriceFeed`, `MockBroker`, `load_sessions` |
| `test_mode_page` | `render(data_client, get_price_fn, get_bars_fn)` | `MultiTrader`, `ReplayPriceFeed`, `_ReplayDispatcher`, `autotrader_page` |

---

## File-by-File Reference

### `version.py`

Single source of truth for the package version string.

```python
__version__ = "1.1.0"
```

---

### `core.py` — Session & Client Management

No classes. All framework-agnostic module-level functions.

**Session store protocol** — any `MutableMapping` (dict or `st.session_state`).

| Function | Signature | Purpose |
|---|---|---|
| `env_get` | `(key, default="") → str` | Read from `os.environ` or `.env` fallback |
| `env_save` | `(values: Dict[str,str]) → None` | Persist to `.env` and reload `os.environ` |
| `get_alpaca_clients` | `(api_key, secret_key, paper=True) → (TradingClient, StockHistoricalDataClient)` | Return cached client pair keyed by `(key, secret, paper)` |
| `clear_alpaca_cache` | `() → None` | Invalidate all cached Alpaca clients |
| `get_gateway` | `(session, ibkr_user, ibkr_pass, trading_mode) → GatewayManager` | Get or create `GatewayManager` in session |
| `get_ib` | `(session) → IB` | Get or create `IB()` in session |
| `get_multi_trader` | `(session, get_price_fn, place_buy_fn, place_sell_fn, get_bars_fn=None) → MultiTrader` | Get or create `MultiTrader` in session |
| `get_portfolio_manager` | `(session, data_client, get_price_fn, place_buy_fn, place_sell_fn, get_bars_fn, get_equity_fn, **kwargs) → PortfolioManager` | Get or create `PortfolioManager` in session |

**Module-level state / constants:**
- `INSTALL_DIR` — directory of this file
- `ENV_FILE` — path to `.env`
- `LIVE_FILLS_FILE` — path to `live_fills.json`
- `_DAILY_LOSS_FILE` — path to `daily_loss.json` (private)
- `_alpaca_cache: Dict[Tuple[str,str,bool], Tuple[TradingClient, StockHistoricalDataClient]]`

**Persistence helpers:**
| Function | Purpose |
|---|---|
| `load_daily_loss() → float` | Return today's cumulative realized loss from `daily_loss.json`; 0.0 if absent or stale |
| `save_daily_loss(realized_loss: float)` | Persist today's realized loss to `daily_loss.json` using an **atomic write** (write to `.tmp` then `os.rename`) to prevent corruption on crash |

**`LiveFillLogger`** — thread-safe fill log for live trades (same JSON format as `MockBroker`).

| Method | Signature | Purpose |
|---|---|---|
| `open_session` | `(symbol: str) → str` | Start a new position session; returns session_id |
| `record` | `(session_id, action, symbol, qty, price)` | Append a fill to the session |
| `close_session` | `(session_id, pnl: float)` | Mark session closed with final P&L |

Wired into `MultiTrader` via `fill_open_fn`, `fill_record_fn`, `fill_close_fn` callbacks in `get_multi_trader()`.

**Imports from project:** *(none)*

---

### `autotrader.py` — Trailing-Stop Position Manager

#### Enums

| Enum | Members |
|---|---|
| `TraderState` | `IDLE → ENTERING → WATCHING → SOLD / STOPPED / ERROR` |
| `StopMode` | `PCT`, `ATR` |
| `EntryMode` | `MARKET`, `LIMIT`, `SCALE` |

#### Dataclasses

**`TraderConfig`**

| Field | Default | Purpose |
|---|---|---|
| `stop_mode` | `PCT` | Stop calculation method |
| `stop_value` | `0.5` | % for PCT; ATR multiplier for ATR |
| `poll_interval` | `5.0` | Seconds between price checks |
| `entry_mode` | `MARKET` | Entry execution strategy |
| `limit_price` | `0.0` | Limit entry price |
| `limit_timeout_s` | `60.0` | Limit order timeout before cancelling |
| `scale_tranches` | `1` | Number of scale-in tranches |
| `scale_interval_s` | `30.0` | Seconds between tranches |
| `tp_trigger_pct` | `0.0` | Take-profit trigger (0 = disabled) |
| `tp_qty_fraction` | `1.0` | Fraction to sell at take-profit |
| `breakeven_trigger_pct` | `0.0` | Move stop to entry after this gain (0 = disabled) |
| `time_stop_minutes` | `0.0` | Close after N minutes (0 = disabled) |
| `max_loss_pct` | `0.0` | Per-trade max loss % (0 = disabled) |

`__post_init__` validates all numeric fields and raises `ValueError` on bad values:
- `stop_value > 0`
- `poll_interval > 0`
- `scale_tranches >= 1`
- `tp_qty_fraction` in `(0, 1]`
- `max_loss_pct >= 0`
- `limit_timeout_s > 0`

**`TradeLog`**

| Field | Type |
|---|---|
| `timestamp` | `datetime` |
| `action` | `str` — BUY, SELL, PEAK, STOP, TAKE_PROFIT, BREAKEVEN, TIME_STOP, CANCEL, INFO, ERROR |
| `price` | `float` |
| `note` | `str` |

**`AutoTraderStatus`** — read-only snapshot of trader state

| Field | Type | Purpose |
|---|---|---|
| `state` | `TraderState` | Current lifecycle state |
| `symbol` | `str` | Ticker |
| `qty` / `qty_remaining` | `int` | Original / remaining quantity |
| `entry_price` / `peak_price` / `current_price` / `stop_floor` | `float` | Price levels |
| `threshold_pct` | `float` | Active trailing stop % |
| `drawdown_pct` / `pnl` | `float` | Drawdown from peak; unrealized P&L |
| `atr_value` | `float` | Last ATR value (ATR mode) |
| `tp_price` / `tp_executed` / `realized_pnl` | `float/bool/float` | Take-profit state |
| `breakeven_active` | `bool` | Whether stop has been moved to entry |
| `tranches_filled` | `int` | Scale-in progress |
| `config` | `TraderConfig` | Snapshot of config at entry |
| `entry_time` | `Optional[datetime]` | When position was entered |
| `last_poll_at` | `Optional[datetime]` | Timestamp of most recent price fetch; used by UI to detect stalled feeds |
| `log` | `List[TradeLog]` | Full activity log |

#### `AutoTrader` class

Single-symbol trailing-stop manager. Runs main loop in a daemon thread.

**Constructor:**
```python
AutoTrader(
    get_price: Callable[[str], float],
    place_buy: Callable[[str, int], None],
    place_sell: Callable[[str, int], None],
    get_bars: Optional[Callable] = None,   # required for ATR mode
    threshold_pct: float = 0.5,
    poll_interval: float = 5.0,
)
```

**Public API:**

| Method | Signature | Purpose |
|---|---|---|
| `start` | `(symbol, qty, config=None, threshold_pct=None, poll_interval=None)` | Buy + begin monitoring |
| `stop` | `()` | Halt monitoring (position stays open on broker) |
| `set_threshold` | `(pct: float)` | Adjust trailing stop % live (PCT mode only) |
| `attach` | `(symbol, qty, entry_price, config=None)` | Attach to existing position (skip buy) |

**Public attributes:**
- `status: AutoTraderStatus`
- `_on_close: Optional[Callable[[float], None]]` — called with P&L on close

**Internal methods:**

| Method | Purpose |
|---|---|
| `_do_market_entry()` | Immediate market buy |
| `_do_limit_entry()` | Wait for limit fill or timeout/cancel |
| `_do_scale_entry()` | Buy N tranches at intervals; per-tranche try/except for partial-fill recovery |
| `_get_atr()` | Fetch ATR, cached 300s |
| `_update_stop_floor()` | Compute stop price from peak + mode |
| `_run()` | Main loop (daemon thread); sets `status.last_poll_at` on every price fetch |
| `_log(action, price, note)` | Append to trade log |

**Scale entry partial-fill recovery:** If a tranche buy throws an exception, the loop breaks and proceeds to WATCHING with however many shares were already filled. Subsequent tranches are abandoned rather than orphaned.

#### `MultiTrader` class

Manages concurrent `AutoTrader` instances keyed by symbol.

**Constructor:**
```python
MultiTrader(
    get_price: Callable[[str], float],
    place_buy: Callable[[str, int], None],
    place_sell: Callable[[str, int], None],
    get_bars: Optional[Callable] = None,
    daily_loss_limit: float = 0.0,   # halt new trades if cumulative loss exceeds this
)
```

**Public API:**

| Method | Signature | Purpose |
|---|---|---|
| `start` | `(symbol, qty, config=None, threshold_pct=None, poll_interval=None, on_close=None) → AutoTrader` | Start new position (raises if loss limit hit) |
| `attach` | `(symbol, qty, entry_price, config=None, on_close=None) → AutoTrader` | Attach to existing position |
| `stop` | `(symbol: str)` | Stop single position |
| `stop_all` | `()` | Stop all WATCHING positions |
| `statuses` | `() → Dict[str, AutoTraderStatus]` | Snapshot of all traders |
| `active_symbols` | `() → List[str]` | Symbols in WATCHING state |
| `all_logs` | `() → List[TradeLog]` | Merged sorted logs |
| `unrealized_pnl` | `() → float` | Sum of unrealized P&L |
| `daily_pnl` | `() → float` | Unrealized + realized P&L for the session |
| `realized_losses` | `() → float` | Cumulative realized losses |

**Internal state:**
- `_traders: Dict[str, AutoTrader]`
- `_realized_loss: float`
- `_loss_lock: threading.Lock`

**Constants:** `_ATR_CACHE_TTL = 300` (seconds)

#### Top-level functions

| Function | Signature | Purpose |
|---|---|---|
| `size_from_risk` | `(equity, risk_pct, entry_price, stop_distance) → int` | Shares that risk exactly `risk_pct`% of equity |
| `_calc_atr` | `(bars: pd.DataFrame, period=14) → float` | ATR from bars with high/low/close |

**Imports from project:** *(none)*

---

### `portfolio.py` — Automated Portfolio Manager

#### `PortfolioManager` class

Maintains up to `target_slots` concurrent AutoTrader positions, auto-refilling on close.

**Constructor:**
```python
PortfolioManager(
    data_client,                              # Alpaca StockHistoricalDataClient
    get_price_fn: Callable[[str], float],
    place_buy_fn: Callable[[str, int], None],
    place_sell_fn: Callable[[str, int], None],
    get_bars_fn: Optional[Callable],
    get_equity_fn: Callable[[], float],
    target_slots: int = 10,
    slot_pct: float = 10.0,                  # % of equity per slot
    slot_dollar: float = 0.0,               # fixed $ per slot (overrides slot_pct if > 0)
    trader_config: Optional[TraderConfig] = None,
    scan_filters=None,                        # ScanFilters instance
    daily_loss_limit: float = 0.0,
)
```

**Public API:**

| Method | Signature | Purpose |
|---|---|---|
| `start` | `()` | Scan → fill all slots sequentially |
| `start_all` | `()` | Scan → open all slots in parallel |
| `stop` | `()` | Stop portfolio (open positions remain) |
| `running` | `@property → bool` | Whether portfolio is active |
| `active_count` | `() → int` | Positions in ENTERING or WATCHING |
| `open_slot_count` | `() → int` | Empty slots |
| `statuses` | `() → Dict` | Snapshot of all trader statuses |
| `session_pnl` | `() → float` | Accumulated P&L from closed positions |
| `realized_losses` | `() → float` | Cumulative realized losses |
| `log_entries` | `() → List[Dict]` | Last 200 activity log entries |
| `scan_age_s` | `() → Optional[float]` | Seconds since last scan |

**Internal methods:**

| Method | Purpose |
|---|---|
| `_slot_label()` | Human-readable sizing description for log messages |
| `_log(msg, level)` | Append timestamped log entry |
| `_rescan()` | Run scanner with lock; blocks concurrent rescans |
| `_candidates_stale()` | True if candidate list > 30 min old |
| `_next_candidate()` | Pop top candidate not held/claimed (atomic) |
| `_open_one_slot()` | Open one position; schedule next slot on close |
| `_fill_empty_slots()` | Sequential startup |
| `_fill_empty_slots_parallel()` | Parallel startup (N threads) |

**Internal state:**
- `_multi: MultiTrader`
- `_candidates: List[str]`
- `_candidates_ts: Optional[datetime]`
- `_claimed: set` — symbols claimed but not yet opened
- `_lock: threading.Lock` — candidates/log/claimed
- `_scan_lock: threading.Lock` — prevents concurrent rescans
- `_session_pnl: float`

**Constants:** `_SCAN_MAX_AGE_S = 1800` (30 min)

**Imports from project:** `autotrader`, `scanner`

---

### `scanner.py` — Stock Scanner

#### `ScanFilters` dataclass

| Field | Default | Hard filter condition |
|---|---|---|
| `min_price` | `5.0` | Last price > min_price |
| `min_adv_m` | `5.0` | ADV > min_adv_m × $1M |
| `rsi_lo` | `35.0` | RSI(14) ≥ rsi_lo |
| `rsi_hi` | `72.0` | RSI(14) ≤ rsi_hi |
| `vol_mult` | `1.0` | Last volume ≥ vol_mult × 20d avg |
| `sma20_tol_pct` | `3.0` | Price ≥ SMA20 × (1 − tol/100) |
| `min_ret_5d` | `−1.0` | 5d return ≥ min_ret_5d % |

Additional always-on filter: Price ≥ SMA50.

#### Scoring formula

```
score = rs_5d×3  + rs_20d×1  + ret_5d×1  + ret_10d×0.5  + ret_20d×0.3
      + ret_1d×0.5  + (rsi-50)×0.2  + (macd_hist>0)×4
      + above_both_smas×3  + sma_slope×0.5
      - max(0, atr_pct-3)×0.5
```

#### Top-level functions

| Function | Signature | Purpose |
|---|---|---|
| `fetch_bars` | `(data_client, symbol, days=60, as_of=None) → Optional[DataFrame]` | Fetch daily bars via Alpaca (60-day lookback) |
| `score_symbol` | `(bars, spy_rets=None, filters=None) → dict or None` | Compute indicators; None if any hard filter fails |
| `_batch_fetch` | `(data_client, syms, days=60, as_of=None) → Dict[str, DataFrame]` | Multi-symbol batch fetch |
| `scan` | `(data_client, top_n=10, progress_cb=None, as_of=None, chunk_size=250, filters=None, symbols=None) → Tuple[DataFrame, int, int]` | Full scan; returns `(top_n_df, skipped_history, skipped_no_data)` |

**`scan()` return value:**
- `df` — `pd.DataFrame` of top N candidates sorted by score, index=Symbol
- `skipped_history` — count of symbols with fewer than 52 bars (insufficient history)
- `skipped_no_data` — count of symbols with no data returned from Alpaca at all

**`scan()` output columns:** `Symbol`, `Price`, `RSI`, `1d Ret%`, `5d Ret%`, `20d Ret%`, `RS vs SPY`, `Vol/Avg`, `ATR%`, `MACD+`, `ADV $M`

**Parallelization:** `ThreadPoolExecutor(max_workers=4)`, chunks of 250 symbols.

#### Universe constants

| Constant | Size | Contents |
|---|---|---|
| `UNIVERSE_US` | ~400 | US equities and ETFs |
| `UNIVERSE_INTL` | ~60 | Flagship ADRs + country ETFs |
| `UNIVERSE_INTL_FULL` | ~120 | Extended international ADRs |
| `UNIVERSE_CH` | ~94 | Swiss-incorporated equities, OTC ADRs, and ETFs (NYSE/NASDAQ-listed Swiss cos, Swiss-chartered NYSE/NASDAQ cos, OTC ADRs mega/large/mid/small-cap, sector buckets: pharma, RE, financial, industrial, ETFs) |
| `UNIVERSE` | combined | All of the above deduplicated |

**Imports from project:** *(none)*

---

### `replay.py` — Backtest Tools

#### `ReplayPriceFeed` class

Replays Alpaca 1-minute historical bars at configurable speed.

**Constructor:**
```python
ReplayPriceFeed(
    data_client,
    symbol: str,
    replay_date: str,              # "YYYY-MM-DD"
    speed: float = 100.0,          # replay multiplier vs real-time
    start_time: Optional[time] = None,
    end_time: Optional[time] = None,
    duration_hours: Optional[float] = None,
)
```

| Method/Property | Purpose |
|---|---|
| `get_price(symbol) → float` | Advance index, return next price |
| `reset()` | Reset to start |
| `recommended_poll_interval` | Seconds between polls for real-time parity |
| `exhausted` / `progress` / `bar_count` / `current_bar` / `current_time` | State inspection |

#### `SyntheticPriceFeed` class

Geometric Brownian Motion price generator.

**Constructor:**
```python
SyntheticPriceFeed(
    start_price: float = 100.0,
    volatility_pct: float = 0.5,
    drift_pct: float = 0.0,
    seed: Optional[int] = None,
)
```

| Method/Property | Purpose |
|---|---|
| `get_price(symbol) → float` | Generate next GBM price |
| `reset()` | Reset to start price |
| `step` | Steps taken |

#### `MockBroker` class

Fake broker that records fills and persists to JSON.

**Constructor:**
```python
MockBroker(
    get_price_fn: Callable[[str], float],
    output_file: str = "backtest_fills.json",
    session_meta: Optional[Dict] = None,
)
```

| Method/Property | Purpose |
|---|---|
| `get_price(symbol) → float` | Fetch from feed |
| `buy(symbol, qty)` | Record BUY fill |
| `sell(symbol, qty)` | Record SELL fill |
| `close(pnl=0.0)` | Mark session closed, flush JSON |
| `session_id` | Short UUID |
| `fills` | Copy of current fills |

**JSON format:**
```json
{
  "sessions": [{
    "id": "abc123",
    "started_at": "...", "closed_at": "...",
    "meta": {...},
    "fills": [{"time":"...","action":"BUY","symbol":"AAPL","qty":10,"price":230.5,"value":2305.0}],
    "pnl": 150.25
  }]
}
```

#### Top-level functions

| Function | Signature | Purpose |
|---|---|---|
| `load_sessions` | `(output_file) → List[Dict]` | Load all sessions, newest first |

**Imports from project:** *(none)*

---

### `activity_tracker.py` — Reusable Activity Log Renderer

Module-level functions for rendering a `MultiTrader` activity log in Streamlit. Used by `autotrader_page` and the sidebar.

| Function | Signature | Purpose |
|---|---|---|
| `render_log` | `(mt: MultiTrader, max_rows=None)` | Full activity log table (reversed chronological) |
| `render_sidebar_log` | `(mt: MultiTrader, max_rows=8)` | Compact log panel inside `st.expander` in the sidebar |

**Imports from project:** `autotrader`

---

### `pages/test_mode_page.py` — Paper Trading / Replay Simulator

Runs AutoTrader logic against live or historical prices without placing real orders. Buys/sells are simulated (fills recorded at the polled price, no broker order submitted).

**Modes:**
- **Live** — uses the real-time `get_price_fn` callable; runs indefinitely.
- **Replay** — replays Alpaca 1-min bars via `_ReplayDispatcher` at a configurable speed multiplier; each symbol gets its own `ReplayPriceFeed` created lazily on first use.

#### `_ReplayDispatcher` (module-private)

Per-symbol `ReplayPriceFeed` factory and dispatcher. Created once per replay config; stored in `st.session_state`.

```python
_ReplayDispatcher(
    data_client,
    replay_date: str,        # "YYYY-MM-DD"
    speed: float,
    start_time=None,         # time window: Full day, Duration, or Custom range
    end_time=None,
    duration_hours=None,
)
```

| Method | Purpose |
|---|---|
| `get_price(symbol) → float` | Create feed on first call; return next price; return 0.0 on feed error |
| `progress_for(symbol) → (pct, bar, total)` | Replay progress for a symbol |
| `exhausted_for(symbol) → bool` | Whether feed for symbol is exhausted |
| `current_time_for(symbol) → str` | Formatted replay clock for symbol |

**Thread safety:** `_lock` guards `_feeds` / `_errors` dict mutations.

**Config change detection:** The page serialises the active replay config to `st.session_state[_TEST_CFG_KEY]` on each run. If it differs from the stored value, all feeds and the simulated `MultiTrader` are reset automatically.

**Imports from project:** `autotrader`, `replay`, `pages.autotrader_page`

---

### `gateway_manager.py` — IB Gateway Lifecycle

#### `GatewayManager` class

Manages IB Gateway via IBC + Xvfb subprocesses.

**Constructor:**
```python
GatewayManager(
    username: str,
    password: str,
    trading_mode: str = "paper",
    ibc_path: str = None,
    gateway_path: str = None,
    timezone: str = "America/New_York",
    display: str = ":99",
)
```

| Method | Signature | Purpose |
|---|---|---|
| `start` | `()` | Start Xvfb + IB Gateway via IBC (idempotent) |
| `stop` | `()` | Stop Gateway and Xvfb |
| `is_running` | `() → bool` | Gateway process alive |
| `wait_for_api` | `(timeout=90, poll=2.0) → bool` | Poll until API port accepts connections |
| `get_logs` | `(lines=60) → str` | Recent stdout from gateway |
| `api_port_open` | `() → bool` | TCP check on API port |
| `_write_config() → str` | Write IBC config file to temp dir; returns path |
| `_start_xvfb()` | Launch Xvfb virtual display subprocess |
| `_gateway_path_resolved() → str` | Resolve gateway binary path (auto-detect version subdir) |

**Constants:** `PAPER_PORT = 4002`, `LIVE_PORT = 4001`

**Imports from project:** *(none)*

---

### `goldvreneli.py` — Streamlit Entry Point

~450 lines. No classes. Responsible for sidebar, broker setup, and dispatching to page modules.

#### Structure

| Lines (approx) | Section |
|---|---|
| 1–95 | Imports, config, sidebar (broker + page selector, live/test toggles) |
| 96–111 | IBKR session helpers; Settings/Help early dispatch |
| 112–583 | Alpaca broker block (confirmation, clients, callables, page dispatch) |
| 584–977 | IBKR broker block (confirmation, gateway panel, callables, page dispatch) |

#### Pages

| Tab | Key Features |
|---|---|
| **Settings** | Alpaca/IBKR credentials; scanner/AutoTrader/Portfolio defaults |
| **Help** | Documentation, workflows, keyboard shortcuts |
| **Portfolio** | Account metrics, positions, price chart, place orders, open orders |
| **AutoTrader** | Multi-symbol manager, queue, position table, daily summary, trade history, CSV export |
| **Portfolio Mode** | Automated multi-slot investing, monitoring |
| **Scanner** | Technical screening, Quick Invest (skips already-open positions), queue to AutoTrader |
| **Backtest** | Replay/synthetic feeds, mock broker, session history, CSV export |
| **Test Mode** | Paper trading against live or historical prices; per-symbol replay progress |

#### Broker scope

- **Alpaca** — all pages
- **IBKR** — all pages (full parity: Scanner, AutoTrader, Portfolio Mode, Portfolio, Backtest, Settings, Help)

#### Shared broker callables (defined in goldvreneli.py, injected into page modules)

| Callable | Broker | Purpose |
|---|---|---|
| `alpaca_get_price(symbol) → float` | Alpaca | Latest quote/trade |
| `alpaca_buy(symbol, qty)` | Alpaca | Market buy |
| `alpaca_sell(symbol, qty)` | Alpaca | Market sell |
| `alpaca_get_bars(symbol) → DataFrame` | Alpaca | 30d daily bars |
| `ibkr_get_price(symbol) → float` | IBKR | Mid of bid/ask |
| `ibkr_buy(symbol, qty)` | IBKR | Market buy |
| `ibkr_sell(symbol, qty)` | IBKR | Market sell |
| `ibkr_get_bars(symbol) → DataFrame` | IBKR | 30d daily bars |
| `ibkr_get_equity() → float` | IBKR | Account equity (NetLiquidation) |

#### `IBKRDataClient` shim (`ibkr_data.py`)

Standalone class (moved from inner class in 0.31.0). Instantiated as `data_client = IBKRDataClient(ib)` in the IBKR broker block.

| Method | Purpose |
|---|---|
| `get_stock_bars(req)` | Translates Alpaca `StockBarsRequest` to `ib.reqHistoricalData()`; returns object with `.df`; supports daily and 1-minute bars |

Note: fetches one symbol at a time — expect slower scan times than Alpaca batch fetches.

#### Key session state variables

| Key | Type | Purpose |
|---|---|---|
| `multitrader` | `MultiTrader` | Active trading session |
| `portfolio_manager` | `PortfolioManager` | Portfolio automation |
| `gateway` | `GatewayManager` | IBKR gateway instance |
| `ib` | `IB` | ib_async connection |
| `alpaca_live` | `bool` | Alpaca paper/live toggle |
| `ibkr_live` | `bool` | IBKR paper/live toggle |
| `ibkr_live_confirmed` | `bool` | Guards IBKR live confirmation step |
| `at_current_symbol` | `str` | AutoTrader form prefill |
| `at_queue` | `List[str]` | Queued symbols |
| `scan_results` | `DataFrame` | Last scanner results |
| `scan_ts` | `datetime` | Timestamp of last scan |
| `_chart_sym` | `str` | Price chart symbol |
| `_broker_last` | `str` | Last active broker key (`"Alpaca"`, `"IBKR:paper"`, `"IBKR:live"`); triggers session reset on change |
| `gw_start_attempted` | `bool` | Prevents repeated gateway auto-start on every rerun |
| `ib_connect_attempted` | `bool` | Prevents repeated IB connect on every rerun |
| `test_mode_multitrader` | `MultiTrader` | Simulated MultiTrader for Test Mode |
| `test_mode_replay_dispatcher` | `_ReplayDispatcher` | Per-symbol replay feed manager |
| `test_mode_replay_cfg` | `dict` | Last-used replay config; change detection triggers reset |

**Imports from project:** all modules (`core`, `autotrader`, `portfolio`, `scanner`, `replay`, `gateway_manager`, `version`)

---

## Key Algorithms

### Trailing stop (PCT mode)
```
stop_floor = peak_price × (1 − stop_value / 100)
if breakeven_active: stop_floor = max(stop_floor, entry_price)
if current_price ≤ stop_floor: SELL
```

### Trailing stop (ATR mode)
```
stop_floor = peak_price − ATR(14) × stop_value
if breakeven_active: stop_floor = max(stop_floor, entry_price)
if current_price ≤ stop_floor: SELL
```

### Risk-based sizing
```
risk_dollars = equity × risk_pct / 100
qty = floor(risk_dollars / stop_distance)
```

### Scale entry
```
for i in range(n_tranches):
    try:
        buy tranche_qty shares at market
        total_filled += tranche_qty
    except Exception:
        if total_filled > 0: break   # proceed with partial fill
        else: break                  # nothing filled; abort
    sleep(scale_interval_s)
entry_price = total_cost / total_qty   # weighted average
```

### Take-profit partial exit
```
if current_price ≥ entry_price × (1 + tp_trigger_pct/100):
    sell_qty = int(qty_remaining × tp_qty_fraction)
    place_sell(sell_qty)
    qty_remaining -= sell_qty
    # trail the remainder
```

---

## Data Flow Diagrams

### AutoTrader flow
```
User: symbol + qty + config
  → MultiTrader.start()
  → AutoTrader spawns daemon thread
  → _run() loop:
      ENTERING: market/limit/scale buy
      WATCHING: poll price → set last_poll_at → update peak/stop
               → check TP, breakeven, time stop, trailing stop
               → if triggered: place_sell → _on_close(pnl)
```

### Portfolio Mode flow
```
User: start_all()
  → _fill_empty_slots_parallel()
  → _rescan() → top N candidates
  → N threads, each: _open_one_slot()
      → _next_candidate() → size qty → MultiTrader.start()
      → on_close: _session_pnl += pnl → spawn next slot
```

### Scanner flow
```
scan(data_client, filters)
  → fetch SPY bars (baseline for RS)
  → batch fetch all symbols' 60d bars (parallel, chunks of 250)
  → score_symbol() per symbol:
      apply hard filters → compute indicators → composite score
  → sort DESC → return (top_n DataFrame, skipped_history, skipped_no_data)
```

### Backtest flow
```
ReplayPriceFeed (or SyntheticPriceFeed)
  ↕ get_price()
MockBroker ← same AutoTrader code as live trading
  → fills logged → backtest_fills.json
```

### Test Mode flow
```
User: configure symbol + qty + config (Live or Replay mode)
  → Test Mode MultiTrader (simulated buy/sell, no real orders)
  → Live mode: uses real get_price_fn
  → Replay mode: _ReplayDispatcher.get_price(sym)
      → lazy-creates ReplayPriceFeed per symbol on first call
      → advances independently per symbol
  → UI shows per-symbol replay progress bars + clock
```

---

## Threading Model

| Component | Thread | Sync |
|---|---|---|
| `AutoTrader` | One daemon thread per instance (`_run`) | `_stop_event` for shutdown |
| `MultiTrader` | No own threads; coordinates AutoTraders | `_loss_lock` for traders dict + loss counter |
| `PortfolioManager` | Daemon threads for slot filling | `_lock` (candidates/log), `_scan_lock` (rescan) |
| `ReplayPriceFeed` | Thread-safe `get_price` | `_lock` on index |
| `SyntheticPriceFeed` | Thread-safe `get_price` | `_lock` on price/step |
| `MockBroker` | Thread-safe file writes | `_write_lock`, `_price_lock` |
| `_ReplayDispatcher` | Thread-safe feed creation | `_lock` on `_feeds`/`_errors` dict |

---

## Configuration Flow

```
.env file (INSTALL_DIR/.env)
  ↕ env_get / env_save
os.environ  (highest priority)
  ↓
Settings page (goldvreneli.py) — reads defaults, writes on Save
```

### Environment variables

| Variable | Purpose |
|---|---|
| `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_SECRET_KEY` | Alpaca paper credentials |
| `ALPACA_LIVE_API_KEY` / `ALPACA_LIVE_SECRET_KEY` | Alpaca live credentials |
| `IBKR_USERNAME` / `IBKR_PASSWORD` | IBKR credentials |
| `IBKR_MODE` | Stored preference only (Settings page); runtime port is driven by the `ibkr_live` sidebar toggle, not this value |
| `IBC_PATH` / `GATEWAY_PATH` | IBC and Gateway installation paths |
| `AT_SYMBOL` / `AT_THRESHOLD` / `AT_POLL` / `AT_DAILY_LOSS_LIMIT` | AutoTrader defaults |
| `SCAN_TOP_N` / `SCAN_RSI_LO` / `SCAN_RSI_HI` / `SCAN_VOL_MULT` | Scanner filter defaults |
| `SCAN_MIN_PRICE` / `SCAN_MIN_ADV_M` / `SCAN_SMA20_TOL` / `SCAN_MIN_RET5D` | Scanner filter defaults |
| `SCAN_WATCHLIST` | Pre-selected symbols for Scanner |
| `PM_TARGET_SLOTS` / `PM_SLOT_PCT` / `PM_SLOT_DOLLAR` | Portfolio Mode defaults |

---

## Design Patterns

| Pattern | Where | Benefit |
|---|---|---|
| Session store protocol | `core.py` | Decouples from Streamlit; works with any `MutableMapping` |
| Dependency injection | Callable parameters (`get_price_fn`, `buy_fn`, …) | Swap brokers without changing trading code; easy backtest |
| Snapshot pattern | `AutoTraderStatus`, `MultiTrader.statuses()` | Thread-safe reads without locks |
| Event signalling | `AutoTrader._stop_event` | Graceful shutdown, no busy-wait |
| Daemon threads | All background loops | Auto-cleanup on process exit |
| Atomic file write | `MockBroker._flush()`, `core.save_daily_loss()` | Temp file → rename, prevents corruption on crash |
| Module-level caching | `core._alpaca_cache` | Survives Streamlit page reruns |
| Rescan locking | `PortfolioManager._scan_lock` | Serialises long-running rescans |
| Lazy per-symbol feeds | `_ReplayDispatcher` in test_mode_page | Supports multi-symbol replay without sharing feed state |
| Heartbeat timestamp | `AutoTraderStatus.last_poll_at` | UI detects stalled price feeds (threshold: 3× poll_interval) |

---

## Test Suite

Run with: `venv/bin/python -m pytest tests/ -v`

### `tests/test_autotrader.py` — 76 tests

| Class | Tests | What is covered |
|---|---|---|
| `TestSizeFromRisk` | 3 | `size_from_risk()` edge cases |
| `TestCalcAtr` | 3 | `_calc_atr()` with fixture DataFrames |
| `TestSyntheticPriceFeed` | 4 | GBM price generation, seed, floor |
| `TestMockBroker` | 6 | Fill recording, JSON persistence, atomicity |
| `TestAutoTraderLifecycle` | 11 | Full state machine: IDLE→ENTERING→WATCHING→SOLD/STOPPED/ERROR |
| `TestTraderConfigValidation` | 6 | `__post_init__` raises on bad stop_value, poll_interval, scale_tranches, tp_qty_fraction, max_loss_pct, limit_timeout_s |
| `TestScaleEntry` | 8 | Scale buy: full fill, partial fill on exception, ATR stop compatibility |
| `TestPartialTakeProfit` | 6 | Take-profit partial exit; qty_remaining; trailing the remainder |
| `TestAtrStopLifecycle` | 8 | ATR stop calculation, cache TTL, stop movement |
| `TestMultiTrader` | 11 | Concurrent positions, daily loss limit enforcement, `active_symbols()` |
| `TestReplayPriceFeed` | 10 | Replay advance, exhaustion, `object.__new__` bypass for unit testing without API calls |

### `tests/test_scanner.py`

Unit tests for `score_symbol()` with fixture DataFrames. Covers filter pass/fail and scoring formula correctness.

---

## Page modules — Function Reference

### `goldvreneli.py` broker-adapter functions (closures over client objects)

| Function | Module | Purpose |
|---|---|---|
| `alpaca_get_price(symbol) → float` | `goldvreneli.py` | Latest trade/quote price via Alpaca |
| `alpaca_buy(symbol, qty)` | `goldvreneli.py` | Market BUY via Alpaca trading client |
| `alpaca_sell(symbol, qty)` | `goldvreneli.py` | Market SELL via Alpaca trading client |
| `alpaca_get_bars(symbol) → DataFrame` | `goldvreneli.py` | 30-day daily OHLCV bars via Alpaca |
| `ibkr_get_price(symbol) → float` | `goldvreneli.py` | Live mid price via IB ticker stream |
| `ibkr_buy(symbol, qty)` | `goldvreneli.py` | Market BUY via IBKR |
| `ibkr_sell(symbol, qty)` | `goldvreneli.py` | Market SELL via IBKR |
| `ibkr_get_bars(symbol) → DataFrame` | `goldvreneli.py` | 30-day daily bars via `ib.reqHistoricalData()` |
| `ibkr_get_equity() → float` | `goldvreneli.py` | Account equity via IB account summary (NetLiquidation) |

### Inner helpers (defined inside page `render()` functions — not exported)

| Function | Module | Purpose |
|---|---|---|
| `_check_alpaca(key, secret, paper, label)` | `settings_page` | Validate Alpaca API keys |
| `_render_alpaca(...)` | `portfolio_page` | Alpaca-specific portfolio view |
| `_render_ibkr(...)` | `portfolio_page` | IBKR-specific portfolio view |
| `_launch_pm(mode)` | `portfolio_mode_page` | Create/configure `PortfolioManager` and start |
| `on_progress(done, total)` | `scanner_page` | Progress callback passed to `scan()` |

---

## Streamlit Rerun Model

### What triggers `st.rerun()`

Every rerun re-executes the entire script from line 1. Session state persists between reruns; local variables do not.

| Trigger | Location | Why |
|---|---|---|
| Settings saved | Settings page | Reload with new credential validation results |
| Alpaca live confirmed | Alpaca block | Apply live guard flag and continue rendering |
| Alpaca live cancelled | Alpaca block | Reset toggle, re-render without confirmation dialog |
| Alpaca live keys saved | Alpaca block | Credentials now available; retry live clients |
| Cancel all orders (Alpaca) | Portfolio view | Refresh order table |
| IBKR live confirmed | IBKR block | Apply guard flag and continue |
| IBKR live cancelled | IBKR block | Reset toggle |
| Gateway API port ready | IBKR block | Advance to connection step |
| IB connected | IBKR block | Advance to page rendering |
| Manual gateway/connect/disconnect/stop buttons | Settings (IBKR) | Reflect new connection state |
| Cancel all orders (IBKR) | Portfolio view | Refresh order table |
| AutoTrader position started | AutoTrader | Show new position in table |
| Stop all | AutoTrader | Clear active positions |
| Individual position stopped | AutoTrader | Remove row from table |
| **Auto-refresh (5s, fragment)** | AutoTrader | Any position in ENTERING or WATCHING state — reruns only the positions fragment, not the form |
| Portfolio Mode started | Portfolio Mode | Show running state |
| Portfolio Mode stopped | Portfolio Mode | Show idle state |
| Monitor position attached | Portfolio Mode | Show attached traders |
| **Auto-refresh (5s)** | Portfolio Mode | While `pm_running` is True |
| Quick Invest complete | Scanner | Shows fill summary; user clicks "Go to AutoTrader" to navigate |
| Symbols queued to AutoTrader | Scanner | Cross-page navigation |
| Stale scan results (30 min) | Scanner | Auto-triggers rescan via `scan_auto_trigger` flag |
| Backtest started | Backtest | Show live status |
| Backtest stopped | Backtest | Show results |
| Refresh history button | Backtest | Reload `backtest_fills.json` |
| Test Mode replay config changed | Test Mode | Detected via `_TEST_CFG_KEY` diff; resets feeds + MultiTrader |
| Test Mode account reset | Test Mode | Clears simulated fills and MultiTrader |

### Auto-refresh loop invariant

AutoTrader's live view is wrapped in `@st.fragment`. The `time.sleep(5); st.rerun()` inside the fragment only reruns the fragment — the form above is unaffected. **Never place side-effectful code** (orders, writes) between the activity check and `st.rerun()` — it will execute on every poll cycle.

Portfolio Mode page still uses a whole-page `time.sleep(5); st.rerun()` because it has no user-input form above the live view.

### Session state keys by category

| Category | Keys | Notes |
|---|---|---|
| **Navigation** | `nav_page` | pop on use; drives `nav_radio` page jump |
| **Auth/config** | `_settings_key_msgs`, `_alpaca_mode`, `_broker_last` | `_broker_last` = `"Alpaca"` / `"IBKR:paper"` / `"IBKR:live"` |
| **Live guards** | `live_confirmed`, `ibkr_live_confirmed` | Cleared when toggle turned off |
| **Gateway** | `gateway`, `gw_start_attempted`, `ib_connect_attempted` | Cleared on broker/mode change |
| **UI state** | `_chart_sym`, `scan_sel_all`, `_scan_market_prev` | Local UI memory |
| **AT queue** | `at_current_symbol`, `at_queue`, `at_prefill`, `at_prefill_list` | Cross-page handoff from Scanner |
| **Trader objects** | `multitrader`, `portfolio_manager`, `bt_at` | Cleared on broker/mode change |
| **Scan cache** | `scan_results`, `scan_ts` | Written by Scanner; read by Portfolio Mode |
| **Scan auto-trigger** | `scan_auto_trigger` | One-shot flag; set when results go stale; consumed at scan trigger point |
| **Quick Invest** | `qi_summary` | Fill summary list shown after Invest Now; cleared on next invest or navigation |
| **Test Mode** | `test_mode_multitrader`, `test_mode_replay_dispatcher`, `test_mode_replay_cfg` | Simulated trading state; reset on config change or manual account reset |

---

## Live Trading Guardrails

### Alpaca live confirmation (lines ~459–476)

```
alpaca_is_live = st.session_state.get("alpaca_live", False)

if not alpaca_is_live:
    st.session_state.pop("live_confirmed", None)   ← reset guard when toggled off

if alpaca_is_live and not st.session_state.get("live_confirmed"):
    show warning dialog with two buttons:
        "I understand — switch to Live"  → live_confirmed = True  → st.rerun()
        "Cancel — stay on Paper"         → alpaca_live = False    → st.rerun()
    st.stop()   ← nothing below executes until user confirms

if alpaca_is_live:
    st.error("⚠️ LIVE TRADING — real orders on your funded account")
    # normal page rendering continues
```

**Invariant:** `live_confirmed` is truthy only when `alpaca_is_live` is also True. Turning the toggle off clears the flag, so next toggle-on always re-prompts.

### IBKR live confirmation (lines ~746–763)

Mirrors Alpaca exactly, using keys `ibkr_live` / `ibkr_live_confirmed`. Additionally resets gateway session state (`gateway`, `gw_start_attempted`, `ib_connect_attempted`) via the `_broker_last` key change (`"IBKR:paper"` → `"IBKR:live"`).

### Daily loss limit

| Component | Details |
|---|---|
| Configured in | AutoTrader section (env var `AT_DAILY_LOSS_LIMIT`) and Portfolio Mode form |
| Passed to | `MultiTrader(daily_loss_limit=...)` and `PortfolioManager(daily_loss_limit=...)` |
| Enforcement | In `MultiTrader.start()` — raises if `realized_losses() >= limit > 0` |
| Display | AutoTrader page: `mt.realized_losses()` metric; Portfolio Mode page: `pm.realized_losses()` metric |
| Reset | Clears with session state when broker/mode changes |

### Error handling patterns

| Pattern | Where | Behavior |
|---|---|---|
| **User-facing error + stop** | Broker connection failure | `st.error(msg)` then `st.stop()` |
| **User-facing error** | Order submission, chart, quick invest | `st.error(msg)` — page continues |
| **Validation error** | Scanner filter inputs, `TraderConfig` | `except ValueError` → `st.error()` → `st.stop()` |
| **Silent failure** | Alternate account data, IB reconnect | `except Exception: pass` |
| **Batch error collection** | Quick Invest, attach positions | Collect in list; display summary after loop |
| **Debug log only** | IBKR historical data per symbol | `logging.debug(...)` — user sees no error |
| **Stall warning** | AutoTrader page, feed heartbeat | `st.warning(...)` when `last_poll_at` lag > 3× poll_interval |

---

## Data Contracts

### `fetch_bars()` → `pd.DataFrame`

| Column | Type | Notes |
|---|---|---|
| `open` | float64 | |
| `high` | float64 | |
| `low` | float64 | |
| `close` | float64 | |
| `volume` | int64 | |
| index | DatetimeIndex | timezone-aware, ascending |

Returns `None` if the response is empty or any exception occurs.

### `score_symbol(bars, spy_rets, filters)` contract

**Input requirements:**
- `bars` must contain columns: `close`, `high`, `low`, `volume`
- `len(bars) >= 52` — returns `None` otherwise
- `spy_rets` optional dict with keys `"5d"` and `"20d"` (floats); defaults to 0 if absent

**Output dict keys (all present on success, `None` on hard-filter failure):**

| Key | Type |
|---|---|
| `Price` | float (2dp) |
| `RSI` | float (1dp) |
| `1d Ret%` | float (2dp) |
| `5d Ret%` | float (2dp) |
| `20d Ret%` | float (2dp) |
| `RS vs SPY` | float (2dp) |
| `Vol/Avg` | float (2dp) |
| `ATR%` | float (2dp) |
| `MACD+` | bool |
| `ADV $M` | float (1dp) |
| `_score` | float (2dp) — internal; dropped from `scan()` output |

### `scan()` → `Tuple[pd.DataFrame, int, int]`

Returns a 3-tuple: `(df, skipped_history, skipped_no_data)`.

- `df` — Index: `Symbol` (str). Columns: all `score_symbol()` output keys except `_score`. Sorted by score descending, trimmed to `top_n`. Returns empty `pd.DataFrame()` if nothing passes filters.
- `skipped_history` — number of symbols that had data but fewer than 52 bars (insufficient history for scoring)
- `skipped_no_data` — number of symbols for which Alpaca returned no data at all

**No-data / rate-limit handling:** SPY missing → `spy_rets` defaults to `{}` (RS treated as 0). Per-symbol errors return `None` from `fetch_bars()`; symbol is silently skipped. No retry logic; relies on Alpaca client's built-in rate limiting.

### `ReplayPriceFeed` boundary behaviour

- **Exhausted (index past end):** `get_price()` returns the last bar's price — does **not** raise. Check `feed.exhausted` before calling.
- **No bars at all:** `get_price()` returns `0.0`.

### `SyntheticPriceFeed` boundary behaviour

- Runs indefinitely (no bar limit).
- Price floor: `max(0.01, round(price, 2))` — never goes negative or zero.

### `MockBroker` JSON resilience

- **File missing:** Creates parent directories and a fresh `{"sessions": []}` structure.
- **File corrupted / `json.JSONDecodeError`:** Falls back to empty sessions; corrupted data is silently discarded.
- **Atomicity:** Writes to temp file first, then renames — prevents half-written files.

### `daily_loss.json` write safety

`core.save_daily_loss()` uses an atomic write: data is written to `daily_loss.tmp` then renamed to `daily_loss.json`. This prevents a half-written file if the process crashes mid-write.
