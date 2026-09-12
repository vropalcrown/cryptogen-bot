"""
CryptoGen Market Regime Detector

Classifies current market conditions into 4 regimes and adjusts
trading aggression automatically:

  BULL_RUN  → Aggressive: lower entry threshold, bigger positions
  RECOVERY  → Normal: standard rules apply
  CRAB      → Conservative: higher threshold, smaller positions
  BEAR/CRASH → Defensive: skip most trades, capital preservation
  
Uses multiple timeframe SOL price data + on-chain volume signals.
"""

import httpx
import pandas as pd
import time
import os
import json
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

REGIME_HISTORY_FILE = os.path.join(os.path.dirname(__file__), "regime_history.json")


class MarketRegimeDetector:
    def __init__(self):
        self.current_regime = "UNKNOWN"
        self.regime_confidence = 0.0
        self.sol_prices_1h = []
        self.sol_prices_4h = []
        self.regime_history = []
        self._load_history()

    def _load_history(self):
        if os.path.exists(REGIME_HISTORY_FILE):
            try:
                with open(REGIME_HISTORY_FILE, "r") as f:
                    self.regime_history = json.load(f)
            except Exception:
                self.regime_history = []

    def _save_history(self):
        # Keep last 200 regime readings
        self.regime_history = self.regime_history[-200:]
        with open(REGIME_HISTORY_FILE, "w") as f:
            json.dump(self.regime_history, f)

    async def detect_regime(self) -> dict:
        """
        Fetches multi-timeframe SOL price data and classifies market regime.
        Returns regime info + aggression parameters.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Fetch 1h candles (last 24h = 24 candles)
                res_1h = await client.get(
                    "https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=1h&limit=24"
                )
                # Fetch 4h candles (last 3 days = 18 candles)
                res_4h = await client.get(
                    "https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=4h&limit=18"
                )

                if res_1h.status_code == 200:
                    self.sol_prices_1h = [float(k[4]) for k in res_1h.json()]
                if res_4h.status_code == 200:
                    self.sol_prices_4h = [float(k[4]) for k in res_4h.json()]

        except Exception:
            pass

        if len(self.sol_prices_1h) < 6:
            return self._build_result("UNKNOWN", 0.0)

        # === Compute indicators ===
        closes_1h = pd.Series(self.sol_prices_1h)
        closes_4h = pd.Series(self.sol_prices_4h) if self.sol_prices_4h else closes_1h

        current_price = closes_1h.iloc[-1]

        # EMAs
        ema_9 = closes_1h.ewm(span=9, adjust=False).mean().iloc[-1]
        ema_21 = closes_1h.ewm(span=21, adjust=False).mean().iloc[-1]

        # Price changes
        change_1h = ((current_price - closes_1h.iloc[-2]) / closes_1h.iloc[-2]) * 100
        change_6h = ((current_price - closes_1h.iloc[-7]) / closes_1h.iloc[-7]) * 100 if len(closes_1h) >= 7 else 0.0
        change_24h = ((current_price - closes_1h.iloc[0]) / closes_1h.iloc[0]) * 100

        # Volatility (1h std / mean)
        volatility = (closes_1h.std() / closes_1h.mean()) * 100

        # Trend strength: how many of last 6 candles were green
        green_candles = sum(1 for i in range(max(0, len(closes_1h)-6), len(closes_1h))
                          if i > 0 and closes_1h.iloc[i] > closes_1h.iloc[i-1])

        # === Classify regime ===
        regime, confidence = self._classify(
            current_price, ema_9, ema_21,
            change_1h, change_6h, change_24h,
            volatility, green_candles
        )

        self.current_regime = regime
        self.regime_confidence = confidence

        # Log to history
        self.regime_history.append({
            "timestamp": time.time(),
            "regime": regime,
            "confidence": confidence,
            "sol_price": current_price,
            "change_24h": round(change_24h, 2)
        })
        self._save_history()

        return self._build_result(regime, confidence)

    def _classify(
        self, price, ema_9, ema_21,
        change_1h, change_6h, change_24h,
        volatility, green_candles
    ) -> tuple:
        """Returns (regime_name, confidence)."""

        # CRASH: Severe drop
        if change_6h < -8.0 or change_24h < -15.0:
            return "CRASH", min(0.95, abs(change_24h) / 20.0)

        # BEAR: Sustained downtrend
        if (price < ema_9 < ema_21) and change_24h < -3.0 and green_candles <= 2:
            return "BEAR", 0.75

        # BULL_RUN: Strong uptrend with momentum
        if (price > ema_9 > ema_21) and change_24h > 3.0 and green_candles >= 4:
            return "BULL_RUN", min(0.90, change_24h / 10.0)

        # RECOVERY: Coming off a dip, turning bullish
        if price > ema_9 and change_6h > 1.0 and change_24h > 0:
            return "RECOVERY", 0.60

        # CRAB: Low volatility, no clear direction
        if volatility < 1.5 and abs(change_24h) < 3.0:
            return "CRAB", 0.70

        # Default: mild conditions
        if change_24h >= 0:
            return "RECOVERY", 0.50
        else:
            return "CRAB", 0.50

    def _build_result(self, regime: str, confidence: float) -> dict:
        """Builds regime result with aggression parameters."""

        # Aggression profiles per regime
        profiles = {
            "BULL_RUN": {
                "ml_threshold": 0.55,       # Lower bar — more trades in bull
                "kelly_multiplier": 1.5,     # Bigger positions
                "max_concurrent": 4,         # More open trades
                "scan_interval_secs": 30,    # Scan more frequently
                "description": "Strong uptrend — aggressive mode"
            },
            "RECOVERY": {
                "ml_threshold": 0.65,
                "kelly_multiplier": 1.0,
                "max_concurrent": 3,
                "scan_interval_secs": 45,
                "description": "Market recovering — normal mode"
            },
            "CRAB": {
                "ml_threshold": 0.82,        # Higher bar — picky in crab (≥82%)
                "kelly_multiplier": 0.5,      # Smaller positions
                "max_concurrent": 1,         # Only 1 trade open in sideways chop
                "scan_interval_secs": 60,
                "description": "Sideways market — high conviction sniper mode (≥82%)"
            },
            "BEAR": {
                "ml_threshold": 0.88,         # Very high bar (≥88%)
                "kelly_multiplier": 0.25,     # Tiny positions
                "max_concurrent": 1,
                "scan_interval_secs": 120,
                "description": "Downtrend — defensive mode, capital preservation"
            },
            "CRASH": {
                "ml_threshold": 0.95,         # Almost never trade
                "kelly_multiplier": 0.1,
                "max_concurrent": 0,          # No new trades
                "scan_interval_secs": 300,
                "description": "CRASH — trading halted, protect capital"
            },
            "UNKNOWN": {
                "ml_threshold": 0.70,
                "kelly_multiplier": 0.8,
                "max_concurrent": 2,
                "scan_interval_secs": 60,
                "description": "Unknown conditions — cautious mode"
            }
        }

        profile = profiles.get(regime, profiles["UNKNOWN"])

        emoji = {
            "BULL_RUN": "🟢🚀", "RECOVERY": "🟡📈", "CRAB": "🟠🦀",
            "BEAR": "🔴📉", "CRASH": "⛔💥", "UNKNOWN": "⚪❓"
        }.get(regime, "⚪")

        return {
            "regime": regime,
            "confidence": round(confidence, 2),
            "emoji": emoji,
            **profile
        }

    def get_regime_trend(self) -> str:
        """Analyzes recent regime history for trend shifts."""
        if len(self.regime_history) < 3:
            return "INSUFFICIENT_DATA"

        recent = [h["regime"] for h in self.regime_history[-5:]]

        # Detect regime transitions
        if recent[-1] == "BULL_RUN" and recent[0] in ("BEAR", "CRAB", "CRASH"):
            return "TURNING_BULLISH"
        if recent[-1] in ("BEAR", "CRASH") and recent[0] in ("BULL_RUN", "RECOVERY"):
            return "TURNING_BEARISH"
        if len(set(recent)) == 1:
            return f"STABLE_{recent[0]}"

        return "TRANSITIONING"
