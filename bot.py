import asyncio
import json
import time
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from config import (
    PAPER_TRADING, STARTING_BALANCE_INR, TARGET_BALANCE_INR,
    MAX_POSITION_PERCENT, STOP_LOSS_PERCENT, TAKE_PROFIT_STAGES,
    EMERGENCY_RESERVE_INR, SOL_TO_INR_ESTIMATE
)
from safety import analyze_token_safety
from data_collector import fetch_dex_token_data, fetch_trending_solana_tokens
from features import extract_features_from_token_data
from ml_brain import CryptoGenBrain

class CryptoGenBot:
    def __init__(self):
        self.portfolio_inr = STARTING_BALANCE_INR
        self.active_positions = {}
        self.trade_history = []
        self.trade_counter = 0
        self.brain = CryptoGenBrain()
        print("\n" + "=" * 65)
        print("                 🤖 CRYPTOGEN AUTONOMOUS BOT")
        print("=" * 65)
        print(f" Initial Balance : ₹{self.portfolio_inr:.2f} (Target: ₹{TARGET_BALANCE_INR:.2f})")
        print(f" Mode            : {'PAPER TRADING (Zero Risk Sim)' if PAPER_TRADING else 'LIVE ON-CHAIN TRADING'}")
        print(f" Reserve Kept    : ₹{EMERGENCY_RESERVE_INR:.2f} SOL for gas")
        print("=" * 65 + "\n")

    def calculate_position_size(self) -> float:
        """Rule 1 & 6: Max 20% size while preserving ₹15 reserve."""
        tradeable_capital = max(0.0, self.portfolio_inr - EMERGENCY_RESERVE_INR)
        size = self.portfolio_inr * MAX_POSITION_PERCENT
        return min(size, tradeable_capital)

    async def evaluate_and_trade(self, token_address: str):
        size_inr = self.calculate_position_size()
        if size_inr < 5.0:
            print("⚠️ [Risk Check] Insufficient tradeable capital (below ₹5 minimum).")
            return

        print(f"\n📡 [Market Ingestion] Scanning online data for {token_address}...")
        live_data = await fetch_dex_token_data(token_address)
        if not live_data:
            print(f"❌ Could not retrieve valid DEX pair for {token_address}. Skipping.")
            return

        token_name = live_data["name"]
        token_symbol = live_data["symbol"]
        print(f"   Identified: {token_name} (${token_symbol})")
        print(f"   Price: ${live_data['price_usd']:.8f} | Liquidity: ${live_data['liquidity_usd']:,.2f}")

        # Step 1: Safety Filter Check
        safety = await analyze_token_safety(token_address, live_data)
        if not safety["safe"]:
            print(f"⛔ [SAFETY FAILED] {safety['reason']}. Skipping.")
            return
        print(f"✅ [SAFETY PASSED] {safety['reason']}.")

        # Step 2: Feature Engineering
        features = extract_features_from_token_data(live_data)

        # Step 3: ML Model Prediction
        win_prob = self.brain.predict_win_probability(features)
        print(f"🧠 [AI Model Analysis] Win Probability: {win_prob * 100:.1f}%")
        print(f"   Buy/Sell Ratio (5m): {features['buy_ratio_5m'] * 100:.1f}% | Vol Accel: {features['vol_acceleration']:.2f}x")

        # Threshold required to risk capital: 70%
        if win_prob < 0.70:
            print(f"⛔ [LOW CONFIDENCE] {win_prob * 100:.1f}% < 70.0% threshold. Skipping.")
            return

        # Step 4: Execute Buy
        self.trade_counter += 1
        entry_price = live_data["price_usd"]
        tokens_bought = (size_inr / SOL_TO_INR_ESTIMATE) / entry_price
        self.portfolio_inr -= size_inr

        position = {
            "trade_number": self.trade_counter,
            "token": token_symbol,
            "address": token_address,
            "entry_price": entry_price,
            "invested_inr": size_inr,
            "remaining_tokens": tokens_bought,
            "initial_tokens": tokens_bought,
            "features": features,
            "stop_loss_price": entry_price * (1.0 - STOP_LOSS_PERCENT),
            "tp_stages": [
                {"mult": s["mult"], "price": entry_price * s["mult"], "ratio": s["sell_ratio"], "hit": False}
                for s in TAKE_PROFIT_STAGES
            ]
        }
        self.active_positions[token_address] = position

        trade_log = {
            "trade_number": self.trade_counter,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action": "BUY",
            "token": token_symbol,
            "entry_price": entry_price,
            "invested_inr": round(size_inr, 2),
            "stop_loss_price": round(position["stop_loss_price"], 8),
            "ai_confidence": f"{win_prob * 100:.1f}%",
            "portfolio_cash_left": round(self.portfolio_inr, 2)
        }
        print(f"\n🎯 [ORDER EXECUTED] Bought {token_symbol}!")
        print(json.dumps(trade_log, indent=2))

    async def update_market_prices(self, price_updates: dict):
        """Simulates or applies price updates to test stop-loss and take-profit logic."""
        closed_tokens = []

        for addr, pos in list(self.active_positions.items()):
            current_price = price_updates.get(addr, pos["entry_price"])
            pnl_pct = ((current_price - pos["entry_price"]) / pos["entry_price"]) * 100
            print(f"\n📈 [Tick Update] {pos['token']}: ${current_price:.8f} ({pnl_pct:+.1f}%)")

            # Check Stop Loss (-30%)
            if current_price <= pos["stop_loss_price"]:
                recovered_inr = pos["invested_inr"] * (pos["remaining_tokens"] / max(1e-6, pos["initial_tokens"])) * (current_price / max(1e-12, pos["entry_price"]))
                self.portfolio_inr += recovered_inr
                loss_inr = pos["invested_inr"] - recovered_inr
                print(f"🚨 [STOP LOSS HIT] Sold 100% of {pos['token']}. Realized Loss: -₹{loss_inr:.2f}")
                self.brain.learn_from_trade_result(pos["features"], was_winner=False)
                closed_tokens.append(addr)
                continue

            # Check Staged Take-Profit (2x, 5x, 10x)
            for stage in pos["tp_stages"]:
                if not stage["hit"] and current_price >= stage["price"]:
                    tokens_to_sell = pos["initial_tokens"] * stage["ratio"]
                    tokens_to_sell = min(tokens_to_sell, pos["remaining_tokens"])
                    sold_ratio = tokens_to_sell / max(1e-6, pos["initial_tokens"])
                    proceeds_inr = pos["invested_inr"] * sold_ratio * (current_price / max(1e-12, pos["entry_price"]))
                    self.portfolio_inr += proceeds_inr
                    pos["remaining_tokens"] -= tokens_to_sell
                    stage["hit"] = True
                    print(f"🎯 [TAKE PROFIT {stage['mult']}x HIT] Sold {stage['ratio']*100:.0f}% of {pos['token']}.")
                    print(f"   Realized Cash: +₹{proceeds_inr:.2f} | Current Portfolio: ₹{self.portfolio_inr:.2f}")

            if pos["remaining_tokens"] <= 0.000001:
                print(f"🏆 Position in {pos['token']} completely closed in profit!")
                self.brain.learn_from_trade_result(pos["features"], was_winner=True)
                closed_tokens.append(addr)

        for addr in closed_tokens:
            del self.active_positions[addr]

    def display_portfolio_summary(self):
        print("\n" + "-" * 50)
        print(f"📊 Total Portfolio Cash: ₹{self.portfolio_inr:.2f} / ₹{TARGET_BALANCE_INR:.2f}")
        progress = min(100.0, (self.portfolio_inr / TARGET_BALANCE_INR) * 100)
        print(f"   Target Progress: [{('#' * int(progress // 5)).ljust(20, '-')}] {progress:.1f}%")
        print("-" * 50 + "\n")

