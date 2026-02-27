import ccxt
import pandas as pd
from .config import settings

def _mk_exchange():
    ex_cls = getattr(ccxt, settings.EXCHANGE)
    return ex_cls({"enableRateLimit": True})

EX = _mk_exchange()

def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
    market = f"{symbol}/{settings.QUOTE}"
    ohlcv = EX.fetch_ohlcv(market, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df.set_index("ts", inplace=True)
    return df