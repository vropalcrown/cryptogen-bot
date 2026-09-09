# CryptoGen Autonomous Solana Trading Bot

An autonomous algorithmic and machine-learning trading agent built for Solana DEX tokens, engineered to turn ₹100 into ₹1,000 through strictly enforced risk management and data-driven pattern recognition.

---

## Folder Structure

```
cryptogen-bot/
├── config.py              # Hardcoded risk rules, TP stages, stop-loss, reserves
├── data_collector.py      # Real-time online data harvester (DexScreener & Binance)
├── features.py            # Feature engineering (order flow, volume surges, liquidity)
├── ml_brain.py            # Random Forest ML model with continuous reinforcement learning
├── safety.py              # RugCheck and DexScreener safety verification
├── bot.py                 # Core autonomous trading agent
├── simulate_trade.py      # Script to test real tokens from online feeds
├── test_lifecycle.py      # Demonstrates full trade lifecycle, staged TP, and ML update
├── requirements.txt       # Python dependencies
└── .env                   # Configuration & private key storage
```

---

## How to Run in Terminal

Navigate to the project folder in your terminal:

```bash
cd "C:\Users\DEVANANDAN K C\.gemini\antigravity\scratch\cryptogen-bot"
```

### 1. Run Live Online DEX Scan
Scans live trending Solana tokens, evaluates safety scores and order flow in real-time, and protects your capital against rugs:

```powershell
python bot.py
```

### 2. Test Full Trade Lifecycle & Staged Take-Profits
Demonstrates an approved AI trade entering with 20% sizing, taking profit at 2x, 5x, and 10x, and reinforcing the machine learning brain:

```powershell
python test_lifecycle.py
```

---

## Hardcoded Risk Management Rules

1. **Max Position Sizing:** Max 20% of current portfolio per trade.
2. **Mandatory Stop-Loss:** Strictly enforced -30% stop loss.
3. **Staged Take-Profit:**
   - **2x:** Sell 40% (secures initial capital).
   - **5x:** Sell 30% (locks significant profit).
   - **10x:** Sell 30% (captures the moonshot).
4. **Emergency Gas Reserve:** ₹15 in SOL is permanently reserved and never traded.
5. **Death Threshold:** If balance drops below ₹20, trading terminates.
6. **Machine Learning Filter:** Requires positive buy pressure ratio and volume acceleration before risking capital.
