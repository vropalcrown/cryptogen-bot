import asyncio
import json
import time
import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from config import (
    STARTING_BALANCE_INR, TARGET_BALANCE_INR,
    STOP_LOSS_PERCENT, TAKE_PROFIT_STAGES,
    EMERGENCY_RESERVE_INR, SOL_TO_INR_ESTIMATE, PAPER_TRADING,
    PERSONAL_WITHDRAWAL_WALLET, COMPOUNDING_LADDER
)
from quant_math import (
    ATA_RENT_EXEMPTION_SOL, BASE_TX_FEE_SOL, AVERAGE_PRIORITY_FEE_SOL,
    calculate_amm_price_impact, calculate_fractional_kelly_size,
    calculate_holder_concentration_hhi
)
from safety import analyze_token_safety
from data_collector import fetch_dex_token_data, fetch_trending_solana_tokens, fetch_sol_macro_context
from features import extract_features_from_token_data
from ml_brain import CryptoGenBrain
from onchain_executor import SolanaOnChainExecutor, SOL_MINT
from ata_reclaimer import ATARentReclaimer
from telegram_notifier import send_telegram_alert, poll_telegram_commands

# === NEW INTELLIGENCE MODULES ===
from trade_journal import TradeJournal
from market_regime import MarketRegimeDetector
from meta_tracker import MetaTracker
from survival_engine import evaluate_survival_tier
from news_sentinel import NewsSentinel
from whale_tracker import WhaleTracker


