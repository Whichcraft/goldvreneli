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

# Liquid universe — large/mid-cap US equities across sectors
UNIVERSE = [
    # Tech
    "AAPL", "MSFT", "NVDA", "AMD", "GOOGL", "META", "AMZN", "TSLA",
    "ORCL", "CRM", "ADBE", "NOW", "SNOW", "PANW", "CRWD", "NET",
    # Finance
    "JPM", "BAC", "GS", "MS", "V", "MA", "AXP", "BX", "KKR",
    # Health
    "LLY", "UNH", "JNJ", "ABBV", "MRK", "PFE", "AMGN", "GILD",
    # Energy
    "XOM", "CVX", "COP", "OXY", "SLB", "EOG",
    # Consumer
    "COST", "HD", "NKE", "SBUX", "MCD", "TGT", "WMT", "AMZN",
    # Industrial
    "CAT", "DE", "BA", "GE", "HON", "RTX", "LMT",
    # ETFs
    "SPY", "QQQ", "IWM", "XLK", "XLF", "XLE", "XLV", "GLD", "SLV",
]

# De-duplicate
UNIVERSE = list(dict.fromkeys(UNIVERSE))


def fetch_bars(data_client, symbol: str, days: int = 60) -> Optional[pd.DataFrame]:
    """Fetch daily bars for a symbol using Alpaca data client."""
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    try:
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=datetime.now() - timedelta(days=days),
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


def scan(data_client, top_n: int = 10, progress_cb=None) -> pd.DataFrame:
    """
    Scan UNIVERSE, apply filters, return top_n candidates sorted by score.

    progress_cb : optional callable(done, total) for progress updates
    """
    results = []
    total = len(UNIVERSE)

    for i, symbol in enumerate(UNIVERSE):
        if progress_cb:
            progress_cb(i + 1, total)

        bars = fetch_bars(data_client, symbol)
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
