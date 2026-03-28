"""
Position Scanner — finds 10 good long candidates using technical filters.

Filters applied per symbol:
  - Price above 20-day and 50-day SMA  (uptrend)
  - RSI(14) between 40 and 65          (momentum, not overbought)
  - Volume > 1.5× 20-day avg volume    (interest/participation)
  - Price > $5 and ADV > $5M           (liquidity)
  - 5-day return > 0                   (recent positive momentum)

Uses Alpaca market data (free, no funded account needed).
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)

# Liquid universe — large/mid-cap US equities, ETFs, and ADRs (~600 symbols)
UNIVERSE = [
    # Mega-cap tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "META", "AMZN", "TSLA",
    # Semiconductors
    "AMD", "INTC", "QCOM", "AVGO", "TXN", "MU", "AMAT", "LRCX", "KLAC", "MRVL",
    "ON", "SMCI", "MPWR", "WOLF", "SWKS", "QRVO", "MCHP", "ADI", "NXPI", "STM",
    "ASML", "TSM", "SLAB", "ACLS", "ONTO", "COHU", "FORM",
    # Software / Cloud
    "ORCL", "CRM", "ADBE", "NOW", "SNOW", "DDOG", "MDB", "VEEV", "WDAY", "ZM",
    "HUBS", "TTD", "GTLB", "CFLT", "NET", "OKTA", "ZS", "FTNT", "PANW", "CRWD",
    "S", "CYBR", "TENB", "RPM", "MNDY", "APPN", "PCTY", "PAYC", "COUP", "NCNO",
    "BRZE", "BILL", "SMAR", "BOX", "DOCN", "ESTC", "FROG", "ALTR", "AVLR",
    "GDDY", "WIX", "SQSP", "WEAVE", "ASAN", "AI", "PLTR", "BBAI", "SOUN",
    # Hardware / Networking
    "ANET", "HPE", "DELL", "WDC", "STX", "PSTG", "NTAP", "VIAV", "CIEN",
    "INFN", "CALX", "LITE", "IIVI", "COHR", "NPKI",
    # Internet / E-commerce / Social
    "SHOP", "EBAY", "PINS", "SNAP", "RDDT", "ABNB", "UBER", "LYFT", "DASH",
    "ETSY", "MELI", "SE", "GRAB", "CARG", "YELP", "ANGI", "IAC",
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
    # Healthcare — large pharma
    "LLY", "JNJ", "ABBV", "MRK", "PFE", "BMY", "AZN", "NVO", "SNY", "GSK",
    # Healthcare — biotech
    "AMGN", "GILD", "REGN", "VRTX", "BIIB", "INCY", "MRNA", "BNTX",
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
    # Consumer discretionary — apparel / brands
    "NKE", "LULU", "PVH", "RL", "VFC", "UAA", "UA", "CROX", "DECK",
    "SKX", "ONON", "BIRK", "GOOS",
    # Consumer discretionary — autos
    "F", "GM", "STLA", "TM", "HMC", "RIVN", "LCID", "NIO", "XPEV", "LI",
    "RACE", "HOG", "THRM", "LEA", "MGA", "BWA",
    # Consumer discretionary — travel / lodging
    "MAR", "HLT", "H", "IHG", "WH", "RCL", "CCL", "NCLH", "VAC",
    "TNL", "PLYA", "SOND",
    # Consumer staples
    "PG", "KO", "PEP", "MDLZ", "GIS", "K", "HRL", "SJM", "MKC",
    "PM", "MO", "BTI", "STZ", "BUD", "TAP", "SAM", "MNST", "CELH",
    "CHD", "CLX", "CL", "EL", "COTY", "REV",
    # Industrials — defense
    "LMT", "RTX", "NOC", "GD", "BA", "HII", "TDG", "LDOS", "SAIC", "BAH", "CACI",
    # Industrials — machinery / equipment
    "CAT", "DE", "EMR", "ETN", "PH", "ROK", "XYL", "CARR", "OTIS",
    "MMM", "HON", "GE", "ITW", "DOV", "FTV", "GNRC", "RRX", "AME",
    "ACCO", "CFX", "FELE", "HLIO", "AIRC",
    # Industrials — transport
    "UPS", "FDX", "JBHT", "CSX", "NSC", "UNP", "CNI", "CP",
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
    # International ETFs
    "EFA", "EEM", "VEA", "VWO", "IEFA", "IEMG",
    "EWJ", "EWZ", "EWC", "EWG", "EWU", "EWA", "EWH", "EWY", "EWT",
    "FXI", "MCHI", "KWEB", "CQQQ",
    "INDA", "INDY", "EPI",
]

# De-duplicate
UNIVERSE = list(dict.fromkeys(UNIVERSE))


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


def score_symbol(bars: pd.DataFrame) -> dict:
    """
    Compute technical indicators and return a score dict.
    Returns None if the symbol fails any hard filter.
    """
    if len(bars) < 52:
        return None

    close  = bars["close"]
    volume = bars["volume"]
    high   = bars["high"]
    low    = bars["low"]

    # ── Indicators ────────────────────────────────────────────────────────────
    sma20  = ta.sma(close, length=20).iloc[-1]
    sma50  = ta.sma(close, length=50).iloc[-1]
    rsi    = ta.rsi(close, length=14).iloc[-1]
    avg_vol20 = volume.rolling(20).mean().iloc[-1]
    atr    = ta.atr(high, low, close, length=14).iloc[-1]
    macd_df = ta.macd(close)
    macd_hist = macd_df["MACDh_12_26_9"].iloc[-1] if macd_df is not None else 0

    last_price  = close.iloc[-1]
    ret_5d      = (last_price / close.iloc[-6] - 1) * 100  if len(close) > 6 else 0
    ret_20d     = (last_price / close.iloc[-21] - 1) * 100 if len(close) > 21 else 0
    adv         = last_price * avg_vol20  # avg daily $ volume

    # ── Hard filters ──────────────────────────────────────────────────────────
    if last_price < 5:               return None   # penny stock
    if adv < 5_000_000:             return None   # illiquid
    if last_price < sma20:          return None   # below 20 SMA
    if last_price < sma50:          return None   # below 50 SMA
    if not (40 <= rsi <= 65):       return None   # overbought or weak
    if volume.iloc[-1] < avg_vol20 * 1.5: return None  # low participation
    if ret_5d <= 0:                 return None   # no recent momentum

    # ── Composite score (higher = better) ────────────────────────────────────
    score = (
        ret_5d * 2          # recent momentum
        + ret_20d * 0.5     # medium-term trend
        + (rsi - 40) * 0.3  # RSI quality (prefer 50–65)
        + (macd_hist > 0) * 5  # MACD histogram positive bonus
    )

    return {
        "Price":      round(last_price, 2),
        "SMA20":      round(sma20, 2),
        "SMA50":      round(sma50, 2),
        "RSI":        round(rsi, 1),
        "5d Ret%":    round(ret_5d, 2),
        "20d Ret%":   round(ret_20d, 2),
        "Vol/Avg":    round(volume.iloc[-1] / avg_vol20, 2),
        "ATR":        round(atr, 2),
        "MACD+":      macd_hist > 0,
        "ADV $M":     round(adv / 1_000_000, 1),
        "_score":     round(score, 2),
    }


def scan(data_client, top_n: int = 10, progress_cb=None,
         as_of: Optional[datetime] = None) -> pd.DataFrame:
    """
    Scan UNIVERSE, apply filters, return top_n candidates sorted by score.

    progress_cb : optional callable(done, total) for progress updates
    as_of       : if set, fetch bars ending on this date (historical mode)
    """
    results = []
    total = len(UNIVERSE)

    for i, symbol in enumerate(UNIVERSE):
        if progress_cb:
            progress_cb(i + 1, total)

        bars = fetch_bars(data_client, symbol, as_of=as_of)
        if bars is None:
            continue

        scored = score_symbol(bars)
        if scored:
            scored["Symbol"] = symbol
            results.append(scored)

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    df = df.sort_values("_score", ascending=False).head(top_n)
    df = df.drop(columns=["_score"])
    df = df.set_index("Symbol")
    return df
