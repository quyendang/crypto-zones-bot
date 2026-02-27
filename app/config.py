from pydantic import BaseModel
import os

class Settings(BaseModel):
    EXCHANGE: str = os.getenv("EXCHANGE", "binance")
    QUOTE: str = os.getenv("QUOTE", "USDT")
    SYMBOLS: list[str] = os.getenv("SYMBOLS", "BTC,ETH").split(",")
    TIMEFRAMES: list[str] = os.getenv("TIMEFRAMES", "4h,1d").split(",")
    UPDATE_SECONDS: int = int(os.getenv("UPDATE_SECONDS", "20"))

    # Mode: "GROW_USDT" or "ACCUMULATE_COIN"
    MODE: str = os.getenv("MODE", "GROW_USDT")

    # Risk knobs
    ATR_MULT_STOP: float = float(os.getenv("ATR_MULT_STOP", "1.8"))
    Z_ENTRY: float = float(os.getenv("Z_ENTRY", "1.2"))     # mean-reversion entry z
    Z_EXIT: float = float(os.getenv("Z_EXIT", "0.3"))       # mean-reversion exit z
    RSI_LOW: float = float(os.getenv("RSI_LOW", "35"))
    RSI_HIGH: float = float(os.getenv("RSI_HIGH", "65"))

    # Trend filter
    SMA_FAST: int = int(os.getenv("SMA_FAST", "20"))
    SMA_SLOW: int = int(os.getenv("SMA_SLOW", "50"))
    SMA_TREND: int = int(os.getenv("SMA_TREND", "200"))

    # Database & trading bot
    DATABASE_URL: str | None = os.getenv("DATABASE_URL")
    TRADE_INTERVAL_SECONDS: int = int(os.getenv("TRADE_INTERVAL_SECONDS", "300"))  # 5 minutes
    MIN_DIFF_ETH: float = float(os.getenv("MIN_DIFF_ETH", "100"))
    MIN_DIFF_BTC: float = float(os.getenv("MIN_DIFF_BTC", "2000"))

settings = Settings()