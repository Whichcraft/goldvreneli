"""
Position Scanner — finds top long candidates using technical filters.

Filters (all must pass):
  - Liquidity    : Price > $5, ADV > $5M
  - Trend        : Price within 3% of SMA20, above SMA50
  - RSI(14)      : 35 – 72  (not oversold, not overbought)
  - Volume       : last-day volume ≥ 20-day average (participation)
  - Momentum     : 5-day return > −1%  (not in freefall)

Scoring (higher = better):
  - Relative strength vs SPY (5d, 20d)
  - Absolute momentum (1d, 5d, 10d, 20d returns)
  - RSI quality (prefer 50–65)
  - MACD histogram positive
  - ATR% (prefer moderate volatility)
  - Trend consistency (SMA20 > SMA50 slope)

Fetch: 60 days of daily bars; parallelised with ThreadPoolExecutor.
Uses Alpaca market data (free, no funded account needed).
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


@dataclass
class ScanFilters:
    """Hard-filter thresholds passed to score_symbol / scan."""
    min_price:      float = 5.0    # minimum last price ($)
    min_adv_m:      float = 5.0    # minimum avg daily $ volume (millions)
    rsi_lo:         float = 35.0   # RSI lower bound
    rsi_hi:         float = 72.0   # RSI upper bound
    vol_mult:       float = 1.0    # last volume must be >= vol_mult × avg20
    sma20_tol_pct:  float = 3.0    # allow price up to this % below SMA20
    min_ret_5d:     float = -1.0   # minimum 5-day return (%)

    def __post_init__(self):
        if self.rsi_lo >= self.rsi_hi:
            raise ValueError(f"rsi_lo ({self.rsi_lo}) must be less than rsi_hi ({self.rsi_hi})")
        if self.min_price < 0:
            raise ValueError("min_price must be non-negative")
        if self.min_adv_m < 0:
            raise ValueError("min_adv_m must be non-negative")
        if self.vol_mult < 0:
            raise ValueError("vol_mult must be non-negative")

# ── US universe — US-incorporated equities and US-focused ETFs ─────────────────
UNIVERSE_US = [
    # Mega-cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "META", "AMZN", "TSLA",
    # Semiconductors (US)
    "AMD", "INTC", "QCOM", "AVGO", "TXN", "MU", "AMAT", "LRCX", "KLAC", "MRVL",
    "ON", "SMCI", "MPWR", "WOLF", "SWKS", "QRVO", "MCHP", "ADI", "NXPI",
    "SLAB", "ACLS", "ONTO", "COHU", "FORM",
    # Software / Cloud
    "ORCL", "CRM", "ADBE", "NOW", "SNOW", "DDOG", "MDB", "VEEV", "WDAY", "ZM",
    "HUBS", "TTD", "GTLB", "CFLT", "NET", "OKTA", "ZS", "FTNT", "PANW", "CRWD",
    "S", "CYBR", "TENB", "RPM", "MNDY", "APPN", "PCTY", "PAYC", "COUP", "NCNO",
    "BRZE", "BILL", "SMAR", "BOX", "DOCN", "ESTC", "FROG", "ALTR", "AVLR",
    "GDDY", "WIX", "SQSP", "WEAVE", "ASAN", "AI", "PLTR", "BBAI", "SOUN",
    # Hardware / Networking
    "ANET", "HPE", "DELL", "WDC", "STX", "PSTG", "NTAP", "VIAV", "CIEN",
    "INFN", "CALX", "LITE", "IIVI", "COHR", "NPKI",
    # Internet / E-commerce / Social (US)
    "EBAY", "PINS", "SNAP", "RDDT", "ABNB", "UBER", "LYFT", "DASH",
    "ETSY", "CARG", "YELP", "ANGI", "IAC",
    "TWLO", "SEND", "BAND", "MSGM", "MTCH", "BMBL", "GRINDR",
    # Finance — banks
    "JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC", "TFC", "COF",
    "FITB", "RF", "HBAN", "CFG", "KEY", "MTB", "WAL", "EWBC", "SIVB", "ZION",
    "ALLY", "SYF", "DFS", "OMF", "NAVI",
    # Finance — capital markets / asset mgmt
    "BX", "KKR", "APO", "CG", "BN", "BAM", "ARES", "OWL", "BLUE", "TPG",
    "BLK", "IVZ", "AMG", "VRTS", "VCTR", "STEP",
    # Finance — payments / fintech
    "AXP", "V", "MA", "PYPL", "SQ", "AFRM", "SOFI", "UPST", "LC", "OPEN",
    "COIN", "HOOD", "MKTX", "IBKR", "LPLA",
    # Finance — insurance
    "CB", "AIG", "MET", "PRU", "AFL", "ALL", "PGR", "TRV", "HIG", "L",
    "RE", "RNR", "ACGL", "ERIE", "CINF",
    # Healthcare — large pharma (US)
    "LLY", "JNJ", "ABBV", "MRK", "PFE", "BMY",
    # Healthcare — biotech (US)
    "AMGN", "GILD", "REGN", "VRTX", "BIIB", "INCY", "MRNA",
    "SGEN", "ALNY", "IONS", "EXEL", "HALO", "JAZZ", "ACAD", "SAGE",
    "FOLD", "RARE", "BLUE", "EDIT", "NTLA", "BEAM", "CRSP", "PACB",
    # Healthcare — managed care / services
    "UNH", "CVS", "CI", "HUM", "CNC", "MOH", "ELV", "OSCR",
    "DGX", "LH", "EXAS", "NTRA", "QDEL",
    # Healthcare — equipment / devices
    "ISRG", "MDT", "ABT", "SYK", "BSX", "EW", "ZBH", "HOLX",
    "DXCM", "PODD", "TDOC", "PHR", "NVCR", "NVRO", "SWAV", "INSP",
    "AXNX", "NARI", "TMDX", "ATRC", "SILK",
    # Energy — oil & gas
    "XOM", "CVX", "COP", "OXY", "SLB", "EOG", "PSX", "MPC", "VLO",
    "HES", "DVN", "FANG", "MRO", "APA", "HAL", "BKR", "FTI", "NOV",
    "RIG", "VAL", "HP", "WTTR", "PUMP",
    # Energy — utilities
    "NEE", "D", "DUK", "SO", "AEP", "EXC", "SRE", "PCG", "XEL",
    "ETR", "PPL", "ES", "CNP", "NI", "OGE", "EVRG", "AEE", "WEC",
    # Energy — clean / renewables
    "ENPH", "FSLR", "PLUG", "BEAM", "RUN", "NOVA", "ARRY", "CSIQ",
    "SEDG", "MAXN", "SHLS", "BE", "BLDP", "CWEN",
    # Consumer discretionary — retail
    "COST", "HD", "LOW", "TGT", "WMT", "DLTR", "DG", "BURL", "TJX", "ROST",
    "BBY", "FIVE", "OLLI", "BIG", "PRTY", "BOOT", "CATO", "EXPR",
    # Consumer discretionary — restaurants / leisure
    "MCD", "SBUX", "YUM", "DPZ", "CMG", "DRI", "TXRH", "DENN", "JACK",
    "EAT", "CAKE", "RRGB", "SHAK", "WING", "BROS", "NDLS",
    # Consumer discretionary — apparel / brands (US)
    "NKE", "LULU", "PVH", "RL", "VFC", "UAA", "UA", "CROX", "DECK", "SKX",
    # Consumer discretionary — autos (US)
    "F", "GM", "RIVN", "LCID", "HOG", "THRM", "LEA", "MGA", "BWA",
    # Consumer discretionary — travel / lodging
    "MAR", "HLT", "H", "IHG", "WH", "RCL", "CCL", "NCLH", "VAC",
    "TNL", "PLYA", "SOND",
    # Consumer staples (US)
    "PG", "KO", "PEP", "MDLZ", "GIS", "K", "HRL", "SJM", "MKC",
    "PM", "MO", "STZ", "TAP", "SAM", "MNST", "CELH",
    "CHD", "CLX", "CL", "EL", "COTY", "REV",
    # Industrials — defense
    "LMT", "RTX", "NOC", "GD", "BA", "HII", "TDG", "LDOS", "SAIC", "BAH", "CACI",
    # Industrials — machinery / equipment
    "CAT", "DE", "EMR", "ETN", "PH", "ROK", "XYL", "CARR", "OTIS",
    "MMM", "HON", "GE", "ITW", "DOV", "FTV", "GNRC", "RRX", "AME",
    "ACCO", "CFX", "FELE", "HLIO", "AIRC",
    # Industrials — transport (US)
    "UPS", "FDX", "JBHT", "CSX", "NSC", "UNP",
    "DAL", "UAL", "AAL", "LUV", "ALK", "SAVE",
    "CHRW", "EXPD", "XPO", "SAIA", "ODFL", "WERN", "KNX",
    # Materials
    "LIN", "APD", "ECL", "SHW", "FCX", "NEM", "GOLD", "WPM",
    "AA", "X", "NUE", "STLD", "CLF", "RS", "CMC",
    "DD", "DOW", "LYB", "CE", "EMN", "OLN", "ASH",
    # Real estate
    "AMT", "PLD", "EQIX", "CCI", "SPG", "O", "WELL", "DLR",
    "PSA", "EXR", "CUBE", "LSI", "NSA",
    "AVB", "EQR", "MAA", "UDR", "CPT",
    "VNO", "BXP", "KIM", "REG", "FRT", "NNN",
    # Communication / media
    "T", "VZ", "TMUS", "CHTR", "CMCSA", "NFLX", "DIS", "WBD", "PARA",
    "FOX", "FOXA", "NYT", "IAC", "ZD", "SGRY",
    # Broad & factor ETFs
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "MDY", "IJR", "IWF", "IWD",
    "VUG", "VTV", "MTUM", "QUAL", "USMV", "VLUE",
    # Sector ETFs
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE",
    "SMH", "SOXX", "IGV", "HACK", "CIBR", "BUG",
    "IBB", "XBI", "FBT", "ARKG",
    "ARKK", "ARKW", "ARKF", "ARKQ",
    "KBWB", "KRE", "IAT", "FINX",
    "OIH", "XOP", "AMLP", "TAN", "ICLN", "QCLN",
    "ITB", "XHB", "JETS", "AWAY",
    # Leveraged / inverse ETFs (liquid, use with care)
    "TQQQ", "SQQQ", "UPRO", "SPXU", "SOXL", "SOXS",
    "UVXY", "SVXY", "VXX",
    # Commodity / macro / bond ETFs
    "GLD", "IAU", "SLV", "PPLT", "PALL",
    "GDX", "GDXJ", "SIL", "SILJ",
    "USO", "UCO", "UNG",
    "TLT", "IEF", "SHY", "GOVT", "BND", "AGG",
    "HYG", "JNK", "LQD", "EMB",
    "UUP", "FXE", "FXY", "FXB",
]

# ── International universe (small) — flagship ADRs + broad country ETFs ───────
UNIVERSE_INTL = [
    # Semiconductors (foreign)
    "ASML", "TSM", "STM",
    # Internet / E-commerce (foreign)
    "SHOP", "MELI", "SE", "GRAB",          # Canada, LatAm, SE Asia
    "BIDU", "JD", "PDD",                   # China
    # Technology (foreign)
    "SONY", "SAP",                         # Japan, Germany
    # Healthcare — pharma (foreign)
    "AZN", "NVO", "SNY", "GSK", "BNTX",   # UK, Denmark, France, UK, Germany
    # Autos (foreign)
    "TM", "HMC",                           # Japan
    "STLA", "RACE",                        # Italy/Netherlands
    "NIO", "XPEV", "LI",                   # China
    # Consumer — apparel (foreign)
    "ONON", "BIRK", "GOOS",               # Switzerland, Denmark, Canada
    # Consumer staples (foreign)
    "BUD", "BTI",                          # Belgium, UK
    # Energy (foreign)
    "BP", "SHEL",                          # UK
    # Finance (foreign)
    "SAN", "HSBC", "RY", "TD",            # Spain, UK, Canada, Canada
    # Materials (foreign)
    "BHP", "RIO", "VALE",                  # Australia, UK, Brazil
    # Transport (foreign)
    "CNI", "CP",                           # Canada
    # International / regional ETFs (broad)
    "EFA", "EEM", "VEA", "VWO", "IEFA", "IEMG",
    "EWJ", "EWZ", "EWC", "EWG", "EWU", "EWA", "EWH", "EWY", "EWT",
    "FXI", "MCHI", "KWEB", "CQQQ",
    "INDA", "INDY", "EPI",
]

# ── International universe (full) — comprehensive ADRs across all regions ──────
UNIVERSE_INTL_FULL = UNIVERSE_INTL + [
    # Europe — industrials / diversified
    "ABB",                                 # Switzerland — automation & electrification
    "ERIC", "NOK",                         # Sweden, Finland — telecom equipment
    "PHG",                                 # Netherlands — health tech
    "MT",                                  # Luxembourg — steel
    "FERG", "CRH",                         # UK/Ireland — building products
    # Europe — financials
    "UBS", "CS",                           # Switzerland — banking
    "ING", "AEG",                          # Netherlands — banking, insurance
    "BCS", "LYG", "NWG",                   # UK — banking
    "DB",                                  # Germany — banking
    "KB", "SHG",                           # Korea — banking
    # Europe — healthcare / pharma
    "NVS",                                 # Switzerland — pharma (Novartis)
    "TAK",                                 # Japan — pharma (Takeda)
    # Europe — telecom
    "VOD", "TEF", "ORAN",                  # UK, Spain, France
    # Europe — consumer
    "UL",                                  # UK/Netherlands — consumer goods (Unilever)
    "PSO",                                 # UK — education/media (Pearson)
    # Asia — China
    "BABA", "VIPS", "YUMC",               # e-commerce, Yum China
    "TAL", "EDU",                          # education
    # Asia — Japan
    "CAJ",                                 # Canon
    "SMFG", "MFG",                         # Sumitomo Mitsui, Mizuho
    # Asia — Korea
    "SKM", "KEP",                          # SK Telecom, Korea Electric Power
    # Asia — India
    "INFY", "WIT",                         # Infosys, Wipro — IT services
    "HDB", "IBN",                          # HDFC Bank, ICICI Bank
    # Canada — energy & materials
    "SU", "CNQ", "ENB", "TRP",            # oil sands, pipelines
    "GOLD",                                # Barrick Gold
    # Australia / other
    "WDS",                                 # Woodside Energy (Australia)
    # Country / regional ETFs — extended
    "EWW", "EWS", "EWP", "EWQ", "EWL",   # Mexico, Singapore, Spain, France, Switzerland
    "EWI", "EWN", "EWD", "EWO", "EWK",   # Italy, Netherlands, Sweden, Austria, Belgium
    "EZA", "THD", "EWM",                  # South Africa, Thailand, Malaysia
    "ARGT", "ECH", "EPU",                 # Argentina, Chile, Peru
    "NORW", "EDEN",                        # Norway, Denmark
    "GXC",                                 # China large-cap broad
]
UNIVERSE_INTL_FULL = list(dict.fromkeys(UNIVERSE_INTL_FULL))

# Combined universe — US + full international
UNIVERSE = list(dict.fromkeys(UNIVERSE_US + UNIVERSE_INTL_FULL))


def fetch_bars(data_client, symbol: str, days: int = 60,
               as_of: Optional[datetime] = None) -> Optional[pd.DataFrame]:
    """Fetch daily bars for a symbol using Alpaca data client."""
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    try:
        end = as_of or datetime.now()
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=end - timedelta(days=days),
            end=end,
        )
        bars = data_client.get_stock_bars(req).df
        if bars.empty:
            return None
        bars = bars.reset_index(level=0, drop=True)  # drop symbol index level
        bars = bars.sort_index()
        return bars
    except Exception as e:
        logger.debug(f"Failed to fetch {symbol}: {e}")
        return None


def score_symbol(bars: pd.DataFrame,
                 spy_rets: Optional[Dict[str, float]] = None,
                 filters: Optional[ScanFilters] = None) -> dict:
    """
    Compute technical indicators and return a score dict.
    Returns None if the symbol fails any hard filter.

    spy_rets: dict with keys "5d", "20d" holding SPY returns for RS calculation.
    filters:  ScanFilters instance (uses defaults if None).
    """
    if len(bars) < 52:
        return None

    f = filters or ScanFilters()

    close     = bars["close"]
    volume    = bars["volume"]
    high      = bars["high"]
    low       = bars["low"]

    # ── Indicators ────────────────────────────────────────────────────────────
    sma20     = ta.sma(close, length=20).iloc[-1]
    sma50     = ta.sma(close, length=50).iloc[-1]
    sma20_series = ta.sma(close, length=20)
    sma20_prev = sma20_series.iloc[-6] if len(sma20_series) >= 6 else sma20
    rsi       = ta.rsi(close, length=14).iloc[-1]
    avg_vol20 = volume.rolling(20).mean().iloc[-1]
    atr       = ta.atr(high, low, close, length=14).iloc[-1]
    macd_df   = ta.macd(close)
    macd_col  = next((c for c in (macd_df.columns if macd_df is not None else []) if c.startswith("MACDh")), None)
    macd_hist = macd_df[macd_col].iloc[-1] if macd_col else 0

    last_price = close.iloc[-1]
    ret_1d  = (last_price / close.iloc[-2]  - 1) * 100 if len(close) > 2  else 0
    ret_5d  = (last_price / close.iloc[-6]  - 1) * 100 if len(close) > 6  else 0
    ret_10d = (last_price / close.iloc[-11] - 1) * 100 if len(close) > 11 else 0
    ret_20d = (last_price / close.iloc[-21] - 1) * 100 if len(close) > 21 else 0
    adv     = last_price * avg_vol20
    atr_pct = (atr / last_price) * 100

    # ── Hard filters ──────────────────────────────────────────────────────────
    if last_price < f.min_price:                            return None
    if adv < f.min_adv_m * 1_000_000:                      return None
    if last_price < sma50:                                  return None
    if last_price < sma20 * (1 - f.sma20_tol_pct / 100):   return None
    if not (f.rsi_lo <= rsi <= f.rsi_hi):                   return None
    if volume.iloc[-1] < avg_vol20 * f.vol_mult:            return None
    if ret_5d < f.min_ret_5d:                               return None

    # ── Relative strength vs SPY ───────────────────────────────────────────
    spy = spy_rets or {}
    rs_5d  = ret_5d  - spy.get("5d",  0)
    rs_20d = ret_20d - spy.get("20d", 0)

    # ── Trend consistency ──────────────────────────────────────────────────
    sma_slope = (sma20 - sma20_prev) / sma20_prev * 100 if (sma20_prev and not pd.isna(sma20_prev)) else 0
    above_both = 1 if last_price > sma20 and sma20 > sma50 else 0

    # ── Composite score (higher = better) ────────────────────────────────────
    score = (
        rs_5d  * 3.0           # relative strength last 5 days (most important)
        + rs_20d * 1.0         # relative strength last 20 days
        + ret_5d * 1.0         # absolute 5d momentum
        + ret_10d * 0.5        # 10d momentum
        + ret_20d * 0.3        # 20d trend
        + ret_1d * 0.5         # yesterday's action
        + (rsi - 50) * 0.2     # RSI quality (prefer 50–65)
        + (macd_hist > 0) * 4  # MACD histogram positive
        + above_both * 3       # clean uptrend structure
        + sma_slope * 0.5      # SMA rising
        - max(0, atr_pct - 3) * 0.5  # penalise excessive volatility
    )

    return {
        "Price":      round(last_price, 2),
        "RSI":        round(rsi, 1),
        "1d Ret%":    round(ret_1d, 2),
        "5d Ret%":    round(ret_5d, 2),
        "20d Ret%":   round(ret_20d, 2),
        "RS vs SPY":  round(rs_5d, 2),
        "Vol/Avg":    round(volume.iloc[-1] / avg_vol20, 2),
        "ATR%":       round(atr_pct, 2),
        "MACD+":      macd_hist > 0,
        "ADV $M":     round(adv / 1_000_000, 1),
        "_score":     round(score, 2),
    }


def _batch_fetch(data_client, syms: list, days: int = 60,
                 as_of: Optional[datetime] = None) -> Dict[str, pd.DataFrame]:
    """Fetch daily bars for multiple symbols in a single API call."""
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    try:
        end = as_of or datetime.now()
        req = StockBarsRequest(
            symbol_or_symbols=syms,
            timeframe=TimeFrame.Day,
            start=end - timedelta(days=days),
            end=end,
        )
        df = data_client.get_stock_bars(req).df
        if df.empty:
            return {}
        result = {}
        for sym in syms:
            try:
                sym_df = df.xs(sym, level=0).sort_index()
                if not sym_df.empty:
                    result[sym] = sym_df
            except KeyError:
                pass
        return result
    except Exception as e:
        logger.debug(f"Batch fetch failed for {syms[:3]}…: {e}")
        return {}


def scan(data_client, top_n: int = 10, progress_cb=None,
         as_of: Optional[datetime] = None,
         chunk_size: int = 250,
         filters: Optional[ScanFilters] = None,
         symbols: Optional[list] = None) -> pd.DataFrame:
    """
    Scan symbols, apply filters, return top_n candidates sorted by score.

    progress_cb : optional callable(done, total) for progress updates
    as_of       : if set, fetch bars ending on this date (historical mode)
    chunk_size  : symbols per batch API request (Alpaca supports ~1000)
    filters     : ScanFilters instance (uses defaults if None)
    symbols     : list of tickers to scan (defaults to full UNIVERSE)
    """
    symbols = list(dict.fromkeys(symbols)) if symbols else UNIVERSE
    total   = len(symbols)

    # ── Fetch SPY for relative-strength baseline ───────────────────────────
    spy_bars = fetch_bars(data_client, "SPY", as_of=as_of)
    spy_rets: Dict[str, float] = {}
    if spy_bars is not None and len(spy_bars) > 21:
        c = spy_bars["close"]
        spy_rets["5d"]  = (c.iloc[-1] / c.iloc[-6]  - 1) * 100 if len(c) > 6  else 0
        spy_rets["20d"] = (c.iloc[-1] / c.iloc[-21] - 1) * 100 if len(c) > 21 else 0

    # ── Batch fetch in parallel chunks ────────────────────────────────────
    bars_map: Dict[str, pd.DataFrame] = {}
    chunks = [symbols[i:i + chunk_size] for i in range(0, len(symbols), chunk_size)]
    done = 0
    with ThreadPoolExecutor(max_workers=min(len(chunks), 4)) as ex:
        futs = {ex.submit(_batch_fetch, data_client, chunk, 60, as_of): len(chunk)
                for chunk in chunks}
        for fut in as_completed(futs):
            bars_map.update(fut.result())
            done += futs[fut]
            if progress_cb:
                progress_cb(min(done, total), total)

    # ── Score ──────────────────────────────────────────────────────────────
    results = []
    skipped_history = 0
    for sym, bars in bars_map.items():
        if len(bars) < 52:
            skipped_history += 1
            continue
        scored = score_symbol(bars, spy_rets, filters)
        if scored:
            scored["Symbol"] = sym
            results.append(scored)

    if not results:
        return pd.DataFrame(), skipped_history

    df = pd.DataFrame(results)
    df = df.sort_values("_score", ascending=False).head(top_n)
    df = df.drop(columns=["_score"])
    df = df.set_index("Symbol")
    return df, skipped_history
