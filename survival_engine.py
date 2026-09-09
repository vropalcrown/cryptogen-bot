"""
CryptoGen Capital Survival Engine (Automaton Architecture)

Inspired by Conway Automaton's sovereign agent survival tiers, adapted
for micro-capital Solana on-chain trading to eliminate fee bleed.

Tiers:
  - EXPANSION (INR >= 250): Compound mode. Max 2 positions. Generous Kelly.
  - NORMAL (INR 100 - 249): Standard operational mode. Full ML scan.
  - DEFENSE (INR 50 - 99):  Capital conservation. Cuts position size by 50%.
                            Raises ML confidence bar to 85%+. Requires $15k+ pool.
  - CRITICAL (INR < 50):    Emergency survival. Halts normal trades.
                            Protects gas reserve. Only acts on 92%+ ultra setups.
"""

from dataclasses import dataclass

@dataclass
class SurvivalTierConfig:
    tier: str
    emoji: str
    min_confidence: float
    max_position_pct: float
    max_concurrent_trades: int
    min_liquidity_usd: float
    description: str

def evaluate_survival_tier(net_worth_inr: float) -> SurvivalTierConfig:
    """
    Evaluates current net worth and returns the active survival policy.
    """
    if net_worth_inr >= 250.0:
        return SurvivalTierConfig(
            tier="EXPANSION",
            emoji="💎🚀",
            min_confidence=0.70,
            max_position_pct=0.25,
            max_concurrent_trades=2,
            min_liquidity_usd=10000.0,
            description="Compounding profits. Multiple positions permitted."
        )
    elif net_worth_inr >= 100.0:
        return SurvivalTierConfig(
            tier="NORMAL",
            emoji="🟢🎯",
            min_confidence=0.75,
            max_position_pct=0.25,
            max_concurrent_trades=1,
            min_liquidity_usd=8000.0,
            description="Nominal operation. Strict sniper entry (25% optimal size)."
        )
    elif net_worth_inr >= 50.0:
        return SurvivalTierConfig(
            tier="DEFENSE",
            emoji="🟡🛡️",
            min_confidence=0.85,
            max_position_pct=0.22,  # 22% optimal size to defeat Solana gas fee drag
            max_concurrent_trades=1,
            min_liquidity_usd=15000.0,  # Require deeper pools to reduce slippage
            description="Capital conservation. 22% optimal sizing. High conviction bar (85%+)."
        )
    else:
        return SurvivalTierConfig(
            tier="CRITICAL",
            emoji="🔴🛑",
            min_confidence=0.92,
            max_position_pct=0.05,
            max_concurrent_trades=0,  # Halt normal trading to protect gas reserve
            min_liquidity_usd=25000.0,
            description="Survival lockdown. Normal trading suspended to save gas reserve."
        )
