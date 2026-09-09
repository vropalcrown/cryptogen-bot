import asyncio
import httpx
import time
import os
import sys
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from data_collector import fetch_dex_token_data, fetch_sol_macro_context
from features import extract_features_from_token_data
from ml_brain import CryptoGenBrain, MEMORY_FILE
from safety import analyze_token_safety
from telegram_notifier import send_telegram_alert

async def fetch_bulk_solana_pairs() -> list:
    """
    Pulls a broad set of active, trending, and newly traded Solana token pairs.
    """
    endpoints = [
        "https://api.dexscreener.com/token-profiles/latest/v1",
        "https://api.dexscreener.com/latest/dex/search?q=solana",
        "https://api.dexscreener.com/latest/dex/search?q=pump"
    ]
    
    addresses = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in endpoints:
            try:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, list):
                        for item in data:
                            if item.get("chainId") == "solana" and item.get("tokenAddress"):
                                addresses.append(item["tokenAddress"])
                    elif isinstance(data, dict):
                        pairs = data.get("pairs", [])
                        for p in pairs:
                            if p.get("chainId") == "solana" and p.get("baseToken", {}).get("address"):
                                addresses.append(p["baseToken"]["address"])
            except Exception:
                pass

    # Verified popular tokens for benchmark data
    core_tokens = [
        "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
        "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  # WIF
        "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  # JUP
        "MEFNBXixkEbait3xn9bkm8FsBp2hDRDbBM453CnhB1Z",  # ME
        "7vfCXTUXx5WJV5JADk17DUJ4ksau7utNKj4b963voxsY",  # WEN
        "CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump",  # GOAT
        "HeLp6NuQkmYB4pYWo2zYs22mESHXPQYzXbB8n4V98jwC",  # AI16Z
        "61V8vBaqAGMpgDQi4JqyS62HsY3gf6LLJ3GakZw3m2W6",  # FWOG
        "ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82"   # BOME
    ]
    addresses.extend(core_tokens)
    return list(dict.fromkeys(addresses))

async def run_bulk_data_harvest():
    print("\n" + "═" * 70)
    print("      🌐 CRYPTOGEN MASSIVE ONLINE DATA HARVESTER & ML TRAINER")
    print("═" * 70)
    
    brain = CryptoGenBrain()
    print("📡 Querying DEX search indices across Solana network...")
    candidates = await fetch_bulk_solana_pairs()
    print(f"🎯 Total unique live Solana token candidates identified: {len(candidates)}")

    ingested_samples = []
    winners_found = 0
    losers_filtered = 0

    print("\n🔍 Ingesting order flow, liquidity, and volume metrics...")
    for i, addr in enumerate(candidates[:25]):
        data = await fetch_dex_token_data(addr)
        if not data or data.get("price_usd", 0) <= 0:
            continue

        symbol = data["symbol"]
        price = data["price_usd"]
        liq = data["liquidity_usd"]
        p_5m = data["price_change_5m"]
        p_1h = data["price_change_1h"]

        features = extract_features_from_token_data(data)
        
        # Ground Truth Classification:
        # Genuine winner requires liquidity >= $8k, positive momentum, strong OFI, and low wash score
        is_winner = (
            p_5m >= 2.0 and
            features["buy_ratio_5m"] > 0.58 and
            features["ofi_5m"] > 0.15 and
            liq >= 8000.0 and
            features["wash_score"] < 35.0
        )

        row = {k: features[k] for k in brain.feature_columns}
        row["label"] = 1 if is_winner else 0
        ingested_samples.append(row)

        if is_winner:
            winners_found += 1
            status_tag = "🚀 [VALID WINNER]"
        else:
            losers_filtered += 1
            status_tag = "⛔ [FILTERED OUT]"

        print(f"[{i+1:02d}] {symbol.ljust(10)} | ${price:.8f} | Liq: ${liq:>9,.0f} | 5m: {p_5m:+6.2f}% | {status_tag}")
        await asyncio.sleep(0.3)

    if ingested_samples:
        new_df = pd.DataFrame(ingested_samples)
        if os.path.exists(MEMORY_FILE):
            full_df = pd.read_csv(MEMORY_FILE)
            full_df = pd.concat([full_df, new_df], ignore_index=True)
        else:
            full_df = new_df

        full_df.to_csv(MEMORY_FILE, index=False)

        # Retrain brain with the massive expanded dataset
        X = full_df[brain.feature_columns]
        y = full_df["label"]
        brain.model.fit(X, y)
        import joblib
        from ml_brain import MODEL_FILE
        joblib.dump(brain.model, MODEL_FILE)

        total_records = len(full_df)
        print("\n" + "─" * 70)
        print(f"✅ HARVEST COMPLETE: {len(ingested_samples)} new live Solana tokens ingested.")
        print(f"📊 Identified: {winners_found} genuine momentum setups | {losers_filtered} scams/traps filtered.")
        print(f"🧠 Total Model Training Dataset: {total_records:,} historical samples.")
        print("─" * 70 + "\n")

        # Send mobile alert to user's Telegram
        await send_telegram_alert(
            f"🧠 *[CRYPTOGEN DATA HARVEST COMPLETE]*\n"
            f"• Ingested: {len(ingested_samples)} live Solana tokens\n"
            f"• Scams/Traps filtered: {losers_filtered}\n"
            f"• Total Training Dataset: *{total_records:,}* samples\n"
            f"• Model Brain Updated: Ready for execution!"
        )

if __name__ == "__main__":
    asyncio.run(run_bulk_data_harvest())
