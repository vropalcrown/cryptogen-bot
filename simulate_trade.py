import asyncio
import sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from bot import CryptoGenBot

async def run_simulation_cycle():
    print("==================================================")
    print("   TESTING BOT EXECUTION WITH QUALIFIED CANDIDATE  ")
    print("==================================================")
    bot = CryptoGenBot()

    # Liquid verified Solana token: BONK
    bonk_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

    print(f"\nEvaluating Liquid Token BONK ({bonk_mint})...")
    await bot.evaluate_and_trade(bonk_mint)

    if bot.active_positions:
        pos = bot.active_positions[bonk_mint]
        entry = pos["entry_price"]
        
        print("\n--- SIMULATING MARKET MOMENTUM ---")
        # 1. Price surges to 2.1x (TP1 Hit: Sells 40%)
        print("\n[EVENT 1] Token doubles on DEX volume surge (+110%)...")
        await bot.update_market_prices({bonk_mint: entry * 2.10})
        bot.display_portfolio_summary()

        # 2. Price surges to 5.2x (TP2 Hit: Sells 30%)
        print("\n[EVENT 2] Token hits tier-1 exchange listing (+420%)...")
        await bot.update_market_prices({bonk_mint: entry * 5.20})
        bot.display_portfolio_summary()

        # 3. Price crosses 10x Moonshot (TP3 Hit: Sells remaining 30%)
        print("\n[EVENT 3] Full Moonshot captured (+950%)...")
        await bot.update_market_prices({bonk_mint: entry * 10.50})
        bot.display_portfolio_summary()
    else:
        print("\nToken was evaluated by ML model and skipped based on confidence score.")
        bot.display_portfolio_summary()

if __name__ == "__main__":
    asyncio.run(run_simulation_cycle())
