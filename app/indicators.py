import numpy as np
import pandas as pd

def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rs = up.ewm(alpha=1/n, adjust=False).mean() / (down.ewm(alpha=1/n, adjust=False).mean() + 1e-12)
    return 100 - (100 / (1 + rs))

def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    m = ema(close, fast) - ema(close, slow)
    sig = ema(m, signal)
    hist = m - sig
    return m, sig, hist

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def stoch_kdj(df: pd.DataFrame, k: int = 9, d: int = 3, j: int = 3):
    low_min = df["low"].rolling(k).min()
    high_max = df["high"].rolling(k).max()
    rsv = (df["close"] - low_min) / (high_max - low_min + 1e-12) * 100
    K = rsv.ewm(alpha=1/d, adjust=False).mean()
    D = K.ewm(alpha=1/j, adjust=False).mean()
    J = 3*K - 2*D
    return K, D, J

def zscore(series: pd.Series, n: int = 50) -> pd.Series:
    mean = series.rolling(n).mean()
    std = series.rolling(n).std(ddof=0)
    return (series - mean) / (std + 1e-12)