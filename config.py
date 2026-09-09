import os
from dotenv import load_dotenv

load_dotenv()

# Mode Setting: Read directly from .env (False = Live Real On-Chain Mode)
PAPER_TRADING = os.getenv("PAPER_TRADING", "False").lower() in ("true", "1")  

# Solana Network Configuration
RPC_ENDPOINT = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
PRIVATE_KEY = os.getenv("SOLANA_PRIVATE_KEY", "")

# Risk Parameters (Exact CryptoGen Rules)
STARTING_BALANCE_INR = 100.0
TARGET_BALANCE_INR = 1000.0
SOL_TO_INR_ESTIMATE = 13000.0   # Current approximate SOL/INR exchange rate

# Milestone Harvest Protocol (At INR 1000)
MILESTONE_PROFIT_SWEEP_INR = 600.0  # INR 100 initial capital recovered + INR 500 profit locked
RESEED_CAPITAL_INR = 400.0          # INR 400 remains in the bot to compound Cycle 2
PERSONAL_WITHDRAWAL_WALLET = os.getenv("PERSONAL_SOLANA_WALLET", "")  # User's personal cold wallet

MAX_POSITION_PERCENT = 0.20     # Rule 1: Max 20% per trade
STOP_LOSS_PERCENT = 0.30        # Rule 2: -30% stop loss
EMERGENCY_RESERVE_INR = 15.0    # Rule 6: ₹15 reserve locked for gas
MAX_SLIPPAGE_BPS = 100          # 1.0% slippage (100 basis points)

# Safety Rules
MIN_LIQUIDITY_USD = 5000.0
MAX_TOP_HOLDER_PERCENT = 15.0
MIN_SAFETY_SCORE = 70.0

# Staged TP Ratios: [price_multiplier, percent_of_initial_tokens_to_sell]
TAKE_PROFIT_STAGES = [
    {"mult": 2.0, "sell_ratio": 0.40},  # Sell 40% at 2x
    {"mult": 5.0, "sell_ratio": 0.30},  # Sell 30% at 5x
    {"mult": 10.0, "sell_ratio": 0.30}  # Sell remaining 30% at 10x
]
