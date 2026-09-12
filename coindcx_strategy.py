"""
CoinDCX Quantitative Strategy Engine

Computes multi-timeframe quantitative signals and win probability:
  1. RSI(14) - Momentum & oversold bounce identification
  2. EMA(20) vs EMA(50) - Trend alignment and dynamic support
  3. Order Book Imbalance (OBI) - 50-level bid/ask depth pressure
  4. Volume Expansion - Breakout acceleration vs 20-period moving average
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional


def calculate_rsi(closes: List[float], period: int = 14) -> List[float]:
    """Calculate standard Wilder's RSI."""
    if len(closes) < period + 1:
        return [50.0] * len(closes)

    series = pd.Series(closes)
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-12)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0).tolist()


def calculate_ema(closes: List[float], period: int) -> List[float]:
    """Calculate Exponential Moving Average."""
    if len(closes) < period:
        return closes[:]
    return pd.Series(closes).ewm(span=period, adjust=False).mean().tolist()


def calculate_orderbook_imbalance(orderbook: Dict[str, Any], depth_levels: int = 30) -> Dict[str, float]:
    """
    Computes Order Book Imbalance (OBI) from top bids vs asks:
    OBI = (Bid Volume - Ask Volume) / (Bid Volume + Ask Volume)
    Range: [-1.0 (100% sell pressure), +1.0 (100% buy pressure)]
    """
    bids = orderbook.get("bids", [])[:depth_levels]
    asks = orderbook.get("asks", [])[:depth_levels]

    bid_vol = sum(q for _, q in bids)
    ask_vol = sum(q for _, q in asks)
    total_vol = bid_vol + ask_vol

    if total_vol <= 0:
        return {"obi": 0.0, "bid_vol": 0.0, "ask_vol": 0.0, "bid_ask_ratio": 1.0}

    obi = (bid_vol - ask_vol) / total_vol
    ratio = bid_vol / max(1e-6, ask_vol)

    return {
        "obi": round(float(obi), 4),
        "bid_vol": round(float(bid_vol), 4),
        "ask_vol": round(float(ask_vol), 4),
        "bid_ask_ratio": round(float(ratio), 2)
    }


class CoinDCXStrategy:
    def __init__(self, entry_confidence_threshold: float = 0.75):
        self.entry_threshold = entry_confidence_threshold

    def analyze_market(self, candles: List[Dict[str, Any]], orderbook: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Takes historical candles and live order book depth.
        Computes technical indicators and returns win probability score.
        """
        if len(candles) < 55:
            return {
                "signal": "WAIT",
                "win_probability": 0.30,
                "reason": "Insufficient candle history (<55 candles)"
            }

        closes = [float(c["close"]) for c in candles]
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        volumes = [float(c["volume"]) for c in candles]

        curr_price = closes[-1]
        prev_close = closes[-2]

        # 1. Indicator Calculations
        rsi_series = calculate_rsi(closes, period=14)
        curr_rsi = rsi_series[-1]
        prev_rsi = rsi_series[-2]

        ema20_series = calculate_ema(closes, period=20)
        ema50_series = calculate_ema(closes, period=50)
        curr_ema20 = ema20_series[-1]
        curr_ema50 = ema50_series[-1]

        # 2. Volume Expansion
        vol_window = volumes[-21:-1]
        avg_vol = np.mean(vol_window) if vol_window else volumes[-1]
        curr_vol = volumes[-1]
        vol_accel = curr_vol / max(1e-6, avg_vol)

        # 3. Order Book Imbalance
        obi_metrics = {"obi": 0.0, "bid_ask_ratio": 1.0}
        if orderbook:
            obi_metrics = calculate_orderbook_imbalance(orderbook)

        obi = obi_metrics["obi"]
        ratio = obi_metrics["bid_ask_ratio"]

        # 4. Quantitative Scoring Rules
        score = 0.35  # Base market probability

        # Rule A: Trend Alignment
        trend_bullish = curr_ema20 > curr_ema50
        price_above_ema50 = curr_price >= curr_ema50 * 0.99
        if trend_bullish and price_above_ema50:
            score += 0.15  # In structural uptrend

        # Rule B: RSI Mean Reversion / Dip Bounce
        if curr_rsi < 35:
            # Deep oversold dip
            score += 0.20
            if curr_rsi > prev_rsi:
                score += 0.05  # Turning up out of oversold
        elif 35 <= curr_rsi <= 52 and curr_rsi > prev_rsi:
            # Healthy pullback bounce in uptrend
            score += 0.12
        elif curr_rsi > 70:
            # Overbought exhaustion penalty
            score -= 0.15

        # Rule C: Order Book Depth Support
        if obi > 0.20:
            score += 0.15  # Solid buy wall
        elif obi > 0.05:
            score += 0.08
        elif obi < -0.20:
            score -= 0.15  # Heavy sell wall

        # Rule D: Volume Confirmation
        if vol_accel >= 1.5:
            score += 0.10
        elif vol_accel >= 1.1:
            score += 0.05

        # Rule E: Green Reversal Candle
        if curr_price > prev_close:
            score += 0.05

        win_prob = round(float(np.clip(score, 0.05, 0.95)), 4)

        # Determine Signal
        reasons = []
        if trend_bullish:
            reasons.append("Uptrend (EMA20>50)")
        if curr_rsi < 40:
            reasons.append(f"Oversold (RSI={curr_rsi:.1f})")
        if obi > 0.10:
            reasons.append(f"Buy Wall (OBI={obi:+.2f})")
        if vol_accel > 1.2:
            reasons.append(f"Vol {vol_accel:.1f}x")

        signal = "BUY" if win_prob >= self.entry_threshold else "WAIT"

        return {
            "signal": signal,
            "win_probability": win_prob,
            "required_threshold": self.entry_threshold,
            "current_price": curr_price,
            "rsi": round(curr_rsi, 2),
            "ema20": round(curr_ema20, 2),
            "ema50": round(curr_ema50, 2),
            "trend": "BULLISH" if trend_bullish else "BEARISH",
            "obi": obi,
            "bid_ask_ratio": ratio,
            "volume_accel": round(vol_accel, 2),
            "reasons": reasons
        }
