"""
CryptoGen Quantitative Monte Carlo Simulation Engine
Simulates 10,000 compounding trajectory paths across parameter sets
to find the mathematically optimal configuration for turning INR 100 into INR 1,000.
"""

import numpy as np
import pandas as pd
import time
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ANSI formatting
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"
DIM = "\033[2m"

def simulate_path(
    starting_nw=100.0,
    target_nw=1000.0,
    danger_floor=50.0,
    position_pct=0.20,
    sl_pct=-0.10,
    tp1_pct=0.25,
    tp1_ratio=0.50,
    tp2_pct=0.60,
    tp2_ratio=0.30,
    tp3_pct=2.00,
    win_rate=0.52,
    max_trades=150,
    ata_rent_inr=16.0
):
    """
    Simulates a single trajectory of sequential trades under Solana DEX micro-capital mechanics.
    """
    nw = starting_nw
    trade_count = 0
    peak_nw = starting_nw
    max_dd_pct = 0.0

    while nw < target_nw and nw > danger_floor and trade_count < max_trades:
        trade_count += 1
        pos_size = nw * position_pct
        if pos_size < 5.0:
            pos_size = 5.0

        is_win = np.random.rand() < win_rate

        if is_win:
            # Determine how high the winning runner went
            roll = np.random.rand()
            if roll < 0.60:
                # Stage 1 only hit (+25%), remainder stopped at breakeven
                gain = pos_size * (tp1_pct * tp1_ratio)
            elif roll < 0.90:
                # Stage 1 + Stage 2 hit (+25% and +60%)
                gain = pos_size * (tp1_pct * tp1_ratio + tp2_pct * tp2_ratio)
            else:
                # Moonshot runner hit! Stage 1 + 2 + 3 (+25%, +60%, +200%)
                gain = pos_size * (tp1_pct * tp1_ratio + tp2_pct * tp2_ratio + tp3_pct * 0.20)

            # Deduct standard Solana DEX gas (~₹0.15) & rent reclaimed
            net_gain = gain - 0.15
            nw += net_gain
        else:
            # Loss: Stop-loss triggered or rug pull
            roll = np.random.rand()
            if roll < 0.05:
                # Rare catastrophic flash dump (-50% beyond SL)
                loss = pos_size * 0.50
            else:
                # Standard ratcheted stop-loss hit
                loss = pos_size * abs(sl_pct)

            net_loss = loss + 0.15
            nw -= net_loss

        # Track drawdown
        if nw > peak_nw:
            peak_nw = nw
        dd = ((peak_nw - nw) / peak_nw) * 100.0
        if dd > max_dd_pct:
            max_dd_pct = dd

    hit_target = nw >= target_nw
    hit_ruin = nw <= danger_floor

    return {
        "final_nw": nw,
        "hit_target": hit_target,
        "hit_ruin": hit_ruin,
        "trade_count": trade_count,
        "max_dd_pct": max_dd_pct
    }

