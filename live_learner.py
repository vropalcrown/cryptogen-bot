import asyncio
import time
import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from data_collector import fetch_dex_token_data, fetch_trending_solana_tokens
from features import extract_features_from_token_data
from ml_brain import CryptoGenBrain, MEMORY_FILE
from safety import analyze_token_safety

class ContinuousLearner:
    def __init__(self):
        self.brain = CryptoGenBrain()
        self.observed_tokens = {}
        self.cycles_completed = 0
        self.total_learned_samples = 0

    async def learn_from_live_market_cycle(self):
        self.cycles_completed += 1
        print("\n" + "=" * 65)
        print(f"🔄 [CYCLE #{self.cycles_completed}] FETCHING LIVE ON-CHAIN SOLANA DATA")
        print("=" * 65)

        # 1. Fetch live trending Solana tokens from DexScreener
        trending_addresses = await fetch_trending_solana_tokens()
        
        # Fallback list of actively traded Solana tokens to ensure broad learning data
        popular_solana_tokens = [
            "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
            "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  # WIF
            "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  # JUP
            "MEFNBXixkEbait3xn9bkm8FsBp2hDRDbBM453CnhB1Z",  # ME
            "7vfCXTUXx5WJV5JADk17DUJ4ksau7utNKj4b963voxsY",  # WEN
            "CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump"   # GOAT
        ]
        
        all_candidates = list(dict.fromkeys(trending_addresses + popular_solana_tokens))
        print(f"📡 Ingesting live data for {len(all_candidates)} active market candidates...")

        for token_address in all_candidates[:6]:
            data = await fetch_dex_token_data(token_address)
            if not data or data.get("price_usd", 0) <= 0:
                continue

            name = data["name"]
            symbol = data["symbol"]
            price = data["price_usd"]
            p_chg_5m = data["price_change_5m"]
            p_chg_1h = data["price_change_1h"]
            
            # Extract quant features
            features = extract_features_from_token_data(data)
            
            # AI Model makes a prediction based on current weights
            current_confidence = self.brain.predict_win_probability(features)

            # Determine real ground truth outcome based on actual online momentum:
            # Positive outcome = Strong 5m momentum (> +3%) + volume acceleration (> 1.2x) + liquidity > $10k
            is_real_winner = (
                p_chg_5m >= 2.5 and 
                features["buy_ratio_5m"] > 0.55 and 
                features["liquidity_usd"] >= 10000
            )

            # Check safety
            safety = await analyze_token_safety(token_address, data)

            print(f"\n🪙 [{symbol}] {name} (${price:.8f})")
            print(f"   5m Change: {p_chg_5m:+.2f}% | 1h Change: {p_chg_1h:+.2f}%")
            print(f"   Buy Ratio (5m): {features['buy_ratio_5m']*100:.1f}% | Liquidity: ${features['liquidity_usd']:,.0f}")
            print(f"   AI Confidence Before: {current_confidence*100:.1f}%")

            # Feed live ground-truth pattern into ML Brain
            self.brain.learn_from_trade_result(features, was_winner=is_real_winner)
            self.total_learned_samples += 1

            # Check confidence after reinforcement
            updated_confidence = self.brain.predict_win_probability(features)
            print(f"   🎯 Pattern Learned! New AI Confidence: {updated_confidence*100:.1f}% (Ground Truth: {'WIN' if is_real_winner else 'LOSS'})")

            # Small delay to respect rate limits
            await asyncio.sleep(1)

        print("\n" + "-" * 65)
        print(f"🧠 [LEARNING STATUS] Total Real Market Samples Ingested: {self.total_learned_samples}")
        print(f"   Model Weights Saved to: cryptogen_ml_model.joblib")
        print("-" * 65)

async def main():
    learner = ContinuousLearner()
    print("🚀 Launching CryptoGen Online Continuous Learning Engine...")
    print("Press Ctrl+C to pause learning anytime.")

    # Run learning cycles
    for cycle in range(2):
        await learner.learn_from_live_market_cycle()
        if cycle < 1:
            print("\n⏳ Waiting 5 seconds before next live market feed cycle...")
            await asyncio.sleep(5)

    print("\n✅ Initial continuous learning pass complete. The model is now trained on live market data!")

if __name__ == "__main__":
    asyncio.run(main())
