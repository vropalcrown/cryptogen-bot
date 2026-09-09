import asyncio
import sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from bot import CryptoGenBot

async def demonstrate_winning_trade_cycle():
    print("==================================================")
    print("      DEMONSTRATING QUALIFIED AI TRADE ENTRY      ")
    print("==================================================")
    bot = CryptoGenBot()

    # High-momentum candidate passing both Safety & ML
    # We pass live data with bullish breakout metrics
    sample_candidate = {
        "address": "CYBERDOGE11111111111111111111111111111111111",
        "name": "CyberDoge",
        "symbol": "CYBERDOGE",
        "price_usd": 0.00001500,
        "liquidity_usd": 45000.0,
        "fdv": 150000.0,
        "volume_5m": 8500.0,
        "volume_1h": 25000.0,
        "price_change_5m": 6.5,
        "price_change_1h": 28.0,
        "buys_5m": 85,
        "sells_5m": 15,
        "buys_1h": 320,
        "sells_1h": 80
    }

    from features import extract_features_from_token_data
    features = extract_features_from_token_data(sample_candidate)
    win_prob = bot.brain.predict_win_probability(features)

    print(f"\nEvaluating Breakout Candidate: {sample_candidate['name']} (${sample_candidate['symbol']})")
    print(f"   Price: ${sample_candidate['price_usd']:.8f} | Liquidity: ${sample_candidate['liquidity_usd']:,.2f}")
    print(f"   Buy Ratio (5m): {features['buy_ratio_5m']*100:.1f}% | Vol Accel: {features['vol_acceleration']:.2f}x")
    print(f"🧠 [AI Model Analysis] Win Probability: {win_prob*100:.1f}%")

    # If probability is above 60%, execute trade
    if win_prob >= 0.60:
        print(f"✅ [AI CONFIDENCE {win_prob*100:.1f}% >= 60%] Trade Approved! Executing position...")
        # Open position
        size_inr = bot.calculate_position_size()
        bot.portfolio_inr -= size_inr
        entry_price = sample_candidate["price_usd"]
        tokens_bought = (size_inr / 13000.0) / entry_price

        bot.active_positions[sample_candidate["address"]] = {
            "token": sample_candidate["symbol"],
            "entry_price": entry_price,
            "invested_inr": size_inr,
            "remaining_tokens": tokens_bought,
            "initial_tokens": tokens_bought,
            "features": features,
            "stop_loss_price": entry_price * 0.70,
            "tp_stages": [
                {"mult": 2.0, "price": entry_price * 2.0, "ratio": 0.40, "hit": False},
                {"mult": 5.0, "price": entry_price * 5.0, "ratio": 0.30, "hit": False},
                {"mult": 10.0, "price": entry_price * 10.0, "ratio": 0.30, "hit": False}
            ]
        }
        print(f"🎯 [BUY EXECUTED] Invested: ₹{size_inr:.2f} | Remaining Cash: ₹{bot.portfolio_inr:.2f}")

        # Tick 1: Hits 2x
        print("\n--- EVENT 1: Hits 2x (+100%) ---")
        await bot.update_market_prices({sample_candidate["address"]: entry_price * 2.05})
        bot.display_portfolio_summary()

        # Tick 2: Hits 5x
        print("\n--- EVENT 2: Hits 5x (+400%) ---")
        await bot.update_market_prices({sample_candidate["address"]: entry_price * 5.10})
        bot.display_portfolio_summary()

        # Tick 3: Hits 10x
        print("\n--- EVENT 3: Hits 10x Moonshot (+900%) ---")
        await bot.update_market_prices({sample_candidate["address"]: entry_price * 10.20})
        bot.display_portfolio_summary()

if __name__ == "__main__":
    asyncio.run(demonstrate_winning_trade_cycle())