def run_monte_carlo_grid(num_simulations=10000):
    print(f"\n{BOLD}{CYAN}{'='*82}")
    print(f"🎲 CRYPTOGEN MONTE CARLO SIMULATION ENGINE — {num_simulations:,} TRIALS PER SET")
    print(f"Goal: ₹100.00 ➔ ₹1,000.00 (Cycle 1) | Danger Floor: ₹50.00 | Solana Micro-DEX")
    print(f"{'='*82}{RESET}\n")

    # Grid of Parameter Sets to evaluate
    parameter_sets = [
        # Set 1: Conservative Sniper (Our Base Setup)
        {"name": "Conservative Sniper (Base)", "pos_pct": 0.20, "sl": -0.10, "tp1": 0.25, "tp2": 0.60, "tp3": 2.00, "win_rate": 0.52},
        # Set 2: Ultra-Defensive (Tight SL, Smaller sizing)
        {"name": "Ultra-Defensive Capital Guard", "pos_pct": 0.15, "sl": -0.08, "tp1": 0.20, "tp2": 0.50, "tp3": 1.50, "win_rate": 0.50},
        # Set 3: Micro-Scalper (Quick exits, frequent trades)
        {"name": "High-Velocity Scalper", "pos_pct": 0.20, "sl": -0.08, "tp1": 0.18, "tp2": 0.40, "tp3": 1.00, "win_rate": 0.55},
        # Set 4: Aggressive Moonshot Hunter
        {"name": "Moonshot Hunter (Wide TP)", "pos_pct": 0.20, "sl": -0.12, "tp1": 0.35, "tp2": 0.90, "tp3": 3.00, "win_rate": 0.46},
        # Set 5: Kelly Heavy (25% allocation)
        {"name": "Kelly Aggressive (25% Size)", "pos_pct": 0.25, "sl": -0.10, "tp1": 0.25, "tp2": 0.60, "tp3": 2.00, "win_rate": 0.52},
        # Set 6: Loose Leash (15% SL, wider room to breathe)
        {"name": "Loose Leash (15% SL)", "pos_pct": 0.20, "sl": -0.15, "tp1": 0.30, "tp2": 0.75, "tp3": 2.50, "win_rate": 0.54},
        # Set 7: Pure Kelly Micro (10% Size - Slow & Steady)
        {"name": "Micro-Allocation (10% Size)", "pos_pct": 0.10, "sl": -0.08, "tp1": 0.25, "tp2": 0.60, "tp3": 2.00, "win_rate": 0.52},
        # Set 8: High Confidence ML Strict (60% Win Rate)
        {"name": "ML High-Selectivity (Strict 90%)", "pos_pct": 0.20, "sl": -0.10, "tp1": 0.25, "tp2": 0.60, "tp3": 2.00, "win_rate": 0.60},
        # Set 9: Bear Market Hardened (Tight risk)
        {"name": "Bear Market Hardened", "pos_pct": 0.15, "sl": -0.07, "tp1": 0.20, "tp2": 0.45, "tp3": 1.20, "win_rate": 0.48}
    ]

    results = []

    for i, p in enumerate(parameter_sets, 1):
        print(f"⏳ Simulating Set #{i}: {BOLD}{p['name']}{RESET} ({num_simulations:,} runs)...", end="\r", flush=True)
        
        target_hits = 0
        ruin_hits = 0
        trade_counts = []
        max_dds = []
        final_nws = []

        for _ in range(num_simulations):
            res = simulate_path(
                starting_nw=100.0,
                target_nw=1000.0,
                danger_floor=50.0,
                position_pct=p["pos_pct"],
                sl_pct=p["sl"],
                tp1_pct=p["tp1"],
                tp2_pct=p["tp2"],
                tp3_pct=p["tp3"],
                win_rate=p["win_rate"],
                max_trades=180
            )
            if res["hit_target"]:
                target_hits += 1
                trade_counts.append(res["trade_count"])
            if res["hit_ruin"]:
                ruin_hits += 1
            max_dds.append(res["max_dd_pct"])
            final_nws.append(res["final_nw"])

        prob_target = (target_hits / num_simulations) * 100.0
        prob_ruin = (ruin_hits / num_simulations) * 100.0
        median_trades = int(np.median(trade_counts)) if trade_counts else 999
        avg_max_dd = float(np.mean(max_dds))
        median_nw = float(np.median(final_nws))

        # Profitability Score = Prob(Target) - 2 * Prob(Ruin)
        score = prob_target - (2.5 * prob_ruin)

        results.append({
            "set_num": i,
            "name": p["name"],
            "pos_size": f"{int(p['pos_pct']*100)}%",
            "sl": f"{int(p['sl']*100)}%",
            "tp_targets": f"+{int(p['tp1']*100)}%/+{int(p['tp2']*100)}%",
            "win_rate": f"{int(p['win_rate']*100)}%",
            "prob_target": prob_target,
            "prob_ruin": prob_ruin,
            "median_trades": median_trades,
            "avg_max_dd": avg_max_dd,
            "score": score
        })

    # Sort results by composite score
    results.sort(key=lambda x: x["score"], reverse=True)

    print(" " * 80, end="\r")  # Clear line
    print(f"{BOLD}{'RANK':<5} {'PARAMETER SET':<30} {'SIZE':<6} {'SL':<6} {'WIN%':<6} {'P(₹1000)':<10} {'P(RUIN)':<10} {'MED TRADES':<11} {'AVG DD'}{RESET}")
    print("-" * 92)

    for rank, r in enumerate(results, 1):
        # Color coding
        if r["prob_target"] >= 75.0:
            target_col = GREEN
        elif r["prob_target"] >= 60.0:
            target_col = CYAN
        else:
            target_col = YELLOW

        if r["prob_ruin"] <= 3.0:
            ruin_col = GREEN
        elif r["prob_ruin"] <= 8.0:
            ruin_col = YELLOW
        else:
            ruin_col = RED

        medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else f"#{rank}"))

        print(
            f"{medal:<5} {r['name']:<30} {r['pos_size']:<6} {r['sl']:<6} {r['win_rate']:<6} "
            f"{target_col}{r['prob_target']:>6.1f}%{RESET}    "
            f"{ruin_col}{r['prob_ruin']:>6.1f}%{RESET}    "
            f"{r['median_trades']:>8}     "
            f"{r['avg_max_dd']:>5.1f}%"
        )

    best = results[0]
    print("-" * 92)
    print(f"\n{BOLD}🏆 MATHEMATICAL OPTIMAL CONFIGURATION:{RESET} {GREEN}{BOLD}{best['name']}{RESET}")
    print(f"• Probability of Compounding ₹100 ➔ ₹1,000: {GREEN}{BOLD}{best['prob_target']:.1f}%{RESET}")
    print(f"• Probability of Hitting Ruin Floor (₹50): {GREEN if best['prob_ruin'] < 5 else RED}{best['prob_ruin']:.1f}%{RESET}")
    print(f"• Median Trades Needed: {CYAN}{best['median_trades']} trades{RESET}")
    print(f"• Average Peak-to-Trough Drawdown: {YELLOW}{best['avg_max_dd']:.1f}%{RESET}\n")

if __name__ == "__main__":
    run_monte_carlo_grid(10000)
