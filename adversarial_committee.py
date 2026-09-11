"""
Adversarial Multi-Agent Investment Committee (Inspired by TauricResearch TradingAgents)

Simulates an institutional trading floor debate before any capital is committed:
  • BullAnalyst: Evaluates momentum, buy flow, whale accumulation, and narrative.
  • BearAnalyst: Aggressively stress-tests liquidity, holder concentration (HHI), wash trading, and insider bundling.
  • RiskOfficer: Holds absolute veto power to protect seed capital and enforces dynamic sizing adjustments.
"""

import time

class BullAnalyst:
    """Advocates for the long thesis, identifying momentum, accumulation, and narrative edge."""

    def evaluate(self, candidate: dict) -> dict:
        features = candidate.get("features", {})
        win_prob = candidate.get("win_prob", candidate.get("win_probability", 0.50))
        meta_bonus = candidate.get("meta_bonus", 0.0)
        whale_bonus = candidate.get("whale_bonus", 0.0)

        score = win_prob * 60.0  # Base 0-60 from ML Brain
        points = []

        buy_ratio = features.get("buy_ratio_5m", 0.5)
        if buy_ratio >= 0.65:
            score += 15.0
            points.append(f"Strong 5m Buy Pressure ({buy_ratio*100:.0f}%)")
        elif buy_ratio >= 0.55:
            score += 8.0
            points.append(f"Positive Buy Ratio ({buy_ratio*100:.0f}%)")

        ofi = features.get("ofi_5m", 0.0)
        if ofi >= 0.5:
            score += 10.0
            points.append(f"Order Flow Inflow (OFI: {ofi:+.2f})")

        vol_accel = features.get("vol_acceleration", 1.0)
        if vol_accel >= 1.8:
            score += 10.0
            points.append(f"Volume Surge Velocity ({vol_accel:.1f}x)")

        if whale_bonus > 0:
            score += 12.0
            points.append("Smart Money / Whale Accumulation Detected")

        if meta_bonus > 0:
            score += 8.0
            points.append("Trending Narrative Meta Alignment")

        # Qlib Formulaic Alpha Factors
        pv_corr = features.get("alpha_pv_corr", 0.0)
        if pv_corr > 0.5:
            score += 8.0
            points.append("Qlib Alpha: Positive Price-Volume Expansion")

        mom_accel = features.get("alpha_momentum_accel", 0.0)
        if mom_accel > 2.5:
            score += 7.0
            points.append(f"Qlib Alpha: Momentum Acceleration (+{mom_accel:.1f}%)")

        thesis = " • ".join(points) if points else "Standard momentum profile"
        return {
            "score": round(min(100.0, score), 1),
            "thesis": thesis,
            "key_drivers": points
        }


class BearAnalyst:
    """Stress-tests every vulnerability, seeking reasons to protect capital from traps."""

    def evaluate(self, candidate: dict, live_data: dict, gas_inr: float, consecutive_losses: int) -> dict:
        score = 15.0  # Base risk floor
        red_flags = []
        features = candidate.get("features", {})

        # 1. Holder Concentration (HHI)
        hhi_data = live_data.get("holder_concentration", {})
        hhi = hhi_data.get("hhi", 0)
        top_wallet = hhi_data.get("top_wallet_pct", 0.0)
        if top_wallet > 15.0:
            score += 35.0
            red_flags.append(f"Top Wallet Holds {top_wallet:.1f}% (High Dump Risk)")
        elif hhi > 2000:
            score += 20.0
            red_flags.append(f"Concentrated Holder Distribution (HHI {hhi:.0f})")

        # 2. Wash Trading Churn
        wash = live_data.get("wash_analysis", {})
        if wash.get("manipulated", False):
            score += 45.0
            red_flags.append(f"Wash Trading Spoofing Detected (Score {wash.get('wash_score', 0)})")
        elif wash.get("vol_to_liq_ratio", 0) > 10.0:
            score += 15.0
            red_flags.append("Abnormal Volume-to-Liquidity Churn")

        # 2.5 Qlib Bearish Alpha Signals
        pv_corr = features.get("alpha_pv_corr", 0.0)
        if pv_corr < -0.5:
            score += 25.0
            red_flags.append("Qlib Alpha: Negative PV Divergence (Distribution Churn)")

        vol_skew = features.get("alpha_vol_skew", 0.0)
        if vol_skew < -0.5:
            score += 20.0
            red_flags.append("Qlib Alpha: Severe Downside Volatility Skew")

        # 3. Micro Liquidity Slippage
        liq = candidate.get("liq", 0)
        if liq < 8000:
            score += 25.0
            red_flags.append(f"Thin Liquidity Pool (${liq:,.0f})")
        elif liq < 15000:
            score += 10.0
            red_flags.append(f"Moderate Liquidity (${liq:,.0f})")

        # 4. Consecutive Loss Chop Context
        if consecutive_losses >= 2:
            score += 20.0
            red_flags.append(f"Sideways Chop Context ({consecutive_losses} consecutive losses)")

        # 5. Network Gas Drain
        if gas_inr > 1.20:
            score += 20.0
            red_flags.append(f"Elevated Solana Gas (₹{gas_inr:.2f})")

        thesis = " • ".join(red_flags) if red_flags else "No critical red flags detected"
        return {
            "score": round(min(100.0, score), 1),
            "thesis": thesis,
            "red_flags": red_flags
        }