async def run_demo():
    bot = CryptoGenBot()

    # Ingest real trending tokens from online Solana DEX profiles
    print("🌐 Fetching live trending Solana token addresses from DexScreener...")
    trending = await fetch_trending_solana_tokens()
    
    # Fallback to popular active Solana tokens if trending is rate-limited
    known_test_tokens = [
        "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  # Jupiter (JUP)
        "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  # WIF
        "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"   # BONK
    ]
    test_tokens = trending if trending else known_test_tokens

    # Evaluate online candidates
    for token_addr in test_tokens[:2]:
        await bot.evaluate_and_trade(token_addr)

    # If any position was opened, demonstrate the tick manager
    if bot.active_positions:
        first_addr = list(bot.active_positions.keys())[0]
        entry = bot.active_positions[first_addr]["entry_price"]
        
        print("\n⏳ Simulating incoming market price ticks...")
        # Tick 1: Price doubles (+100% / 2x)
        await bot.update_market_prices({first_addr: entry * 2.05})
        bot.display_portfolio_summary()
        
        # Tick 2: Price hits 5x target
        await bot.update_market_prices({first_addr: entry * 5.10})
        bot.display_portfolio_summary()
    else:
        print("\nℹ️ No candidate matched strict >70% confidence filter. Capital protected.")
        bot.display_portfolio_summary()

if __name__ == "__main__":
    asyncio.run(run_demo())
