import httpx
from config import MIN_LIQUIDITY_USD, MAX_TOP_HOLDER_PERCENT, MIN_SAFETY_SCORE
from bundler_detector import analyze_token_bundling

async def analyze_token_safety(token_address: str, live_data: dict = None) -> dict:
    """
    Comprehensive token security:
      1. Minimum liquidity floor
      2. Top holder concentration (RugCheck)
      3. Dev wallet Jito bundle & freeze authority check (Helius on-chain RPC)
    """
    if live_data:
        liquidity = live_data.get("liquidity_usd", 0.0)
        if liquidity < MIN_LIQUIDITY_USD:
            return {
                "safe": False,
                "reason": f"Liquidity ${liquidity:,.2f} is below minimum threshold ${MIN_LIQUIDITY_USD:,.2f}"
            }

    # Dev Bundler & On-Chain Authority Inspection via Helius RPC
    bundle_analysis = await analyze_token_bundling(token_address)
    if bundle_analysis.get("bundled", False):
        return {
            "safe": False,
            "reason": f"⛔ Insider Risk: {bundle_analysis.get('reason')}"
        }

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            rug_url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}/report"
            rug_res = await client.get(rug_url)
            
            if rug_res.status_code == 200:
                rug_data = rug_res.json()
                top_holders = rug_data.get("topHolders", [])
                if top_holders:
                    top_percent = float(top_holders[0].get("pct", 0.0))
                    if top_percent > MAX_TOP_HOLDER_PERCENT:
                        return {
                            "safe": False,
                            "reason": f"Top wallet holds {top_percent:.1f}% (> {MAX_TOP_HOLDER_PERCENT}%)"
                        }
        except Exception:
            pass

    return {"safe": True, "reason": "Passed safety checks"}
