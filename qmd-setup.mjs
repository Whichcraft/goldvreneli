import { createStore } from '@tobilu/qmd'

/** @import { UpdateProgress, EmbedProgress } from '@tobilu/qmd' */

const store = await createStore({
  dbPath: './qmd.sqlite',
  configPath: './qmd.yml',
})

// Global context
await store.setGlobalContext(
  'Streamlit trading dashboard (Python). Supports Alpaca and IBKR brokers. Features: AutoTrader/MultiTrader, PortfolioManager, stock scanner, replay/test mode. Entry: goldvreneli.py (sidebar + dispatch) → pages/.',
)

// source collection
await store.addContext('source', '/', 'Core modules: goldvreneli.py (entry/sidebar), core.py (session store — get_multi_trader/get_portfolio_manager/get_gateway/get_ib), autotrader.py (AutoTrader states: IDLE→ENTERING→WATCHING→SOLD/STOPPED/ERROR; MultiTrader; TraderConfig), portfolio.py (PortfolioManager: start/start_all, slot refill), scanner.py (scan logic, ScanFilters, UNIVERSE_US, UNIVERSE_INTL), replay.py (ReplayPriceFeed + MockBroker for test mode), gateway_manager.py (IB Gateway/IBC lifecycle), ibkr_data.py (IBKRDataClient), activity_tracker.py (log renderer), version.py')

// pages collection
await store.addContext('pages', '/', 'Streamlit page modules — each exports a single render() function. Pages must not import each other; communicate via st.session_state. Pages: autotrader_page, scanner_page, portfolio_page, portfolio_mode_page, test_mode_page, settings_page, help_page')

// tests collection
await store.addContext('tests', '/', 'pytest test suites: test_autotrader.py (69 tests — AutoTrader state machine), test_portfolio.py (10 tests), test_core.py (17 tests — session helpers), test_scanner.py (11 tests — ScanFilters). Run: venv/bin/python -m pytest tests/ -v')

// docs collection
await store.addContext('docs', '/', 'Top-level docs: architecture.md, CHANGELOG.md, README.md, todo.md')

// Index + embed
await store.update({
  onProgress: /** @param {UpdateProgress} p */ ({ collection, file, current, total }) =>
    process.stdout.write(`\r[${collection}] ${current}/${total} ${file}`),
})
console.log()

await store.embed({
  chunkStrategy: 'auto',
  onProgress: /** @param {EmbedProgress} p */ ({ current, total, collection }) =>
    process.stdout.write(`\r[${collection}] embedding ${current}/${total}`),
})
console.log()

await store.close()
console.log('qmd index ready.')
