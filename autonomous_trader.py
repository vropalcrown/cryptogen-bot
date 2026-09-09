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
    EMERGENCY_RESERVE_INR, SOL_TO_INR_ESTIMATE, PAPER_TRADING
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
from telegram_notifier import send_telegram_alert

# === NEW INTELLIGENCE MODULES ===
from trade_journal import TradeJournal
from market_regime import MarketRegimeDetector
from meta_tracker import MetaTracker


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

        # Track last known macro state for journal
        self.last_macro_change = 0.0

        self.is_live = (not PAPER_TRADING) and (self.live_sol_balance > 0.001)
        mode_str = f"LIVE ON-CHAIN (Balance: {self.live_sol_balance:.4f} SOL)" if self.is_live else "PAPER SIMULATION (Awaiting SOL Deposit)"
        print("\n" + "=" * 70)
        print("      ⚡ CRYPTOGEN v2 — INTELLIGENT AUTONOMOUS TRADER ⚡")
        print("=" * 70)
        print(f" Execution Mode     : {mode_str}")
        print(f" Burner Address     : {self.executor.wallet_pubkey}")
        print(f" Starting Balance   : INR{self.portfolio_inr:.2f} (Target: INR{TARGET_BALANCE_INR:.2f})")
        print(f" Smart Brain v2     : Ensemble RF+GBM | Adaptive Threshold | RL")
        print(f" Trade Journal      : Failure-aware categorization")
        print(f" Market Regime      : Auto bull/bear/crab detection")
        print(f" Meta Tracker       : Narrative trend intelligence")
        print(f" Quant Risk Engine  : Fractional Kelly + AMM Price Impact")
        print(f" Manipulation Filter: Wash-trading + HHI Concentration")
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

    def calculate_kelly_position_size(self, win_probability: float) -> float:
        """Kelly sizing adjusted by market regime multiplier."""
        tradeable_cash = max(0.0, self.portfolio_inr - EMERGENCY_RESERVE_INR)
        if tradeable_cash < 5.0:
            return 0.0

        kelly_size = calculate_fractional_kelly_size(
            win_probability=win_probability,
            portfolio_inr=self.portfolio_inr,
            reward_to_risk_ratio=3.33,
            fraction=0.25,
            max_cap_pct=0.20
        )

        # Apply regime multiplier (bull = bigger, bear = smaller)
        regime_mult = self.current_regime.get("kelly_multiplier", 1.0)
        kelly_size *= regime_mult

        return min(kelly_size, tradeable_cash)

    async def update_intelligence(self):
        """
        Runs before each trading scan:
          1. Detects market regime (bull/bear/crab/crash)
          2. Scans trending token meta (which narratives are hot)
          3. Loads failure pattern weights from journal
        """
        print("\n--- INTELLIGENCE UPDATE ---")

        # 1. Market Regime Detection
        self.current_regime = await self.regime_detector.detect_regime()
        regime = self.current_regime
        print(f"   {regime.get('emoji', '')} Market Regime: {regime['regime']} "
              f"(Confidence: {regime.get('confidence', 0)*100:.0f}%) — {regime.get('description', '')}")

        # 2. Meta Tracker (less frequent — every 10 min)
        meta = await self.meta_tracker.scan_trending_meta()
        if self.meta_tracker.hot_categories:
            top3 = self.meta_tracker.hot_categories[:3]
            print(f"   Hot Meta: {' > '.join(top3)}")

        # 3. Journal Insights
        self.journal_weights = self.journal.get_failure_pattern_weights()

        # 4. Brain Status
        print(f"   {self.brain.get_brain_status()}")
        print("---")

    async def scan_and_trade(self, candidate_addresses: list):
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

        # Get adaptive threshold from brain + regime
        regime_threshold = self.current_regime.get("ml_threshold", 0.65)
        entry_threshold = self.brain.get_adaptive_threshold(regime_threshold)
        print(f"   [THRESHOLD] Entry bar: {entry_threshold*100:.0f}% (Regime: {regime_threshold*100:.0f}%, Brain: {self.brain.adaptive_threshold*100:.0f}%)")

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

            # === NEW: Enhanced prediction with meta + journal ===
            win_prob = self.brain.predict_win_probability(
                features, meta_bonus=meta_bonus, journal_weights=self.journal_weights
            )

            print(f"\n   [EVALUATING] {symbol} (${price:.8f}) | Liq: ${liq:,.0f}")
            print(f"   Buy Ratio (5m): {features['buy_ratio_5m']*100:.1f}% | OFI: {features['ofi_5m']:+.2f} | Vol Accel: {features['vol_acceleration']:.2f}x")
            if meta_bonus > 0:
                meta_cats = self.meta_tracker.classify_token(name, symbol)
                print(f"   Meta Bonus: +{meta_bonus*100:.0f}% ({', '.join(meta_cats)})")
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

            # Track peak price for journal
            if curr_price > pos.get("peak_price", pos["entry_price"]):
                pos["peak_price"] = curr_price

            print(f"   [{pos['token']}] Current: ${curr_price:.8f} ({pnl_pct:+.1f}%) | Peak: ${pos.get('peak_price', 0):.8f}")

            # === Check Stop Loss (-30%) ===
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
        progress = min(100.0, (total_nw / TARGET_BALANCE_INR) * 100)
        uptime = time.time() - self.session_start

        regime = self.current_regime.get("regime", "UNKNOWN")
        regime_emoji = self.current_regime.get("emoji", "")

        print("\n" + "-" * 60)
        print(f" PORTFOLIO: INR{total_nw:.2f} / INR{TARGET_BALANCE_INR:.2f}")
        print(f"   Liquid Cash    : INR{self.portfolio_inr:.2f}")
        print(f"   ATA Locked     : INR{self.locked_ata_rent_inr:.2f} (Refundable)")
        print(f"   Open Positions : {len(self.active_positions)}")
        print(f"   Win Rate       : {win_rate:.1f}% ({self.wins}W / {self.losses}L)")
        print(f"   Market Regime  : {regime_emoji} {regime}")
        print(f"   Brain Accuracy : {self.brain.recent_accuracy*100:.0f}% | Threshold: {self.brain.adaptive_threshold*100:.0f}%")
        bar_len = int(progress // 5)
        print(f"   Target Metric  : [{'#' * bar_len}{'-' * (20 - bar_len)}] {progress:.1f}%")

        # Journal summary if we have trades
        if self.journal.entries:
            regime_wr = self.journal.get_win_rate_by_regime()
            if regime_wr:
                regime_str = " | ".join(f"{r}: {wr:.0f}%" for r, wr in regime_wr.items())
                print(f"   Win Rate/Regime: {regime_str}")

        print("-" * 60)


async def run_autonomous_simulation_loop():
    trader = AutonomousDemoTrader()
    print("🚀 CryptoGen Cloud Worker started. Running 24/7 continuous autonomous trading loop...")
    await send_telegram_alert("🚀 *[BOT ONLINE]* CryptoGen 24/7 Cloud Incubation started!\n• Mode: Virtual Paper Trading\n• Starting Balance: INR 100.00\n• Monitoring live Solana DEX pairs...")

    cycle_count = 0
    last_hourly_digest = time.time()

    while True:
        cycle_count += 1
        print(f"\n{'='*65}\n🔄 [CLOUD CYCLE #{cycle_count}] Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n{'='*65}")

        try:
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

                    if not trader.active_positions:
                        break
            else:
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
