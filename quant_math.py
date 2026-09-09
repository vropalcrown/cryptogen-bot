import numpy as np

# =====================================================================
#                   QUANTITATIVE MATHEMATICS ENGINE
# =====================================================================

# Solana On-Chain Cost Constants
ATA_RENT_EXEMPTION_SOL = 0.00203928  # Exact lamports needed for rent-exempt ATA (2,039,280 lamports)
BASE_TX_FEE_SOL = 0.000005          # 5,000 lamports standard signature fee
AVERAGE_PRIORITY_FEE_SOL = 0.00005   # Typical priority fee for fast inclusion

def calculate_amm_price_impact(trade_sol: float, pool_sol_liquidity: float) -> float:
    """
    Computes exact constant-product AMM price impact (x * y = k):
    Price Impact = dx / (x + dx)
    """
    if pool_sol_liquidity <= 0:
        return 1.0  # 100% price impact (empty pool)
    return trade_sol / (pool_sol_liquidity + trade_sol)

def detect_wash_trading(volume_1h_usd: float, liquidity_usd: float, price_change_1h_pct: float) -> dict:
    """
    Market Manipulation Detection: Wash Trading.
    In meme tokens, scammers churn volume between 2 bot wallets to spoof DEX rankings.
    Indicator: Huge volume relative to liquidity pool, but price doesn't expand accordingly.
    """
    if liquidity_usd <= 0:
        return {"manipulated": True, "wash_score": 100.0, "reason": "Zero liquidity"}

    vol_to_liq_ratio = volume_1h_usd / liquidity_usd
    abs_price_move = abs(price_change_1h_pct)

    # If volume is > 15x total liquidity but price changed less than 8%, wash trading is active
    is_wash = (vol_to_liq_ratio > 15.0) and (abs_price_move < 8.0)
    wash_score = min(100.0, (vol_to_liq_ratio / (1.0 + abs_price_move * 0.1)) * 10.0)

    return {
        "manipulated": is_wash,
        "wash_score": round(wash_score, 1),
        "vol_to_liq_ratio": round(vol_to_liq_ratio, 2),
        "reason": "Abnormal volume-to-liquidity churn with negligible price velocity" if is_wash else "Natural organic trading flow"
    }

def calculate_holder_concentration_hhi(top_holders_pct: list) -> dict:
    """
    Herfindahl-Hirschman Index (HHI) for wallet concentration:
    HHI = sum(share_i ^ 2)
    High HHI (> 2500) indicates concentrated oligopoly/cabal with high dump vulnerability.
    """
    if not top_holders_pct:
        return {"hhi": 0.0, "safe": True, "risk": "LOW"}
    
    # Calculate HHI on top holders
    hhi = sum([p**2 for p in top_holders_pct[:10]])
    is_safe = (hhi < 1800) and (top_holders_pct[0] <= 15.0)
    
    risk_level = "HIGH" if hhi > 2500 else ("MEDIUM" if hhi > 1500 else "LOW")
    return {
        "hhi": round(hhi, 1),
        "top_wallet_pct": top_holders_pct[0] if top_holders_pct else 0.0,
        "safe": is_safe,
        "risk": risk_level
    }

def calculate_fractional_kelly_size(
    win_probability: float,
    portfolio_inr: float,
    reward_to_risk_ratio: float = 3.33, # Target avg 2.0x (100% gain) vs 30% stop-loss = 1.0 / 0.3 = 3.33
    fraction: float = 0.25,             # Quarter-Kelly for extreme survival safety
    max_cap_pct: float = 0.20           # Strict hardcoded rule: max 20%
) -> float:
    """
    Fractional Kelly Criterion:
    f* = (p * b - q) / b
    where:
      p = probability of winning
      q = 1 - p
      b = reward-to-risk ratio
    """
    p = win_probability
    q = 1.0 - p
    b = reward_to_risk_ratio

    if b <= 0 or p <= 0:
        return 0.0

    raw_kelly = (p * b - q) / b
    if raw_kelly <= 0:
        return 0.0  # Mathematical negative expected value -> do not trade

    # Apply fractional Kelly (Quarter-Kelly)
    adjusted_kelly = raw_kelly * fraction

    # Cap at hardcoded maximum rule (20% of portfolio)
    final_pct = min(adjusted_kelly, max_cap_pct)
    return round(portfolio_inr * final_pct, 2)