class ChiefRiskOfficer:
    """The final decision authority with absolute veto power."""

    def adjudicate(self, candidate: dict, bull: dict, bear: dict, consecutive_losses: int, gas_inr: float) -> dict:
        symbol = candidate.get("symbol", "UNKNOWN")
        addr = candidate.get("addr", "")
        win_prob = candidate.get("win_prob", candidate.get("win_probability", 0.50))

        veto = False
        veto_reason = None

        # VETO RULE 1: Bear Risk Dominates
        if bear["score"] >= 65.0:
            veto = True
            veto_reason = f"Bear Risk Score Too High ({bear['score']}/100): {bear['red_flags'][0] if bear['red_flags'] else 'Excessive downside'}"

        # VETO RULE 2: Net Margin of Safety
        elif (bull["score"] - bear["score"]) < 10.0:
            veto = True
            veto_reason = f"Insufficient Margin of Safety (Bull {bull['score']} vs Bear {bear['score']})"

        # VETO RULE 3: Elevated Loss Streak Caution
        elif consecutive_losses >= 2 and win_prob < 0.78:
            veto = True
            veto_reason = f"Caution Bump Active ({consecutive_losses} losses): Required Conviction >= 78% (Got {win_prob*100:.0f}%)"

        # VETO RULE 4: Gas Spike Drain
        elif gas_inr >= 1.80:
            veto = True
            veto_reason = f"Gas Fee Elevated (₹{gas_inr:.2f} >= ₹1.80 ceiling)"

        # Determine Sizing Multiplier if Approved
        if veto:
            verdict = "VETOED"
            sizing_mult = 0.0
        else:
            verdict = "APPROVED"
            margin = bull["score"] - bear["score"]
            if margin >= 40.0:
                sizing_mult = 1.15
            elif margin >= 25.0:
                sizing_mult = 1.00
            else:
                sizing_mult = 0.85

        return {
            "token": symbol,
            "address": addr,
            "time": time.strftime("%H:%M:%S"),
            "bull_score": bull["score"],
            "bull_thesis": bull["thesis"],
            "bear_score": bear["score"],
            "bear_thesis": bear["thesis"],
            "verdict": verdict,
            "veto_reason": veto_reason,
            "sizing_mult": sizing_mult,
            "net_conviction": round(max(0.0, (bull["score"] - bear["score"]) / 100.0), 2)
        }


class AdversarialCommittee:
    """The coordinated investment committee orchestrator."""

    def __init__(self):
        self.bull = BullAnalyst()
        self.bear = BearAnalyst()
        self.cro = ChiefRiskOfficer()
        self.latest_debate = {
            "token": "None",
            "time": "—",
            "bull_score": 0.0,
            "bull_thesis": "Awaiting candidate scan",
            "bear_score": 0.0,
            "bear_thesis": "Awaiting candidate scan",
            "verdict": "STANDBY",
            "veto_reason": None,
            "sizing_mult": 1.0
        }
        self.debate_history = []

    def conduct_debate(self, candidate: dict, live_data: dict, gas_inr: float = 0.50, consecutive_losses: int = 0) -> dict:
        """Runs the adversarial debate and records outcome."""
        bull_res = self.bull.evaluate(candidate)
        bear_res = self.bear.evaluate(candidate, live_data, gas_inr, consecutive_losses)
        verdict_res = self.cro.adjudicate(candidate, bull_res, bear_res, consecutive_losses, gas_inr)

        self.latest_debate = verdict_res
        self.debate_history.insert(0, verdict_res)
        if len(self.debate_history) > 20:
            self.debate_history.pop()

        return verdict_res
