"""
CoinDCX Public Market Data Client

Fetches authentic real-time market data from CoinDCX public REST APIs:
  1. Live Ticker: 24h volume, last price, high/low across all INR pairs
  2. Order Book: Real-time 50-level bid/ask depth
  3. Candles: Historical OHLCV (15m, 1h, 4h, 1d) up to 500 candles
"""

import httpx
import time
from typing import Dict, List, Optional, Any


class CoinDCXClient:
    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout
        self.base_api = "https://api.coindcx.com"
        self.base_public = "https://public.coindcx.com"
        self._cached_ticker = None
        self._last_ticker_time = 0.0

    async def get_ticker(self, max_cache_age_sec: float = 5.0) -> List[Dict[str, Any]]:
        """Fetch 24h ticker for all active markets with short caching."""
        now = time.time()
        if self._cached_ticker and (now - self._last_ticker_time) < max_cache_age_sec:
            return self._cached_ticker

        url = f"{self.base_api}/exchange/ticker"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                res = await client.get(url)
                if res.status_code == 200:
                    self._cached_ticker = res.json()
                    self._last_ticker_time = now
                    return self._cached_ticker
            except Exception as e:
                print(f"⚠️ [CoinDCX Ticker Error] {e}")
        return self._cached_ticker or []

    async def get_inr_markets(self) -> List[Dict[str, Any]]:
        """Returns all INR pairs sorted by 24h volume."""
        tickers = await self.get_ticker()
        inr_tickers = []
        for t in tickers:
            market = t.get("market", "")
            # Filter for primary INR pairs (e.g. SOLINR, BTCINR, ETHINR)
            if market.endswith("INR"):
                try:
                    vol = float(t.get("volume", 0.0) or 0.0)
                    last_price = float(t.get("last_price", 0.0) or 0.0)
                    change = float(t.get("change_24_hour", 0.0) or 0.0)
                    inr_tickers.append({
                        "market": market,
                        "pair": f"I-{market[:-3]}_INR",
                        "symbol": market[:-3],
                        "last_price": last_price,
                        "volume": vol,
                        "change_24h": change,
                        "high": float(t.get("high", 0.0) or 0.0),
                        "low": float(t.get("low", 0.0) or 0.0)
                    })
                except (ValueError, TypeError):
                    continue

        # Sort by highest 24h volume
        inr_tickers.sort(key=lambda x: x["volume"], reverse=True)
        return inr_tickers

    async def get_candles(self, pair: str = "I-SOL_INR", interval: str = "1h", limit: int = 500) -> List[Dict[str, Any]]:
        """
        Fetch historical OHLCV candles from CoinDCX.
        Available intervals: '1m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '1d'.
        Returns list of dicts: [{'open': float, 'high': float, 'low': float, 'close': float, 'volume': float, 'time': int}]
        Chronological order (oldest to newest).
        """
        url = f"{self.base_public}/market_data/candles"
        params = {"pair": pair, "interval": interval, "limit": limit}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                res = await client.get(url, params=params)
                if res.status_code == 200:
                    candles = res.json()
                    if isinstance(candles, list):
                        # CoinDCX returns newest first, reverse so oldest is first for technical indicators
                        candles.reverse()
                        return candles
            except Exception as e:
                print(f"⚠️ [CoinDCX Candles Error for {pair}] {e}")
        return []

    async def get_orderbook(self, pair: str = "I-SOL_INR") -> Dict[str, Any]:
        """
        Fetch 50-level order book depth from CoinDCX.
        Returns {'timestamp': int, 'bids': [(price, qty), ...], 'asks': [(price, qty), ...]}
        """
        url = f"{self.base_public}/market_data/orderbook"
        params = {"pair": pair}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                res = await client.get(url, params=params)
                if res.status_code == 200:
                    data = res.json()
                    bids = data.get("bids", {})
                    asks = data.get("asks", {})
                    
                    # Convert to sorted list of (price, quantity) tuples
                    sorted_bids = sorted(
                        [(float(p), float(q)) for p, q in bids.items()],
                        key=lambda x: x[0],
                        reverse=True
                    )
                    sorted_asks = sorted(
                        [(float(p), float(q)) for p, q in asks.items()],
                        key=lambda x: x[0]
                    )
                    return {
                        "pair": pair,
                        "timestamp": data.get("timestamp", int(time.time() * 1000)),
                        "bids": sorted_bids,
                        "asks": sorted_asks,
                        "best_bid": sorted_bids[0][0] if sorted_bids else 0.0,
                        "best_ask": sorted_asks[0][0] if sorted_asks else 0.0
                    }
            except Exception as e:
                print(f"⚠️ [CoinDCX Orderbook Error for {pair}] {e}")
        return {"pair": pair, "bids": [], "asks": [], "best_bid": 0.0, "best_ask": 0.0}
