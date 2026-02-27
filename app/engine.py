from __future__ import annotations
import pandas as pd
import numpy as np
from .config import settings
from .indicators import sma, rsi, macd, atr, stoch_kdj, zscore

def _slope(s: pd.Series, n: int = 5) -> float:
    # simple slope: last - n-bars-ago
    if len(s) < n + 1:
        return 0.0
    return float(s.iloc[-1] - s.iloc[-(n+1)])

def analyze(df: pd.DataFrame, symbol: str, timeframe: str) -> dict:
    close = df["close"]

    sma_fast = sma(close, settings.SMA_FAST)
    sma_slow = sma(close, settings.SMA_SLOW)
    sma_trend = sma(close, settings.SMA_TREND)

    r = rsi(close, 14)
    m, sig, hist = macd(close)
    K, D, J = stoch_kdj(df)
    a = atr(df, 14)

    dev = close - sma_fast
    z = zscore(dev, 50)

    last = df.iloc[-1]
    price = float(last["close"])
    atr_now = float(a.iloc[-1]) if not np.isnan(a.iloc[-1]) else 0.0

    trend_up = price > float(sma_trend.iloc[-1]) and _slope(sma_trend.dropna(), 8) > 0
    trend_down = price < float(sma_trend.iloc[-1]) and _slope(sma_trend.dropna(), 8) < 0

    # --- scoring (0..100) ---
    score_buy = 0
    score_sell = 0

    # Trend contribution
    if trend_up:
        score_buy += 25
    if trend_down:
        score_sell += 25

    # MA crossover / alignment
    if float(sma_fast.iloc[-1]) > float(sma_slow.iloc[-1]):
        score_buy += 10
    else:
        score_sell += 10

    # MACD momentum
    if float(hist.iloc[-1]) > 0:
        score_buy += 15
    else:
        score_sell += 15

    # RSI bias
    rsi_now = float(r.iloc[-1])
    if rsi_now < settings.RSI_LOW:
        score_buy += 15
    if rsi_now > settings.RSI_HIGH:
        score_sell += 15

    # KDJ extreme / turn
    j_now = float(J.iloc[-1])
    if j_now < 10:
        score_buy += 10
    if j_now > 90:
        score_sell += 10

    # Mean reversion (Z-score of deviation)
    z_now = float(z.iloc[-1])
    if z_now < -settings.Z_ENTRY:
        score_buy += 15
    if z_now > settings.Z_ENTRY:
        score_sell += 15

    # Mode tweaks
    mode = settings.MODE.upper()
    if mode == "ACCUMULATE_COIN":
        # ưu tiên mua pullback trong trend up
        if trend_up and z_now < -0.6:
            score_buy += 10
        # bán nhẹ hơn
        score_sell = max(0, score_sell - 5)
    else:  # GROW_USDT
        # ưu tiên chốt lời khi quá đà
        if trend_up and (rsi_now > 65 or z_now > 0.8):
            score_sell += 10

    score_buy = int(min(100, score_buy))
    score_sell = int(min(100, score_sell))

    # --- mini chart series (last N closes) ---
    tail = df.tail(120)
    series_times = [ts.isoformat() for ts in tail.index]
    series_closes = [float(c) for c in tail["close"]]

    # --- zones (simple + practical) ---
    # Base pivot = SMA20; zones use ATR bands
    pivot = float(sma_fast.iloc[-1])
    buy_zone = (pivot - 1.2 * atr_now, pivot - 0.4 * atr_now)
    sell_zone = (pivot + 0.4 * atr_now, pivot + 1.2 * atr_now)

    # --- triggers (easy rules) ---
    # BUY trigger: price enters buy_zone AND (hist rising or RSI turns up) AND not in strong downtrend
    hist_now = float(hist.iloc[-1])
    hist_prev = float(hist.iloc[-2]) if len(hist) > 2 else hist_now
    hist_rising = hist_now > hist_prev

    rsi_prev = float(r.iloc[-2]) if len(r) > 2 else rsi_now
    rsi_turn_up = (rsi_prev < rsi_now) and (rsi_now < 55)

    rsi_turn_down = (rsi_prev > rsi_now) and (rsi_now > 45)

    in_buy_zone = buy_zone[0] <= price <= buy_zone[1]
    in_sell_zone = sell_zone[0] <= price <= sell_zone[1]

    buy_trigger = bool(in_buy_zone and (hist_rising or rsi_turn_up) and not trend_down)
    sell_trigger = bool(in_sell_zone and (not hist_rising or rsi_turn_down))

    # Stop suggestion (ATR-based)
    stop_buy = price - settings.ATR_MULT_STOP * atr_now
    stop_sell = price + settings.ATR_MULT_STOP * atr_now

    # Take-profit suggestion: mean reversion back to pivot or opposite band
    tp_buy_1 = pivot
    tp_buy_2 = pivot + 0.9 * atr_now
    tp_sell_1 = pivot
    tp_sell_2 = pivot - 0.9 * atr_now

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "ts": df.index[-1].isoformat(),
        "price": price,
        "mode": mode,
        "trend": "UP" if trend_up else ("DOWN" if trend_down else "SIDE"),
        "score": {"buy": score_buy, "sell": score_sell},
        "indicators": {
            "rsi": round(rsi_now, 2),
            "macd_hist": round(hist_now, 6),
            "kdj_j": round(j_now, 2),
            "z": round(z_now, 3),
            "atr": round(atr_now, 2),
            "pivot_sma20": round(pivot, 2),
            "sma200": round(float(sma_trend.iloc[-1]), 2) if not np.isnan(sma_trend.iloc[-1]) else None,
            # extra indicators for richer UI
            "macd": round(float(m.iloc[-1]), 6),
            "macd_signal": round(float(sig.iloc[-1]), 6),
            "kdj_k": round(float(K.iloc[-1]), 2),
            "kdj_d": round(float(D.iloc[-1]), 2)
        },
        "zones": {
            "buy": [round(buy_zone[0], 2), round(buy_zone[1], 2)],
            "sell": [round(sell_zone[0], 2), round(sell_zone[1], 2)]
        },
        "triggers": {
            "buy": buy_trigger,
            "sell": sell_trigger
        },
        "series": {
            "t": series_times,
            "close": series_closes
        },
        "risk": {
            "stop_buy": round(stop_buy, 2),
            "stop_sell": round(stop_sell, 2),
            "tp_buy": [round(tp_buy_1, 2), round(tp_buy_2, 2)],
            "tp_sell": [round(tp_sell_1, 2), round(tp_sell_2, 2)]
        }
    }