class AutonomousDemoTrader:
    def __init__(self):
        # === Core Systems ===
        self.brain = CryptoGenBrain()
        self.executor = SolanaOnChainExecutor()
        self.reclaimer = ATARentReclaimer()

        # === NEW: Intelligence Systems ===
        self.journal = TradeJournal()
        self.regime_detector = MarketRegimeDetector()
        self.meta_tracker = MetaTracker()
        self.news_sentinel = NewsSentinel()
        self.whale_tracker = WhaleTracker()

        # === Regime state (will be updated before first trade) ===
        self.current_regime = {
            "regime": "UNKNOWN", "ml_threshold": 0.65,
            "kelly_multiplier": 1.0, "max_concurrent": 3,
            "description": "Initializing..."
        }
        self.journal_weights = {}

        # Verify Live On-Chain Balance
        from wallet_manager import check_wallet_balance_onchain
        onchain_bal = check_wallet_balance_onchain(self.executor.wallet_pubkey) if self.executor.wallet_pubkey else {"sol": 0.0}
        self.live_sol_balance = onchain_bal.get("sol", 0.0)

        self.portfolio_inr = STARTING_BALANCE_INR
        self.locked_ata_rent_inr = 0.0
        self.active_positions = {}
        self.trade_history = []
        self.wins = 0
        self.losses = 0
        self.trade_counter = 0
        self.session_start = time.time()

        # Compounding Ladder Tracking
        self.current_cycle_idx = 0  # Starts at Cycle 1 (index 0)
        self.is_danger_halted = False
        self.is_paused = False  # Controlled via Telegram /pause and /resume

        # Track last known macro state for journal
        self.last_macro_change = 0.0

        self.is_live = (not PAPER_TRADING) and (self.live_sol_balance > 0.001)
        mode_str = f"LIVE ON-CHAIN (Balance: {self.live_sol_balance:.4f} SOL)" if self.is_live else "PAPER SIMULATION (Awaiting SOL Deposit)"
        ladder_stage = COMPOUNDING_LADDER[self.current_cycle_idx]
        print("\n" + "=" * 70)
        print("      ⚡ CRYPTOGEN v2 — INTELLIGENT AUTONOMOUS TRADER ⚡")
        print("=" * 70)
        print(f" Execution Mode     : {mode_str}")
        print(f" Burner Address     : {self.executor.wallet_pubkey}")
        print(f" Compounding Cycle  : Cycle #{ladder_stage['cycle']} (Goal: INR {ladder_stage['seed_inr']:.0f} -> INR {ladder_stage['target_inr']:.0f})")
        print(f" Danger Floor       : INR {ladder_stage['danger_floor_inr']:.0f} (Emergency freeze if breached)")
        print(f" Harvest Policy     : Lock INR {ladder_stage['profit_sweep_inr']:.0f} | Re-seed INR {ladder_stage['reseed_inr']:.0f}")
        print(f" Smart Brain v2     : Ensemble RF+GBM | Adaptive Threshold | RL")
        print(f" Survival Engine    : Conway Automaton Dynamic Risk Throttling")
        if not self.is_live and not PAPER_TRADING:
            print(f"\n! [NOTICE] Real Mode enabled, but burner wallet has 0.0000 SOL.")
            print(f"  Deposit SOL to: {self.executor.wallet_pubkey}")
            print("   Running paper trading simulation while awaiting deposit...")
        print("=" * 70 + "\n")

    def get_total_net_worth(self) -> float:
        """Returns liquid cash + refundable ATA rent + market value of open positions."""
        position_value = sum([
            pos["remaining_tokens"] * pos["entry_price"] * SOL_TO_INR_ESTIMATE
            for pos in self.active_positions.values()
        ])
        return self.portfolio_inr + self.locked_ata_rent_inr + position_value

    def get_current_ladder_stage(self) -> dict:
        """Returns the current active cycle config from COMPOUNDING_LADDER."""
        idx = min(self.current_cycle_idx, len(COMPOUNDING_LADDER) - 1)
        return COMPOUNDING_LADDER[idx]

    async def check_danger_floor(self) -> bool:
        """
        Safety Checkpoint:
        If current net worth drops below the cycle's danger floor (e.g. INR 100 in Cycle 2),
        immediately freeze all trading and alert the user via Telegram.
        """
        stage = self.get_current_ladder_stage()
        danger_floor = stage["danger_floor_inr"]
        total_nw = self.get_total_net_worth()

        if total_nw <= danger_floor and not self.is_danger_halted:
            self.is_danger_halted = True
            print("\n" + "🚨" * 35)
            print(f"🛑 [DANGER FLOOR BREACHED] Net worth INR {total_nw:.2f} <= Danger Floor INR {danger_floor:.2f}!")
            print(f"   Trading HALTED to protect remaining capital in Cycle #{stage['cycle']}.")
            print("🚨" * 35 + "\n")

            await send_telegram_alert(
                f"🚨 *[DANGER FLOOR HALT - CYCLE #{stage['cycle']}]*\n"
                f"• *Current Net Worth:* INR {total_nw:.2f}\n"
                f"• *Danger Floor:* INR {danger_floor:.2f}\n"
                f"• *Status:* Trading FROZEN immediately to preserve remaining capital!\n"
                f"• Manual review required before resuming."
            )
            return True
        return self.is_danger_halted

    async def check_milestone_harvest(self):
        """
        Geometric Compounding Ladder Milestone Protocol:
        When total net worth reaches the target for the current cycle:
          1. Closes any remaining open positions
          2. Reclaims all ATA rent deposits
          3. Sweeps profit into safe reserve / cold wallet
          4. Advances to the next cycle and re-seeds the new starting capital
          5. Saves the winning ML model weights as 'golden_checkpoint_cycle_X.joblib'
          6. Sends a celebratory Telegram alert with details
        """
        stage = self.get_current_ladder_stage()
        target = stage["target_inr"]
        total_nw = self.get_total_net_worth()

        if total_nw >= target:
            cycle_num = stage["cycle"]
            print("\n" + "🎉" * 35)
            print(f"🏆 [CYCLE #{cycle_num} COMPLETED] NET WORTH HIT INR {total_nw:.2f} (>= INR {target:.2f})!")
            print("🎉" * 35)

            # 1. Close open positions to lock gains
            if self.active_positions:
                print(f"🔒 Closing {len(self.active_positions)} active position(s) to lock cycle profit...")
                for addr, pos in list(self.active_positions.items()):
                    await self.executor.execute_swap(addr, SOL_MINT, int(pos["remaining_tokens"] * 1_000_000), paper_mode=(not self.is_live))
                    self.reclaimer.reclaim_rent(addr, paper_mode=(not self.is_live))
                    self.portfolio_inr += (pos["remaining_tokens"] * pos["entry_price"] * SOL_TO_INR_ESTIMATE) + pos["ata_locked_inr"]
                self.active_positions.clear()
                self.locked_ata_rent_inr = 0.0

            # 2. Permanent Model Checkpoint
            import shutil
            golden_path = os.path.join(os.path.dirname(__file__), f"golden_checkpoint_cycle_{cycle_num}.joblib")
            src_model = os.path.join(os.path.dirname(__file__), "cryptogen_ml_model.joblib")
            if os.path.exists(src_model):
                shutil.copyfile(src_model, golden_path)
                print(f"💾 [GOLDEN MODEL SAVED] Cycle #{cycle_num} ML weights saved to: {os.path.basename(golden_path)}")

            # 3. Harvest & Re-Seed
            profit_sweep = stage["profit_sweep_inr"]
            reseed_capital = stage["reseed_inr"]
            self.portfolio_inr = reseed_capital
            self.is_danger_halted = False  # Reset danger status for new cycle

            # Advance to next ladder cycle
            if self.current_cycle_idx < len(COMPOUNDING_LADDER) - 1:
                self.current_cycle_idx += 1
                next_stage = self.get_current_ladder_stage()
                next_info = f"Cycle #{next_stage['cycle']} initialized with INR {reseed_capital:.0f} (Target: INR {next_stage['target_inr']:.0f}, Danger Floor: INR {next_stage['danger_floor_inr']:.0f})"
            else:
                next_info = "Ultimate ladder cycle completed! Bot awaiting creator instructions."

            sol_harvest = profit_sweep / SOL_TO_INR_ESTIMATE
            dest_msg = f"Sent to {PERSONAL_WITHDRAWAL_WALLET[:8]}..." if PERSONAL_WITHDRAWAL_WALLET else "Locked in cold reserve"

            print(f"\n💰 [CYCLE #{cycle_num} HARVEST SUMMARY]")
            print(f"   • Profit Secured & Locked Away : INR {profit_sweep:.2f} (~{sol_harvest:.4f} SOL)")
            print(f"   • Re-Seed Working Balance      : INR {reseed_capital:.2f}")
            print(f"   • Next Stage                   : {next_info}")
            print(f"   • Status                       : {dest_msg}")
            print("-" * 65 + "\n")

            await send_telegram_alert(
                f"🏆 *[CYCLE #{cycle_num} TARGET CRUSHED!]*\n\n"
                f"💰 *Profit Locked Away:* INR {profit_sweep:.2f} (~{sol_harvest:.4f} SOL)\n"
                f"🔄 *Next Cycle Seed:* INR {reseed_capital:.2f}\n"
                f"🎯 *Next Goal:* INR {next_stage['target_inr']:.0f}\n"
                f"🛡️ *Next Danger Floor:* INR {next_stage['danger_floor_inr']:.0f}\n"
                f"💾 Winning brain frozen to golden checkpoint."
            )

    async def handle_remote_commands(self):
        """
        Polls Telegram for user remote commands and executes them instantly.
        """
        commands = await poll_telegram_commands()
        for cmd in commands:
            print(f"   📱 [TELEGRAM COMMAND RECEIVED] {cmd}")

            if cmd == "/status":
                stage = self.get_current_ladder_stage()
                total_nw = self.get_total_net_worth()
                regime = self.current_regime.get("regime", "UNKNOWN")
                nr = getattr(self, "news_report", {})
                pause_status = "⏸️ PAUSED" if self.is_paused else "▶️ ACTIVE"
                st = getattr(self, "survival_tier", evaluate_survival_tier(total_nw))

                pos_summary = "\n".join([
                    f"  • {p['token']}: ${p['entry_price']:.8f} (Invested: ₹{p['invested_inr']:.2f})"
                    for p in self.active_positions.values()
                ]) or "  • None (Cash 100% liquid)"

                await send_telegram_alert(
                    f"📊 *[CRYPTOGEN STATUS REPORT]*\n\n"
                    f"• *Status:* {pause_status}\n"
                    f"• *Net Worth:* INR {total_nw:.2f} / Goal: INR {stage['target_inr']:,.0f}\n"
                    f"• *Liquid Cash:* INR {self.portfolio_inr:.2f}\n"
                    f"• *Cycle:* #{stage['cycle']} (Danger Floor: INR {stage['danger_floor_inr']:.0f})\n"
                    f"• *Survival Tier:* {st.emoji} {st.tier}\n"
                    f"• *Market Regime:* {regime}\n"
                    f"• *News Sentiment:* {nr.get('sentiment_label', 'NEUTRAL')}\n"
                    f"• *Win Rate:* {self.wins}W / {self.losses}L\n\n"
                    f"💼 *Open Positions:*\n{pos_summary}"
                )

            elif cmd == "/pause":
                self.is_paused = True
                print("   ⏸️ [BOT PAUSED] New token buying suspended by user.")
                await send_telegram_alert("⏸️ *[BOT PAUSED]* Autonomous buying suspended. Active positions will still be monitored for TP/SL.")

            elif cmd == "/resume":
                self.is_paused = False
                print("   ▶️ [BOT RESUMED] Autonomous buying active.")
                await send_telegram_alert("▶️ *[BOT RESUMED]* Autonomous market scans and buying resumed!")

            elif cmd == "/closeall":
                print("   🚨 [EMERGENCY CLOSE ALL] Selling all active positions...")
                closed_count = len(self.active_positions)
                for addr, pos in list(self.active_positions.items()):
                    await self.executor.execute_swap(addr, SOL_MINT, int(pos["remaining_tokens"] * 1_000_000), paper_mode=(not self.is_live))
                    self.reclaimer.reclaim_rent(addr, paper_mode=(not self.is_live))
                    self.portfolio_inr += (pos["remaining_tokens"] * pos["entry_price"] * SOL_TO_INR_ESTIMATE) + pos["ata_locked_inr"]
                self.active_positions.clear()
                self.locked_ata_rent_inr = 0.0
                await send_telegram_alert(f"🚨 *[EMERGENCY CLOSE ALL]* Closed {closed_count} position(s). All capital converted to cash/SOL + ATA rent reclaimed!")

            elif cmd == "/harvest":
                await self.check_milestone_harvest()

            elif cmd == "/help":
                await send_telegram_alert(
                    "🤖 *CryptoGen Remote Commands:*\n\n"
                    "• `/status` - Live portfolio, open trades & regime\n"
                    "• `/pause` - Pause autonomous buying\n"
                    "• `/resume` - Resume autonomous buying\n"
                    "• `/closeall` - Emergency close all positions to SOL\n"
                    "• `/harvest` - Check and trigger profit sweep\n"
                    "• `/help` - Show this menu"
                )

    def calculate_kelly_position_size(self, win_probability: float) -> float:
        """Kelly sizing adjusted by survival tier and market regime multiplier."""
        tradeable_cash = max(0.0, self.portfolio_inr - EMERGENCY_RESERVE_INR)
        if tradeable_cash < 5.0:
            return 0.0

        # Survival Tier Cap (halves risk in DEFENSE mode)
        tier_cfg = evaluate_survival_tier(self.get_total_net_worth())
        max_cap = tier_cfg.max_position_pct

        kelly_size = calculate_fractional_kelly_size(
            win_probability=win_probability,
            portfolio_inr=self.portfolio_inr,
            reward_to_risk_ratio=3.33,
            fraction=0.25,
            max_cap_pct=max_cap
        )

        # Apply regime multiplier (bull = bigger, bear = smaller)
        regime_mult = self.current_regime.get("kelly_multiplier", 1.0)
        kelly_size *= regime_mult

        return min(kelly_size, tradeable_cash)

    async def update_intelligence(self):
        """
        Runs before each trading scan:
          1. Evaluates Capital Survival Tier (Automaton policy)
          2. Detects market regime (bull/bear/crab/crash)
          3. Scans trending token meta (which narratives are hot)
          4. Loads failure pattern weights from journal
        """
        print("\n--- INTELLIGENCE UPDATE ---")

        # 1. Capital Survival Tier
        self.survival_tier = evaluate_survival_tier(self.get_total_net_worth())
        st = self.survival_tier
        print(f"   {st.emoji} Survival Tier: {st.tier} — {st.description}")

        # 2. Market Regime Detection
        self.current_regime = await self.regime_detector.detect_regime()
        regime = self.current_regime
        print(f"   {regime.get('emoji', '')} Market Regime: {regime['regime']} "
              f"(Confidence: {regime.get('confidence', 0)*100:.0f}%) — {regime.get('description', '')}")

        # 3. Real-Time News Sentinel (With Anti-Fake-News Verification)
        self.news_report = await self.news_sentinel.analyze_market_news(sol_6h_change_pct=self.last_macro_change)
        nr = self.news_report
        news_emoji = "🟢" if nr["sentiment_label"] == "BULLISH" else ("🔴" if nr["sentiment_label"] == "BEARISH" else "⚪")
        fake_alert = f" [🛡️ FUD Caught: {nr['fake_news_reason'][:35]}...]" if nr.get("fake_news_detected") else ""
        print(f"   📰 News Sentiment: {news_emoji} {nr['sentiment_label']} (Score: {nr['sentiment_score']:+.2f}) | {nr['headline_count']} headlines{fake_alert}")
        if nr.get("news_narratives"):
            print(f"   Trending in News: {', '.join(nr['news_narratives'])}")

        # 4. Meta Tracker (every cycle, cached)
        meta = await self.meta_tracker.scan_trending_meta()
        if self.meta_tracker.hot_categories:
            top3 = self.meta_tracker.hot_categories[:3]
            print(f"   Hot Meta: {' > '.join(top3)}")

        # 5. Smart Money / Whale Wallet Tracker (Helius RPC)
        whale_activity = await self.whale_tracker.scan_whale_activity()
        if whale_activity:
            print(f"   🐋 Whale Tracker: {len(whale_activity)} active smart money transaction(s) detected!")

        # 6. Journal Insights
        self.journal_weights = self.journal.get_failure_pattern_weights()

        # 7. Brain Status
        print(f"   {self.brain.get_brain_status()}")
        print("---")

    async def scan_and_trade(self, candidate_addresses: list):
        # Check User Remote Pause
        if self.is_paused:
            print(f"   [PAUSED] Bot is paused by user. Skipping new token buys.")
            return

        # Check Danger Floor (Cycle safety limit)
        if await self.check_danger_floor():
            print(f"   [HALT] Danger Floor active. Trading halted to preserve seed.")
            return

        # Check News Panic Circuit Breaker (Solana outage, critical exploit, etc.)
        if getattr(self, "news_report", {}).get("panic_halt", False):
            reason = self.news_report.get("panic_reason", "Critical news event")
            print(f"   [NEWS HALT] 🚨 Breaking news circuit breaker triggered: {reason}")
            await send_telegram_alert(f"🚨 *[NEWS CIRCUIT BREAKER]*\n• Trading paused due to breaking news: {reason}")
            return

        # Check regime — if CRASH, halt all new trades
        if self.current_regime.get("regime") == "CRASH":
            print(f"   [HALT] Market crash detected. No new trades allowed.")
            await send_telegram_alert(f"[CRASH MODE] Trading halted. Protecting capital.")
            return

        # Check max concurrent positions (regime-dependent)
        max_concurrent = self.current_regime.get("max_concurrent", 3)
        if len(self.active_positions) >= max_concurrent:
            print(f"   [LIMIT] Already {len(self.active_positions)}/{max_concurrent} positions open.")
            return

        # 1. Macro Context Check
        macro = await fetch_sol_macro_context()
        self.last_macro_change = macro.get('sol_6h_change_pct', 0.0)

        # Enhanced macro sensitivity from journal
        macro_threshold = -4.5
        if self.journal_weights.get("macro_sensitivity", 1.0) > 1.5:
            macro_threshold = -2.5  # Much more cautious if journal says crashes hurt us

        if not macro["safe_to_trade"] or self.last_macro_change < macro_threshold:
            print(f"   [MACRO HALT] SOL dumped {macro['sol_6h_change_pct']}%. Pausing buys.")
            return

        print(f"\n   [MACRO] SOL: ${macro['sol_price_usd']:.2f} ({macro['macro_trend']}) | {macro['sol_6h_change_pct']:+0.1f}%")

        # Get adaptive threshold from brain + regime + survival tier
        regime_threshold = self.current_regime.get("ml_threshold", 0.65)
        survival_min_conf = getattr(self, "survival_tier", None).min_confidence if hasattr(self, "survival_tier") else 0.70
        entry_threshold = max(self.brain.get_adaptive_threshold(regime_threshold), survival_min_conf)
        min_pool_liq = self.survival_tier.min_liquidity_usd if hasattr(self, "survival_tier") else 5000.0
        print(f"   [THRESHOLD] Entry bar: {entry_threshold*100:.0f}% (Regime: {regime_threshold*100:.0f}%, Survival: {survival_min_conf*100:.0f}%, Min Liq: ${min_pool_liq:,.0f})")

        for addr in candidate_addresses:
            if addr in self.active_positions:
                continue
            if len(self.active_positions) >= max_concurrent:
                break

            live_data = await fetch_dex_token_data(addr)
            if not live_data or live_data.get("price_usd", 0) <= 0:
                continue

            name = live_data["name"]
            symbol = live_data["symbol"]
            price = live_data["price_usd"]
            liq = live_data["liquidity_usd"]

            # Filter 0: Survival Tier Pool Liquidity Check
            if liq < min_pool_liq:
                print(f"   [SURVIVAL LIQ] {symbol}: Pool ${liq:,.0f} < ${min_pool_liq:,.0f} tier floor. Skipped.")
                continue

            # Filter 1: Basic Safety (RugCheck / DexScreener)
            safety = await analyze_token_safety(addr, live_data)
            if not safety["safe"]:
                # Journal says tighten safety? Extra penalty
                if self.journal_weights.get("safety_strictness", 1.0) > 1.0:
                    print(f"   [SAFETY+] {symbol}: {safety['reason']}. STRICTLY Skipped.")
                else:
                    print(f"   [SAFETY] {symbol}: {safety['reason']}. Skipped.")
                continue

            # Filter 2: Wash Trading & Manipulation Detection
            wash = live_data.get("wash_analysis", {})
            if wash.get("manipulated", False):
                print(f"   [MANIPULATION] {symbol}: Wash trading (Score {wash['wash_score']}). Skipped.")
                continue

            # Filter 3: AMM Price Impact
            trade_sol = 20.0 / SOL_TO_INR_ESTIMATE
            pool_sol = liq / 140.0
            price_impact = calculate_amm_price_impact(trade_sol, pool_sol)
            if price_impact > 0.03:
                print(f"   [SLIPPAGE] {symbol}: Price impact {price_impact*100:.2f}% > 3.0%. Skipped.")
                continue

            # Filter 4: Feature Extraction & ML Prediction
            features = extract_features_from_token_data(live_data)

            # === NEW: Meta bonus for hot narrative tokens ===
            meta_bonus = self.meta_tracker.get_meta_bonus(name, symbol)

            # === NEW: Enhanced prediction with meta + journal + whale ===
            win_prob = self.brain.predict_win_probability(
                features, meta_bonus=meta_bonus, journal_weights=self.journal_weights
            )

            # Smart Money / Whale Tracker Bonus
            whale_bonus = self.whale_tracker.get_whale_bonus(addr)
            if whale_bonus > 0:
                win_prob = min(0.99, win_prob + whale_bonus)

            print(f"\n   [EVALUATING] {symbol} (${price:.8f}) | Liq: ${liq:,.0f}")
            print(f"   Buy Ratio (5m): {features['buy_ratio_5m']*100:.1f}% | OFI: {features['ofi_5m']:+.2f} | Vol Accel: {features['vol_acceleration']:.2f}x")
            if meta_bonus > 0:
                meta_cats = self.meta_tracker.classify_token(name, symbol)
                print(f"   Meta Bonus: +{meta_bonus*100:.0f}% ({', '.join(meta_cats)})")
            if whale_bonus > 0:
                print(f"   🐋 Whale Bonus: +{whale_bonus*100:.0f}% (Tracked Smart Money Accumulated)")
            print(f"   ML Confidence: {win_prob*100:.1f}% (Need: {entry_threshold*100:.0f}%)")

            # Entry Check with adaptive threshold
            if win_prob < entry_threshold:
                print(f"   Confidence {win_prob*100:.1f}% < {entry_threshold*100:.0f}%. Skipping.")
                continue

            # Position Sizing via Kelly (regime-adjusted)
            size_inr = self.calculate_kelly_position_size(win_prob)
            if size_inr < 5.0:
                print(f"   Kelly sizing INR{size_inr:.2f} below INR5 minimum. Skipping.")
                continue

            # ATA Rent Reservation
            ata_locked = min(5.0, self.portfolio_inr * 0.05)
            self.locked_ata_rent_inr += ata_locked
            self.portfolio_inr -= (size_inr + ata_locked)

            # Execute On-Chain Swap
            lamports_to_invest = int((size_inr / SOL_TO_INR_ESTIMATE) * 1_000_000_000)
            swap_res = await self.executor.execute_swap(
                input_mint=SOL_MINT,
                output_mint=addr,
                amount_lamports=lamports_to_invest,
                paper_mode=(not self.is_live)
            )
            if not swap_res.get("success", False):
                print(f"   Swap failed: {swap_res.get('reason')}. Skipping.")
                self.portfolio_inr += (size_inr + ata_locked)
                self.locked_ata_rent_inr -= ata_locked
                continue

            self.trade_counter += 1
            tokens_bought = (size_inr / SOL_TO_INR_ESTIMATE) / price

            self.active_positions[addr] = {
                "trade_number": self.trade_counter,
                "token": symbol,
                "name": name,
                "entry_price": price,
                "peak_price": price,  # NEW: Track peak for journal
                "invested_inr": size_inr,
                "ata_locked_inr": ata_locked,
                "remaining_tokens": tokens_bought,
                "initial_tokens": tokens_bought,
                "tx_hash": swap_res.get("tx_hash"),
                "features": features,
                "stop_loss_price": price * (1.0 - STOP_LOSS_PERCENT),
                "entry_time": time.time(),  # NEW: Track hold duration
                "entry_volume": live_data.get("volume_1h", 0),  # NEW: Volume at entry
                "regime_at_entry": self.current_regime.get("regime", "UNKNOWN"),  # NEW
                "tp_stages_hit": 0,  # NEW: Count TP stages
                "tp_stages": [
                    {"mult": s["mult"], "price": price * s["mult"], "ratio": s["sell_ratio"], "hit": False}
                    for s in TAKE_PROFIT_STAGES
                ]
            }

            regime_tag = self.current_regime.get("regime", "?")
            print(f"   [BUY FILLED] {symbol} | Invested: INR{size_inr:.2f} | ATA Rent: INR{ata_locked:.2f} | Regime: {regime_tag}")
            print(f"   TX: {swap_res.get('tx_hash')[:32]}...")
            print(f"   Stop Loss: ${price * (1.0 - STOP_LOSS_PERCENT):.8f} (-30%)")
            print(f"   Cash: INR{self.portfolio_inr:.2f} | Net Worth: INR{self.get_total_net_worth():.2f}")
            await send_telegram_alert(
                f"*[BUY]* {symbol}\n"
                f"- Invested: INR{size_inr:.2f}\n"
                f"- Confidence: {win_prob*100:.0f}%\n"
                f"- Regime: {regime_tag}\n"
                f"- Net Worth: INR{self.get_total_net_worth():.2f}"
            )

    async def update_market_ticks(self, price_dict: dict):
        """
        Updates prices, manages stop-loss/take-profit, logs to trade journal,
        and triggers reinforcement learning with failure categorization.
        """
        closed_addrs = []

        for addr, pos in list(self.active_positions.items()):
            curr_price = price_dict.get(addr, pos["entry_price"])
            pnl_pct = ((curr_price - pos["entry_price"]) / pos["entry_price"]) * 100

            # Track peak price and ratchet Trailing Stop-Loss
            if curr_price > pos.get("peak_price", pos["entry_price"]):
                pos["peak_price"] = curr_price

            peak = pos.get("peak_price", pos["entry_price"])
            entry = pos["entry_price"]
            peak_gain_pct = ((peak - entry) / entry) * 100

            # Dynamic Trailing Stop-Loss Escalator:
            # Tier 3 (5x+ Moonshot): Trail 20% below peak
            if peak >= entry * 5.0:
                trailing_stop = peak * 0.80
                if trailing_stop > pos["stop_loss_price"]:
                    pos["stop_loss_price"] = trailing_stop
                    print(f"   📈 [TRAILING STOP ESCALATED] {pos['token']}: Locked at ${trailing_stop:.8f} (80% of ${peak:.8f} peak)")
            # Tier 2 (2x Double): Trail 25% below peak
            elif peak >= entry * 2.0:
                trailing_stop = peak * 0.75
                if trailing_stop > pos["stop_loss_price"]:
                    pos["stop_loss_price"] = trailing_stop
                    print(f"   📈 [TRAILING STOP ESCALATED] {pos['token']}: Locked at ${trailing_stop:.8f} (75% of ${peak:.8f} peak)")
            # Tier 1 (+30% Surge): Move stop-loss to Break-Even (entry price)
            elif peak >= entry * 1.30:
                if entry > pos["stop_loss_price"]:
                    pos["stop_loss_price"] = entry
                    print(f"   🛡️ [BREAK-EVEN RATCHET] {pos['token']}: Stop-loss moved to entry price ${entry:.8f} (Zero Risk Locked)")

            print(f"   [{pos['token']}] Current: ${curr_price:.8f} ({pnl_pct:+.1f}%) | Peak: ${peak:.8f} | Stop: ${pos['stop_loss_price']:.8f}")

            # === Check Stop Loss (Trailing or Hard) ===
            if curr_price <= pos["stop_loss_price"]:
                recovered_inr = (pos["remaining_tokens"] * curr_price) * SOL_TO_INR_ESTIMATE
                await self.executor.execute_swap(addr, SOL_MINT, int(pos["remaining_tokens"] * 1_000_000), paper_mode=(not self.is_live))
                self.reclaimer.reclaim_rent(addr, paper_mode=(not self.is_live))
                refund_ata = pos["ata_locked_inr"]
                self.locked_ata_rent_inr -= refund_ata
                self.portfolio_inr += (recovered_inr + refund_ata)

                loss = pos["invested_inr"] - recovered_inr
                self.losses += 1

                # === NEW: Get current volume for journal ===
                exit_volume = 0
                try:
                    exit_data = await fetch_dex_token_data(addr)
                    if exit_data:
                        exit_volume = exit_data.get("volume_1h", 0)
                except Exception:
                    pass

                # === NEW: Log to Trade Journal with categorization ===
                category = self.journal.log_trade(
                    token_symbol=pos["token"],
                    token_address=addr,
                    entry_price=pos["entry_price"],
                    exit_price=curr_price,
                    peak_price=pos.get("peak_price", pos["entry_price"]),
                    pnl_pct=pnl_pct,
                    pnl_inr=-loss,
                    hold_duration_secs=time.time() - pos.get("entry_time", time.time()),
                    sol_macro_change_pct=self.last_macro_change,
                    volume_at_entry=pos.get("entry_volume", 0),
                    volume_at_exit=exit_volume,
                    was_stop_loss=True,
                    tp_stages_hit=pos.get("tp_stages_hit", 0),
                    features=pos["features"],
                    market_regime=pos.get("regime_at_entry", "UNKNOWN")
                )

                print(f"   [STOP LOSS] {pos['token']} sold @ -30%. Loss: -INR{loss:.2f} (ATA Refund: +INR{refund_ata:.2f})")
                await send_telegram_alert(
                    f"*[STOP LOSS]* {pos['token']}\n"
                    f"- Loss: -INR{loss:.2f}\n"
                    f"- Reason: {category}\n"
                    f"- Cash: INR{self.portfolio_inr:.2f}"
                )

                # === NEW: Learn with failure category ===
                self.brain.learn_from_trade_result(pos["features"], was_winner=False, trade_category=category)
                closed_addrs.append(addr)
                continue

            # === Check Staged Take-Profit ===
            for stage in pos["tp_stages"]:
                if not stage["hit"] and curr_price >= stage["price"]:
                    tokens_to_sell = pos["initial_tokens"] * stage["ratio"]
                    tokens_to_sell = min(tokens_to_sell, pos["remaining_tokens"])
                    proceeds = (tokens_to_sell * curr_price) * SOL_TO_INR_ESTIMATE
                    await self.executor.execute_swap(addr, SOL_MINT, int(tokens_to_sell * 1_000_000), paper_mode=(not self.is_live))
                    self.portfolio_inr += proceeds
                    pos["remaining_tokens"] -= tokens_to_sell
                    stage["hit"] = True
                    pos["tp_stages_hit"] = pos.get("tp_stages_hit", 0) + 1
                    print(f"   [TP {stage['mult']}x HIT] Sold {stage['ratio']*100:.0f}% of {pos['token']}. Locked: +INR{proceeds:.2f}")
                    await send_telegram_alert(
                        f"*[TAKE PROFIT {stage['mult']}x]* {pos['token']}\n"
                        f"- Locked: +INR{proceeds:.2f}\n"
                        f"- Net Worth: INR{self.get_total_net_worth():.2f}"
                    )

            # If all tokens sold via TP stages
            if pos["remaining_tokens"] <= 0.000001:
                self.reclaimer.reclaim_rent(addr, paper_mode=(not self.is_live))
                refund_ata = pos["ata_locked_inr"]
                self.locked_ata_rent_inr -= refund_ata
                self.portfolio_inr += refund_ata
                self.wins += 1

                # === NEW: Log winning trade to journal ===
                category = self.journal.log_trade(
                    token_symbol=pos["token"],
                    token_address=addr,
                    entry_price=pos["entry_price"],
                    exit_price=curr_price,
                    peak_price=pos.get("peak_price", curr_price),
                    pnl_pct=pnl_pct,
                    pnl_inr=pos["invested_inr"] * (pnl_pct / 100),
                    hold_duration_secs=time.time() - pos.get("entry_time", time.time()),
                    sol_macro_change_pct=self.last_macro_change,
                    volume_at_entry=pos.get("entry_volume", 0),
                    volume_at_exit=0,
                    was_stop_loss=False,
                    tp_stages_hit=pos.get("tp_stages_hit", 0),
                    features=pos["features"],
                    market_regime=pos.get("regime_at_entry", "UNKNOWN")
                )

                print(f"   [FULL EXIT] {pos['token']} closed in profit! ({category}) ATA Reclaimed: +INR{refund_ata:.2f}")
                self.brain.learn_from_trade_result(pos["features"], was_winner=True, trade_category=category)
                closed_addrs.append(addr)

        for addr in closed_addrs:
            del self.active_positions[addr]

    def display_dashboard(self):
        total_nw = self.get_total_net_worth()
        total_trades = self.wins + self.losses
        win_rate = (self.wins / total_trades * 100) if total_trades > 0 else 0.0
        stage = self.get_current_ladder_stage()
        cycle_target = stage["target_inr"]
        progress = min(100.0, (total_nw / cycle_target) * 100)
        uptime = time.time() - self.session_start

        regime = self.current_regime.get("regime", "UNKNOWN")
        regime_emoji = self.current_regime.get("emoji", "")
        st = getattr(self, "survival_tier", evaluate_survival_tier(total_nw))

        danger_status = "⚠️ FROZEN" if self.is_danger_halted else f"INR {stage['danger_floor_inr']:.0f}"

        nr = getattr(self, "news_report", {})
        news_str = f"{nr.get('sentiment_label', 'NEUTRAL')} ({nr.get('sentiment_score', 0.0):+.2f})" if nr else "N/A"

        print("\n" + "-" * 60)
        print(f" PORTFOLIO: INR {total_nw:.2f} | CYCLE #{stage['cycle']} GOAL: INR {cycle_target:,.0f}")
        print(f"   Liquid Cash    : INR {self.portfolio_inr:.2f}")
        print(f"   ATA Locked     : INR {self.locked_ata_rent_inr:.2f} (Refundable)")
        print(f"   Open Positions : {len(self.active_positions)}")
        print(f"   Win Rate       : {win_rate:.1f}% ({self.wins}W / {self.losses}L)")
        print(f"   Danger Floor   : {danger_status}")
        print(f"   Survival Tier  : {st.emoji} {st.tier} (Floor: ${st.min_liquidity_usd:,.0f})")
        print(f"   Market Regime  : {regime_emoji} {regime}")
        print(f"   News Sentiment : 📰 {news_str}")
        print(f"   Brain Accuracy : {self.brain.recent_accuracy*100:.0f}% | Threshold: {self.brain.adaptive_threshold*100:.0f}%")
        bar_len = int(progress // 5)
        print(f"   Cycle Metric   : [{'#' * bar_len}{'-' * (20 - bar_len)}] {progress:.1f}%")

        # Journal summary if we have trades
        if self.journal.entries:
            regime_wr = self.journal.get_win_rate_by_regime()
            if regime_wr:
                regime_str = " | ".join(f"{r}: {wr:.0f}%" for r, wr in regime_wr.items())
                print(f"   Win Rate/Regime: {regime_str}")

        print("-" * 60)


async def run_autonomous_simulation_loop():
    trader = AutonomousDemoTrader()

    # Start Web Analytics Dashboard in background thread
    import threading
    from dashboard_server import start_dashboard_server
    dashboard_port = int(os.getenv("PORT", 8080))
    dash_thread = threading.Thread(target=start_dashboard_server, args=(dashboard_port,), daemon=True)
    dash_thread.start()

    print(f"🚀 CryptoGen Cloud Worker started. Web Dashboard live on port {dashboard_port}!")
    await send_telegram_alert(f"🚀 *[BOT ONLINE]* CryptoGen 24/7 Cloud Incubation started!\n• Mode: Virtual Paper Trading\n• Starting Balance: INR 100.00\n• Web Dashboard: Live on port {dashboard_port}")

    cycle_count = 0
    last_hourly_digest = time.time()

    while True:
        cycle_count += 1
        print(f"\n{'='*65}\n🔄 [CLOUD CYCLE #{cycle_count}] Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n{'='*65}")

        try:
            # 0. Check and Process Remote Telegram Commands (/status, /pause, /resume, /closeall, /harvest)
            await trader.handle_remote_commands()

            # 1. Intelligence & Market Regime Update
            await trader.update_intelligence()

            # 2. Fetch live trending Solana candidates
            trending = await fetch_trending_solana_tokens()
            popular_tokens = [
                "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
                "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  # WIF
                "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  # JUP
                "CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump"   # GOAT
            ]
            candidates = list(dict.fromkeys(trending + popular_tokens))

            # 3. Scan & execute candidate trades (Virtual or Live)
            await trader.scan_and_trade(candidates[:10])
            trader.display_dashboard()

            # 4. Monitor active positions (if any are held)
            if trader.active_positions:
                print(f"⏳ Monitoring {len(trader.active_positions)} active position(s)...")
                for _ in range(6):  # Check ticks every 5s for 30s
                    await asyncio.sleep(5)
                    live_prices = {}
                    for addr in list(trader.active_positions.keys()):
                        data = await fetch_dex_token_data(addr)
                        if data and data.get("price_usd", 0) > 0:
                            live_prices[addr] = data["price_usd"]

                    if live_prices:
                        await trader.update_market_ticks(live_prices)
                        trader.display_dashboard()
                        # Check milestone harvest condition
                        await trader.check_milestone_harvest()

                    if not trader.active_positions:
                        break
            else:
                # Check milestone harvest if no positions are active
                await trader.check_milestone_harvest()

                # No open positions: pause before next scan to respect free API rate limits
                sleep_secs = trader.current_regime.get("scan_interval_secs", 45)
                print(f"💤 Sleeping {sleep_secs}s before next market scan...")
                await asyncio.sleep(sleep_secs)

            # 5. Hourly Telegram Heartbeat Digest
            if time.time() - last_hourly_digest >= 3600:
                last_hourly_digest = time.time()
                total_nw = trader.get_total_net_worth()
                regime = trader.current_regime.get("regime", "UNKNOWN")
                await send_telegram_alert(
                    f"📊 *[HOURLY DIGEST]*\n"
                    f"• Net Worth: INR {total_nw:.2f} / 1000.00\n"
                    f"• Wins: {trader.wins} | Losses: {trader.losses}\n"
                    f"• Regime: {regime}\n"
                    f"• Open Positions: {len(trader.active_positions)}"
                )

        except Exception as e:
            print(f"⚠️ [LOOP ERROR] {e}. Retrying in 15 seconds...")
            await asyncio.sleep(15)


if __name__ == "__main__":
    asyncio.run(run_autonomous_simulation_loop())
