"""IBKRDataClient — minimal shim matching Alpaca's StockHistoricalDataClient interface."""
import logging
import pandas as pd
from datetime import datetime as _dt

logger = logging.getLogger(__name__)


class IBKRDataClient:
    """Minimal shim matching Alpaca's StockHistoricalDataClient interface."""

    def __init__(self, ib) -> None:
        self._ib = ib

    def get_stock_bars(self, req):
        from ib_async import Stock, util

        ib = self._ib
        symbols = req.symbol_or_symbols
        single = isinstance(symbols, str)
        if single:
            symbols = [symbols]
        start = getattr(req, "start", None)
        end = getattr(req, "end", None)
        tf_str = str(getattr(req, "timeframe", "Day"))
        is_minute = "Minute" in tf_str or "minute" in tf_str
        if is_minute:
            bar_size = "1 min"
            days = max(1, (end - start).days + 1) if (start and end) else 1
        else:
            bar_size = "1 day"
            if start and end:
                days = max(1, (end - start).days + 5)
            elif start:
                days = max(1, (_dt.now() - start).days + 5)
            else:
                days = 90
        end_str = end.strftime("%Y%m%d %H:%M:%S") if end else ""
        dur_str = f"{days} D"
        frames = []
        for sym in symbols:
            contract = Stock(sym, "SMART", "USD")
            try:
                bars = ib.reqHistoricalData(
                    contract, endDateTime=end_str, durationStr=dur_str,
                    barSizeSetting=bar_size, whatToShow="TRADES",
                    useRTH=True, formatDate=1, keepUpToDate=False,
                )
                if bars:
                    df = util.df(bars)
                    col = "date" if "date" in df.columns else df.columns[0]
                    df = df.rename(columns={col: "timestamp"})
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    df["symbol"] = sym
                    df = df.set_index(["symbol", "timestamp"])
                    frames.append(df)
            except Exception as _exc:
                logger.debug(f"IBKR hist fetch {sym}: {_exc}")
        combined = pd.concat(frames) if frames else pd.DataFrame()

        class _Res:
            def __init__(self, df):
                self.df = df

        return _Res(combined)
