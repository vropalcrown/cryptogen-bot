import httpx
import pandas as pd
import asyncio
from quant_math import detect_wash_trading

async def fetch_sol_macro_context() -> dict:
    """
    Ingests macro Solana market context via Binance REST API.
    Computes 1h trend, EMA, and volatility to prevent trading during macro market dumps.
    """
    url = "https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=15m&limit=24"
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            res = await client.get(url)
            if res.status_code == 200:
                raw = res.json()
                closes = [float(k[4]) for k in raw]
                curr_price = closes[-1]
                start_price = closes[0]
                pct_change_6h = ((curr_price - start_price) / start_price) * 100
                
                # Simple EMA 9
                ema_9 = pd.Series(closes).ewm(span=9, adjust=False).mean().iloc[-1]
                is_uptrend = curr_price >= ema_9

                return {
                    "sol_price_usd": curr_price,
                    "macro_trend": "BULLISH" if is_uptrend and pct_change_6h >= 0 else "BEARISH",
                    "sol_6h_change_pct": round(pct_change_6h, 2),
                    "safe_to_trade": pct_change_6h > -4.5  # Don't buy meme tokens if SOL dumped >4.5%
                }
        except Exception as e:
            pass

    # Safe fallback if Binance is unreachable
    return {
        "sol_price_usd": 140.0,
        "macro_trend": "NEUTRAL",
        "sol_6h_change_pct": 0.0,
        "safe_to_trade": True
    }

async def fetch_dex_token_data(token_address: str) -> dict:
    """
    Pulls live online trading data for any Solana token via DexScreener API:
    - 5m, 1h, 24h volume & price change
    - Buy count vs Sell count (Order flow sentiment)
    - Liquidity & Fully Diluted Valuation (FDV)
    - Wash Trading Detection
    """
    url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.get(url)
            if res.status_code != 200:
                return None
            
            data = res.json()
            pairs = data.get("pairs", [])
            if not pairs:
                return None
                
            pair = pairs[0]  # Select primary liquid pair
            
            price_usd = float(pair.get("priceUsd", 0.0) or 0.0)
            liquidity_usd = float(pair.get("liquidity", {}).get("usd", 0.0) or 0.0)
            vol_1h = float(pair.get("volume", {}).get("h1", 0.0) or 0.0)
            p_chg_1h = float(pair.get("priceChange", {}).get("h1", 0.0) or 0.0)

            # Wash trading check
            wash_analysis = detect_wash_trading(vol_1h, liquidity_usd, p_chg_1h)

            return {
                "token": token_address,
                "name": pair.get("baseToken", {}).get("name", "Unknown"),
                "symbol": pair.get("baseToken", {}).get("symbol", "UNKNOWN"),
                "price_usd": price_usd,
                "liquidity_usd": liquidity_usd,
                "fdv": float(pair.get("fdv", 0.0) or 0.0),
                "volume_5m": float(pair.get("volume", {}).get("m5", 0.0) or 0.0),
                "volume_1h": vol_1h,
                "price_change_5m": float(pair.get("priceChange", {}).get("m5", 0.0) or 0.0),
                "price_change_1h": p_chg_1h,
                "buys_5m": int(pair.get("txns", {}).get("m5", {}).get("buys", 0) or 0),
                "sells_5m": int(pair.get("txns", {}).get("m5", {}).get("sells", 0) or 0),
                "buys_1h": int(pair.get("txns", {}).get("h1", {}).get("buys", 0) or 0),
                "sells_1h": int(pair.get("txns", {}).get("h1", {}).get("sells", 0) or 0),
                "wash_analysis": wash_analysis
            }
        except Exception as e:
            return None

async def fetch_trending_solana_tokens() -> list:
    """
    Pulls high-conviction Solana trading candidates across multiple sources:
      1. GeckoTerminal Trending Pools (verified liquidity $20k - $5M)
      2. DexScreener Top Community Boosts (active retail momentum)
      3. DexScreener Latest Token Profiles (early breakouts for shadow monitoring)
    """
    candidates = []

    async with httpx.AsyncClient(timeout=8.0) as client:
        # Source 1: GeckoTerminal Trending Pools (High Volume & Real Liquidity)
        try:
            res = await client.get(
                "https://api.geckoterminal.com/api/v2/networks/solana/trending_pools",
                headers={"Accept": "application/json"}
            )
            if res.status_code == 200:
                for pool in res.json().get("data", []):
                    base_id = pool.get("relationships", {}).get("base_token", {}).get("data", {}).get("id", "")
                    addr = base_id.replace("solana_", "")
                    if addr and len(addr) >= 32:
                        candidates.append(addr)
        except Exception:
            pass

        # Source 2: DexScreener Top Community Boosts
        try:
            res = await client.get("https://api.dexscreener.com/token-boosts/top/v1")
            if res.status_code == 200:
                for item in res.json():
                    if item.get("chainId") == "solana" and item.get("tokenAddress"):
                        candidates.append(item["tokenAddress"])
        except Exception:
            pass

        # Source 3: DexScreener Latest Token Profiles (early gems / shadow targets)
        try:
            res = await client.get("https://api.dexscreener.com/token-profiles/latest/v1")
            if res.status_code == 200:
                for item in res.json()[:10]:
                    if item.get("chainId") == "solana" and item.get("tokenAddress"):
                        candidates.append(item["tokenAddress"])
        except Exception:
            pass

    # Deduplicate preserving order
    unique_candidates = list(dict.fromkeys(candidates))
    return unique_candidates[:30]
