import httpx
from config import MIN_LIQUIDITY_USD, MAX_TOP_HOLDER_PERCENT, MIN_SAFETY_SCORE
from bundler_detector import analyze_token_bundling

def check_range_stability(live_data: dict) -> dict:
    """
    Freqtrade-inspired Range Stability Filter:
    Prevents buying tokens caught in erratic sideways ping-pong chop.
    In small accounts (e.g. ₹100 seed), choppy ping-pong action generates false breakouts
    and bleeds capital through repeated stop-losses.
    """
    if not live_data:
        return {"stable": True, "reason": "No live data"}

    p_chg_5m = abs(float(live_data.get("price_change_5m", 0.0)))
    p_chg_1h = abs(float(live_data.get("price_change_1h", 0.0)))
    tx_5m = int(live_data.get("buys_5m", 0) + live_data.get("sells_5m", 0))
    tx_1h = int(live_data.get("buys_1h", 0) + live_data.get("sells_1h", 0))
    vol_5m = float(live_data.get("volume_5m", 0.0))
    liq = float(live_data.get("liquidity_usd", 1.0))

    # Check 1: High frequency micro-chop (lots of trades, zero net direction)
    if tx_5m > 60 and p_chg_5m < 0.25:
        return {
            "stable": False,
            "reason": f"Chop Trap: {tx_5m} txs in 5m with near-zero direction ({p_chg_5m:.2f}%)"
        }

    # Check 2: 1h range compression chop (high churn relative to liquidity, directionless)
    if tx_1h > 350 and p_chg_1h < 0.80 and (vol_5m * 12.0) > (liq * 2.0):
        return {
            "stable": False,
            "reason": f"Range Stagnation: 1h price flat ({p_chg_1h:.1f}%) despite heavy churn"
        }

    return {"stable": True, "reason": "Passed range stability check"}


async def analyze_token_safety(token_address: str, live_data: dict = None) -> dict:
    """
    Comprehensive token security:
      1. Minimum liquidity floor
      2. Freqtrade Range Stability Chop Filter
      3. Top holder concentration (RugCheck)
      4. Dev wallet Jito bundle & freeze authority check (Helius on-chain RPC)
    """
    if live_data:
        liquidity = live_data.get("liquidity_usd", 0.0)
        if liquidity < MIN_LIQUIDITY_USD:
            return {
                "safe": False,
                "reason": f"Liquidity ${liquidity:,.2f} is below minimum threshold ${MIN_LIQUIDITY_USD:,.2f}"
            }

        # Freqtrade Range Stability Filter
        stability = check_range_stability(live_data)
        if not stability["stable"]:
            return {
                "safe": False,
                "reason": f"⚠️ {stability['reason']}"
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
