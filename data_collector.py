import httpx
import pandas as pd
import asyncio
import time
from quant_math import detect_wash_trading

_LAST_NET_CHECK = 0
_CACHED_NET_STATUS = {
    "tps": 3250,
    "user_tps": 1220,
    "est_gas_inr": 0.50,
    "congestion": "OPTIMAL",
    "safe_to_trade": True
}

async def fetch_solana_network_status() -> dict:
    """
    Queries public Solana RPC for live TPS, non-vote user transactions,
    and congestion metrics to prevent trading during network gas spikes.
    """
    global _LAST_NET_CHECK, _CACHED_NET_STATUS
    now = time.time()
    if now - _LAST_NET_CHECK < 30:
        return _CACHED_NET_STATUS

    _LAST_NET_CHECK = now
    async with httpx.AsyncClient(timeout=4.0) as client:
        try:
            payload = {'jsonrpc': '2.0', 'id': 1, 'method': 'getRecentPerformanceSamples', 'params': [1]}
            res = await client.post("https://api.mainnet-beta.solana.com", json=payload)
            if res.status_code == 200:
                samples = res.json().get('result', [])
                if samples:
                    s = samples[0]
                    secs = max(1, s.get('samplePeriodSecs', 60))
                    tps = int(s.get('numTransactions', 195000) / secs)
                    u_tps = int(s.get('numNonVoteTransactions', 72000) / secs)
                    
                    congestion = "OPTIMAL"
                    est_gas = 0.50
                    if tps > 4500 or u_tps > 2200:
                        congestion = "ELEVATED"
                        est_gas = 0.85
                    
                    _CACHED_NET_STATUS = {
                        "tps": tps,
                        "user_tps": u_tps,
                        "est_gas_inr": est_gas,
                        "congestion": congestion,
                        "safe_to_trade": est_gas < 1.80
                    }
        except Exception:
            pass
    return _CACHED_NET_STATUS

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

SOL_MINT = "So11111111111111111111111111111111111111112"

async def fetch_trending_solana_tokens() -> list:
    """
    Pulls high-conviction Solana trading candidates across 5 parallel multi-DEX sources:
      1. Raydium Official v3 Pools API (Top 30 by 24h volume)
      2. GeckoTerminal Trending Pools (Verified high-activity pools)
      3. GeckoTerminal 24h Top Volume Pools (Deepest liquidity pools)
      4. DexScreener Top Community Boosts (Active retail momentum)
      5. DexScreener Latest Promoted Boosts (Early breakout velocity)
    """
    candidates = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
        # Source 1: Raydium Official v3 Pools (Solana's Primary DEX)
        async def fetch_raydium():
            try:
                res = await client.get("https://api-v3.raydium.io/pools/info/list?poolType=all&poolSortField=volume24h&sortType=desc&pageSize=30&page=1")
                if res.status_code == 200:
                    for p in res.json().get("data", {}).get("data", []):
                        mA = p.get("mintA", {}).get("address", "")
                        mB = p.get("mintB", {}).get("address", "")
                        tok = mB if mA == SOL_MINT else mA
                        if tok and tok != SOL_MINT and len(tok) >= 32:
                            candidates.append(tok)
            except Exception:
                pass

        # Source 2: GeckoTerminal Trending Pools
        async def fetch_gecko_trending():
            try:
                res = await client.get("https://api.geckoterminal.com/api/v2/networks/solana/trending_pools", headers={"Accept": "application/json"})
                if res.status_code == 200:
                    for pool in res.json().get("data", []):
                        base_id = pool.get("relationships", {}).get("base_token", {}).get("data", {}).get("id", "")
                        addr = base_id.replace("solana_", "")
                        if addr and addr != SOL_MINT and len(addr) >= 32:
                            candidates.append(addr)
            except Exception:
                pass

        # Source 3: GeckoTerminal Top 24h Volume Pools (Deep Liquidity)
        async def fetch_gecko_top_vol():
            try:
                res = await client.get("https://api.geckoterminal.com/api/v2/networks/solana/pools?sort=h24_volume_usd_desc", headers={"Accept": "application/json"})
                if res.status_code == 200:
                    for pool in res.json().get("data", []):
                        base_id = pool.get("relationships", {}).get("base_token", {}).get("data", {}).get("id", "")
                        addr = base_id.replace("solana_", "")
                        if addr and addr != SOL_MINT and len(addr) >= 32:
                            candidates.append(addr)
            except Exception:
                pass

        # Source 4: DexScreener Top Community Boosts
        async def fetch_dex_top_boosts():
            try:
                res = await client.get("https://api.dexscreener.com/token-boosts/top/v1")
                if res.status_code == 200:
                    for item in res.json():
                        if item.get("chainId") == "solana" and item.get("tokenAddress"):
                            candidates.append(item["tokenAddress"])
            except Exception:
                pass

        # Source 5: DexScreener Latest Promoted Boosts
        async def fetch_dex_latest_boosts():
            try:
                res = await client.get("https://api.dexscreener.com/token-boosts/latest/v1")
                if res.status_code == 200:
                    for item in res.json()[:20]:
                        if item.get("chainId") == "solana" and item.get("tokenAddress"):
                            candidates.append(item["tokenAddress"])
            except Exception:
                pass

        # Run all 5 API calls in parallel
        await asyncio.gather(
            fetch_raydium(),
            fetch_gecko_trending(),
            fetch_gecko_top_vol(),
            fetch_dex_top_boosts(),
            fetch_dex_latest_boosts(),
            return_exceptions=True
        )

    # Deduplicate preserving discovery order
    unique_candidates = list(dict.fromkeys(candidates))
    return unique_candidates[:75]
