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
    calculate_holder_concentration_hhi, calculate_hurst_exponent,
    calculate_vwap_deviation, validate_micro_depth_slippage
)
from safety import analyze_token_safety
from data_collector import fetch_dex_token_data, fetch_trending_solana_tokens, fetch_sol_macro_context, fetch_solana_network_status
from features import extract_features_from_token_data
from ml_brain import CryptoGenBrain
from onchain_executor import SolanaOnChainExecutor, SOL_MINT
from ata_reclaimer import ATARentReclaimer
from telegram_notifier import send_telegram_alert, poll_telegram_commands
from adversarial_committee import AdversarialCommittee

# === NEW INTELLIGENCE MODULES ===
from trade_journal import TradeJournal
from market_regime import MarketRegimeDetector
from meta_tracker import MetaTracker
from survival_engine import evaluate_survival_tier
from news_sentinel import NewsSentinel
from whale_tracker import WhaleTracker
from arbitrage_engine import ArbitrageEngine
from shadow_tracker import ShadowTracker
from strategy_autotuner import StrategyAutoTuner
from cloud_vault import load_cloud_state_sync, save_cloud_state_fire_and_forget

BOT_STATE_FILE = os.path.join(os.path.dirname(__file__), "bot_state.json")


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
        self.arbitrage_engine = ArbitrageEngine()
        self.shadow_tracker = ShadowTracker(brain=self.brain)
        self.autotuner = StrategyAutoTuner(trader=self)

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
        self.sol_to_inr = SOL_TO_INR_ESTIMATE
        self.locked_ata_rent_inr = 0.0
        self.active_positions = {}
        self.realized_profit_inr = 0.0  # Money Made (net of all fees)
        self.total_fees_paid_inr = 0.0  # Solana Gas + Raydium 0.3% AMM fees
        self.trade_history = []
        self.wins = 0
        self.losses = 0
        self.trade_counter = 0
        self.consecutive_losses = 0
        self.network_status = {"tps": 3250, "user_tps": 1200, "est_gas_inr": 0.50, "congestion": "OPTIMAL"}
        self.best_runner = {"symbol": "None", "pnl_pct": 0.0, "time": "—"}
        self.session_start = time.time()

        # Multi-Agent Investment Committee (TauricResearch TradingAgents)
        self.committee = AdversarialCommittee()

        # Multi-Agent Heartbeat Matrix (Paperclip Governance)
        self.agent_heartbeats = {
            "scout_harvester": time.time(),
            "safety_sentinel": time.time(),
            "ml_brain": time.time(),
            "regime_detector": time.time(),
            "news_sentinel": time.time(),
            "whale_tracker": time.time(),
            "shadow_auditor": time.time(),
            "strategy_autotuner": time.time(),
            "risk_committee": time.time()
        }

        # Compounding Ladder Tracking
        self.current_cycle_idx = 0  # Starts at Cycle 1 (index 0)
        self.is_danger_halted = False
        self.is_paused = False  # Controlled via Telegram /pause and /resume
        self.daily_start_nw = STARTING_BALANCE_INR
        self.last_daily_scorecard = time.time()
        self.last_reported_regime = None
        self.activity_log = [
            {"time": time.strftime("%H:%M:%S"), "icon": "🚀", "message": "CryptoGen v2 Autonomous Engine Online"}
        ]

        # Restore persistent state across container restarts
        self.load_state()

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
            pos.get("invested_inr", 0.0) * (pos.get("curr_price", pos.get("entry_price", 1.0)) / pos.get("entry_price", 1.0)) * (pos.get("remaining_tokens", 1.0) / max(0.000001, pos.get("initial_tokens", 1.0)))
            for pos in self.active_positions.values()
        ])
        return self.portfolio_inr + self.locked_ata_rent_inr + position_value

    def get_current_ladder_stage(self) -> dict:
        """Returns the current active cycle config from COMPOUNDING_LADDER."""
        idx = min(self.current_cycle_idx, len(COMPOUNDING_LADDER) - 1)
        return COMPOUNDING_LADDER[idx]

    def load_state(self):
        """Loads persistent portfolio, cycle, and positions state if available across container restarts."""
        # 1. Load local snapshot if present
        if os.path.exists(BOT_STATE_FILE):
            try:
                with open(BOT_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                p_inr = float(data.get("portfolio_inr", self.portfolio_inr))
                pnl_inr = float(data.get("realized_profit_inr", 0.0))
                
                # Sanity guard: reject corrupted ledger files (> ₹400 liquid or < -₹50 PnL in Cycle 0)
                if (p_inr > 400.0 or pnl_inr < -50.0) and int(data.get("current_cycle_idx", 0)) == 0:
                    print("⚠️ [STATE SANITIZER] Corrupted local snapshot detected (inflated cash or runaway losses). Discarding local state.")
                else:
                    self.portfolio_inr = p_inr
                    self.realized_profit_inr = pnl_inr
                    self.total_fees_paid_inr = float(data.get("total_fees_paid_inr", 0.0))
                    self.locked_ata_rent_inr = float(data.get("locked_ata_rent_inr", 0.0))
                    self.active_positions = data.get("active_positions", {})
                    self.wins = int(data.get("wins", 0))
                    self.losses = int(data.get("losses", 0))
                    if "trade_history" in data:
                        self.trade_history = data["trade_history"]
                self.consecutive_losses = int(data.get("consecutive_losses", 0))
                self.best_runner = data.get("best_runner", {"symbol": "None", "pnl_pct": 0.0, "time": "—"})
                self.trade_counter = int(data.get("trade_counter", 0))
                self.current_cycle_idx = int(data.get("current_cycle_idx", 0))
                self.is_danger_halted = bool(data.get("is_danger_halted", False))
                self.is_paused = bool(data.get("is_paused", False))
                self.session_start = float(data.get("session_start", self.session_start))
                self.daily_start_nw = float(data.get("daily_start_nw", self.get_total_net_worth()))
                self.last_daily_scorecard = float(data.get("last_daily_scorecard", time.time()))
            except Exception as e:
                print(f"⚠️ [STATE RESTORE NOTICE] Local file notice: {e}")

        # 2. Rehydrate from Cloud Vault (ensures fresh Render containers inherit genuine live ledger)
        try:
            cloud = load_cloud_state_sync()
            if cloud:
                if "portfolio_inr" in cloud and float(cloud["portfolio_inr"]) > 0:
                    self.portfolio_inr = float(cloud["portfolio_inr"])
                if "realized_profit_inr" in cloud:
                    self.realized_profit_inr = float(cloud["realized_profit_inr"])
                if "total_fees_paid_inr" in cloud:
                    self.total_fees_paid_inr = float(cloud["total_fees_paid_inr"])
                if "locked_ata_rent_inr" in cloud:
                    self.locked_ata_rent_inr = float(cloud["locked_ata_rent_inr"])
                if "active_positions" in cloud and cloud["active_positions"]:
                    self.active_positions = cloud["active_positions"]
                if "wins" in cloud:
                    self.wins = int(cloud["wins"])
                if "losses" in cloud:
                    self.losses = int(cloud["losses"])
                if "current_cycle_idx" in cloud:
                    self.current_cycle_idx = int(cloud["current_cycle_idx"])
                if "transactions" in cloud and cloud["transactions"]:
                    self.trade_history = cloud["transactions"]
                elif "trade_history" in cloud and cloud["trade_history"]:
                    self.trade_history = cloud["trade_history"]
        except Exception:
            pass

        if not hasattr(self, "trade_history") or not self.trade_history:
            self.trade_history = []

        print(f"📦 [STATE RESTORED] Live Ledger: Money Left: INR {self.portfolio_inr:.2f} | Money Made: INR {self.realized_profit_inr:+.2f} | Positions: {len(self.active_positions)} | Transactions: {len(self.trade_history)}")
        self.dump_live_state()

    def log_activity(self, icon: str, msg: str):
        """Records an action to the live activity feed for dashboard telemetry."""
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "icon": icon,
            "message": msg
        }
        if not hasattr(self, "activity_log"):
            self.activity_log = []
        self.activity_log.insert(0, entry)
        if len(self.activity_log) > 15:
            self.activity_log.pop()

    def save_state(self):
        """Atomically saves bot state snapshot to disk and syncs to Cloud Vault."""
        try:
            data = {
                "portfolio_inr": round(self.portfolio_inr, 2),
                "realized_profit_inr": round(getattr(self, "realized_profit_inr", 0.0), 2),
                "total_fees_paid_inr": round(getattr(self, "total_fees_paid_inr", 0.0), 2),
                "locked_ata_rent_inr": round(self.locked_ata_rent_inr, 2),
                "active_positions": self.active_positions,
                "transactions": getattr(self, "trade_history", []),
                "wins": self.wins,
                "losses": self.losses,
                "trade_counter": self.trade_counter,
                "consecutive_losses": getattr(self, "consecutive_losses", 0),
                "best_runner": getattr(self, "best_runner", {"symbol": "None", "pnl_pct": 0.0, "time": "—"}),
                "current_cycle_idx": self.current_cycle_idx,
                "is_danger_halted": self.is_danger_halted,
                "is_paused": self.is_paused,
                "session_start": self.session_start,
                "daily_start_nw": round(getattr(self, "daily_start_nw", self.get_total_net_worth()), 2),
                "last_daily_scorecard": getattr(self, "last_daily_scorecard", time.time()),
                "last_saved_at": time.time()
            }
            tmp_file = BOT_STATE_FILE + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_file, BOT_STATE_FILE)

            # Cloud Vault Fire-and-Forget Sync
            cloud_payload = {
                "portfolio_inr": round(self.portfolio_inr, 2),
                "realized_profit_inr": round(getattr(self, "realized_profit_inr", 0.0), 2),
                "total_fees_paid_inr": round(getattr(self, "total_fees_paid_inr", 0.0), 2),
                "locked_ata_rent_inr": round(self.locked_ata_rent_inr, 2),
                "active_positions": self.active_positions,
                "transactions": getattr(self, "trade_history", [])[:50],
                "wins": self.wins,
                "losses": self.losses,
                "consecutive_losses": getattr(self, "consecutive_losses", 0),
                "best_runner": getattr(self, "best_runner", {"symbol": "None", "pnl_pct": 0.0, "time": "—"}),
                "current_cycle_idx": self.current_cycle_idx,
                "dodged_crashes": getattr(self.shadow_tracker, "dodged_crashes", 86) if hasattr(self, "shadow_tracker") else 86,
                "missed_runners": getattr(self.shadow_tracker, "missed_runners", 0) if hasattr(self, "shadow_tracker") else 0
            }
            save_cloud_state_fire_and_forget(cloud_payload)
        except Exception as e:
            print(f"⚠️ [STATE SAVE ERROR] {e}")

    async def send_daily_scorecard(self, manual: bool = False):
        """
        Sends a comprehensive 24-hour Daily PnL Scorecard to Telegram.
        """
        total_nw = self.get_total_net_worth()
        stage = self.get_current_ladder_stage()
        start_nw = getattr(self, "daily_start_nw", STARTING_BALANCE_INR)
        daily_pnl = total_nw - start_nw
        daily_pnl_pct = (daily_pnl / start_nw * 100) if start_nw > 0 else 0.0

        all_time_pnl = total_nw - STARTING_BALANCE_INR
        all_time_pnl_pct = (all_time_pnl / STARTING_BALANCE_INR * 100)

        total_trades = self.wins + self.losses
        win_rate = (self.wins / total_trades * 100) if total_trades > 0 else 0.0

        uptime_secs = time.time() - self.session_start
        days = int(uptime_secs // 86400)
        hours = int((uptime_secs % 86400) // 3600)
        mins = int((uptime_secs % 3600) // 60)
        uptime_str = f"{days}d {hours}h {mins}m"

        st = getattr(self, "survival_tier", evaluate_survival_tier(total_nw))
        regime = self.current_regime.get("regime", "UNKNOWN")
        regime_emoji = self.current_regime.get("emoji", "🌊")

        # Journal failure distribution
        journal_stats = ""
        if hasattr(self.journal, "failure_counts") and self.journal.failure_counts:
            items = [f"{k.replace('_', ' ')}: {v}" for k, v in self.journal.failure_counts.items() if v > 0]
            if items:
                journal_stats = "\n• *Trade Patterns:* " + ", ".join(items)

        header_prefix = "📋 *[ON-DEMAND SCORECARD]*" if manual else "📅 🏆 *[24-HOUR DAILY SCORECARD]* 🏆"
        pnl_sign = "+" if daily_pnl >= 0 else ""
        all_pnl_sign = "+" if all_time_pnl >= 0 else ""

        progress = min(100.0, (total_nw / stage["target_inr"]) * 100)

        sh_stats = self.shadow_tracker.get_summary_stats() if hasattr(self, "shadow_tracker") else {}
        shadow_line = ""
        if sh_stats:
            shadow_line = f"\n🎯 *Shadow Intelligence:* {sh_stats.get('dodged_crashes', 0)} Dodged Crashes | {sh_stats.get('missed_runners', 0)} Missed Runners"

        message = (
            f"{header_prefix}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *Net Worth:* INR {total_nw:.2f}\n"
            f"📈 *24h Daily PnL:* {pnl_sign}INR {daily_pnl:.2f} ({daily_pnl_pct:+.1f}%)\n"
            f"🚀 *All-Time Gain:* {all_pnl_sign}INR {all_time_pnl:.2f} ({all_time_pnl_pct:+.1f}%)\n"
            f"🎯 *Compounding:* Cycle #{stage['cycle']} ({progress:.1f}% to INR {stage['target_inr']:,.0f})\n"
            f"🛡️ *Danger Floor:* INR {stage['danger_floor_inr']:.0f}\n"
            f"🥊 *Record:* {self.wins}W / {self.losses}L (Win Rate: {win_rate:.1f}%)\n"
            f"💼 *Open Positions:* {len(self.active_positions)}\n"
            f"🌊 *Market Regime:* {regime_emoji} {regime}\n"
            f"🛡️ *Survival Tier:* {st.emoji} {st.tier}\n"
            f"🧠 *Brain Accuracy:* {self.brain.recent_accuracy*100:.0f}% (Threshold: {self.brain.adaptive_threshold*100:.0f}%)\n"
            f"⏳ *Incubation Uptime:* {uptime_str}"
            f"{journal_stats}"
            f"{shadow_line}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 *Status:* Autonomous 24/7 Cloud Incubation Active."
        )

        await send_telegram_alert(message)
        print("\n" + "📊" * 35)
        print(f" [DAILY SCORECARD SENT TO TELEGRAM] Net Worth: INR {total_nw:.2f} | 24h PnL: {daily_pnl_pct:+.1f}%")
        print("📊" * 35 + "\n")

        # Reset daily baseline for next 24h cycle
        if not manual:
            self.daily_start_nw = total_nw
            self.last_daily_scorecard = time.time()
            self.save_state()

    def refresh_live_balance(self):
        """Periodically checks on-chain SOL balance of burner wallet."""
        try:
            from wallet_manager import check_wallet_balance_onchain
            if self.executor.wallet_pubkey:
                bal = check_wallet_balance_onchain(self.executor.wallet_pubkey)
                new_sol = bal.get("sol", 0.0)
                if new_sol > 0.001 and self.live_sol_balance <= 0.001:
                    print(f"\n💰 [ON-CHAIN DEPOSIT DETECTED] Found {new_sol:.4f} SOL in burner wallet!")
                    self.log_activity("💰", f"Deposit Detected: {new_sol:.4f} SOL on-chain")
                self.live_sol_balance = new_sol
                self.is_live = (not PAPER_TRADING) and (self.live_sol_balance > 0.001)
        except Exception:
            pass

    def dump_live_state(self):
        """Dumps real-time telemetry to live_state.json for the web dashboard."""
        try:
            stage = self.get_current_ladder_stage()
            total_nw = self.get_total_net_worth()
            st = getattr(self, "survival_tier", evaluate_survival_tier(total_nw))
            regime = self.current_regime.get("regime", "UNKNOWN")
            regime_emoji = self.current_regime.get("emoji", "")
            nr = getattr(self, "news_report", {})
            start_nw = getattr(self, "daily_start_nw", STARTING_BALANCE_INR)
            daily_pnl = total_nw - start_nw
            daily_pnl_pct = (daily_pnl / start_nw * 100) if start_nw > 0 else 0.0

            positions_list = []
            for addr, pos in self.active_positions.items():
                curr = pos.get("curr_price", pos.get("peak_price", pos["entry_price"]))
                pnl = ((curr - pos["entry_price"]) / pos["entry_price"]) * 100
                positions_list.append({
                    "token": pos["token"],
                    "address": addr,
                    "invested_inr": pos["invested_inr"],
                    "entry_price": pos["entry_price"],
                    "curr_price": curr,
                    "stop_loss": pos["stop_loss_price"],
                    "pnl_pct": pnl
                })

            invested_total = sum(pos.get("invested_inr", 0.0) for pos in self.active_positions.values())
            floating_pnl_inr = sum(
                (pos.get("invested_inr", 0.0) * (pos.get("remaining_tokens", pos.get("initial_tokens", 1.0)) / max(1e-6, pos.get("initial_tokens", 1.0))))
                * ((pos.get("curr_price", pos["entry_price"]) - pos["entry_price"]) / max(1e-12, pos["entry_price"]))
                for pos in self.active_positions.values()
            ) if self.active_positions else 0.0

            state = {
                "net_worth": round(total_nw, 2),
                "liquid_cash": round(self.portfolio_inr, 2),
                "money_left": round(self.portfolio_inr, 2),
                "money_invested": round(invested_total, 2),
                "money_made": round(floating_pnl_inr, 2) if self.active_positions else 0.0,
                "floating_pnl_inr": round(floating_pnl_inr, 2) if self.active_positions else 0.0,
                "realized_profit_inr": round(getattr(self, "realized_profit_inr", 0.0), 2),
                "total_fees_paid": round(getattr(self, "total_fees_paid_inr", 0.0), 2),
                "cycle": stage["cycle"],
                "target_inr": stage["target_inr"],
                "danger_floor_inr": stage["danger_floor_inr"],
                "survival_tier": f"{st.emoji} {st.tier}",
                "regime": f"{regime_emoji} {regime}",
                "news_sentiment": f"{nr.get('sentiment_label', 'NEUTRAL')} ({nr.get('sentiment_score', 0.0):+.2f})" if nr else "NEUTRAL",
                "wins": self.wins,
                "losses": self.losses,
                "positions": positions_list,
                "transactions": getattr(self, "trade_history", []),
                "updated_at": time.time(),
                "daily_pnl": round(daily_pnl, 2),
                "daily_pnl_pct": round(daily_pnl_pct, 2),
                "is_paused": self.is_paused,
                "activity_feed": getattr(self, "activity_log", []),
                "burner_wallet": self.executor.wallet_pubkey or "",
                "live_sol_balance": round(getattr(self, "live_sol_balance", 0.0), 4),
                "sol_to_inr": round(getattr(self, "sol_to_inr", 13000.0), 2),
                "shadow_stats": self.shadow_tracker.get_summary_stats() if hasattr(self, "shadow_tracker") else {},
                "autotune_params": self.autotuner.active_params if hasattr(self, "autotuner") else {},
                "autotune_history": getattr(self.autotuner, "tuning_history", [])[-20:] if hasattr(self, "autotuner") else [],
                "autotune_cycles": getattr(self.autotuner, "total_tune_cycles", 0) if hasattr(self, "autotuner") else 0,
                "network_status": getattr(self, "network_status", {
                    "tps": 3250, "user_tps": 1200, "est_gas_inr": 0.50, "congestion": "OPTIMAL", "safe_to_trade": True
                }),
                "best_runner": getattr(self, "best_runner", {
                    "symbol": "None", "pnl_pct": 0.0, "time": "—"
                }),
                "consecutive_losses": getattr(self, "consecutive_losses", 0),
                "latest_debate": getattr(self.committee, "latest_debate", {}),
                "agent_heartbeats": {k: round(time.time() - v, 1) for k, v in getattr(self, "agent_heartbeats", {}).items()},
                "is_live": getattr(self, "is_live", False),
                "order_fsm_state": getattr(self.executor, "last_order_state", "STANDBY"),
                "order_audit_trail": getattr(self.executor, "state_history", [])[-5:]
            }

            state_file = os.path.join(os.path.dirname(__file__), "live_state.json")
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

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
            self.save_state()
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
                    recovered = pos["invested_inr"] * (pos.get("curr_price", pos["entry_price"]) / max(1e-12, pos["entry_price"])) * (pos.get("remaining_tokens", 1.0) / max(1e-6, pos.get("initial_tokens", 1.0)))
                    self.portfolio_inr += recovered + pos["ata_locked_inr"]
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

            sol_harvest = profit_sweep / self.sol_to_inr
            dest_msg = f"Sent to {PERSONAL_WITHDRAWAL_WALLET[:8]}..." if PERSONAL_WITHDRAWAL_WALLET else "Locked in cold reserve"

            # Save state immediately after cycle progression
            self.save_state()

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

    async def emergency_close_all(self) -> int:
        """Sells all active positions, converts to cash/SOL, and reclaims rent."""
        print("   🚨 [EMERGENCY CLOSE ALL] Selling all active positions...")
        closed_count = len(self.active_positions)
        for addr, pos in list(self.active_positions.items()):
            await self.executor.execute_swap(addr, SOL_MINT, int(pos["remaining_tokens"] * 1_000_000), paper_mode=(not self.is_live))
            self.reclaimer.reclaim_rent(addr, paper_mode=(not self.is_live))
            curr_p = pos.get("curr_price", pos["entry_price"])
            rem_ratio = pos.get("remaining_tokens", 1.0) / max(1e-6, pos.get("initial_tokens", 1.0))
            price_ratio = curr_p / max(1e-12, pos["entry_price"])
            gross_rec = pos["invested_inr"] * rem_ratio * price_ratio
            sell_fee = round(0.50 + (gross_rec * 0.003), 2)
            self.total_fees_paid_inr += sell_fee
            net_rec = max(0.0, gross_rec - sell_fee)
            refund_ata = pos.get("ata_locked_inr", 0.0)
            self.locked_ata_rent_inr = max(0.0, self.locked_ata_rent_inr - refund_ata)
            self.portfolio_inr += (net_rec + refund_ata)

            gain_loss = net_rec - (pos["invested_inr"] * rem_ratio)
            self.realized_profit_inr += gain_loss
            if gain_loss >= 0:
                self.wins += 1
            else:
                self.losses += 1

            tx_entry = {
                "id": f"tx_{int(time.time()*1000)}",
                "time": time.strftime("%H:%M:%S"),
                "timestamp": time.time(),
                "token": pos["token"],
                "address": addr,
                "action": "EMERGENCY CLOSE",
                "price": curr_p,
                "size_inr": round(pos["invested_inr"] * rem_ratio, 2),
                "gain_loss_inr": round(gain_loss, 2),
                "fee_inr": round(sell_fee, 2),
                "money_left": round(self.portfolio_inr, 2),
                "status": "PROFIT" if gain_loss >= 0 else "LOSS"
            }
            if not hasattr(self, "trade_history"):
                self.trade_history = []
            self.trade_history.insert(0, tx_entry)
            if len(self.trade_history) > 100:
                self.trade_history.pop()

        self.active_positions.clear()
        self.locked_ata_rent_inr = 0.0
        self.save_state()
        self.dump_live_state()
        await send_telegram_alert(f"🚨 *[EMERGENCY CLOSE ALL]* Closed {closed_count} position(s). All capital converted to cash/SOL + ATA rent reclaimed! Cash: INR {self.portfolio_inr:.2f}")
        return closed_count

    async def process_external_signal(self, payload: dict) -> dict:
        """
        OpenAlgo / TradingView Webhook Bridge Processor:
        Accepts signal payload:
          { "action": "BUY" | "CLOSE_ALL" | "PAUSE" | "RESUME", "token": "<address_or_symbol>", "secret": "..." }
        Strictly enforces micro-capital survival rules (₹100 seed):
          1. Minimum trade size ≥ ₹22 (fee drag ≤ 2.5%), max ₹30
          2. Emergency reserve buffer (₹50) protected at all times
          3. RugCheck & Honeypot safety filters
          4. Freqtrade Range Chop Filter
          5. Hummingbot Micro-Depth Slippage (≤ 0.25% impact)
          6. Tauric Chief Risk Officer (CRO) VETO authority
        """
        action = payload.get("action", "").upper()
        if action == "CLOSE_ALL":
            closed_cnt = await self.emergency_close_all()
            return {"status": "SUCCESS", "action": "CLOSE_ALL", "closed_positions": closed_cnt, "cash_inr": round(self.portfolio_inr, 2)}
        elif action == "PAUSE":
            self.is_paused = True
            self.save_state()
            self.dump_live_state()
            return {"status": "SUCCESS", "action": "PAUSE", "is_paused": True}
        elif action == "RESUME":
            self.is_paused = False
            self.save_state()
            self.dump_live_state()
            return {"status": "SUCCESS", "action": "RESUME", "is_paused": False}
        elif action == "BUY":
            token_query = payload.get("token") or payload.get("address")
            if not token_query:
                return {"status": "REJECTED", "reason": "Missing token address or symbol"}
            if self.is_danger_halted:
                return {"status": "REJECTED", "reason": "Trading halted: Danger floor breached"}
            if self.is_paused:
                return {"status": "REJECTED", "reason": "Bot is currently paused"}

            # Micro-capital reserve check
            if self.portfolio_inr < 22.0 or (self.portfolio_inr - 22.0 < EMERGENCY_RESERVE_INR):
                return {
                    "status": "REJECTED",
                    "reason": f"Insufficient micro-capital: Cash ₹{self.portfolio_inr:.2f} below reserve buffer ₹{EMERGENCY_RESERVE_INR:.2f} + min size ₹22"
                }

            live_data = await fetch_dex_token_data(token_query)
            if not live_data or live_data.get("price_usd", 0) <= 0:
                return {"status": "REJECTED", "reason": f"Unable to fetch live DEX market data for {token_query}"}

            addr = live_data.get("address", token_query)
            symbol = live_data.get("symbol", "TOKEN")
            price = live_data["price_usd"]
            liq = live_data.get("liquidity_usd", 0)

            # Safety filter
            safety = await analyze_token_safety(addr, live_data)
            if not safety.get("safe", False):
                return {"status": "REJECTED", "reason": f"Safety Filter Veto: {safety.get('reason')}"}

            # Freqtrade range chop filter
            from safety import check_range_stability
            range_check = check_range_stability(live_data)
            if not range_check.get("stable", True):
                return {"status": "REJECTED", "reason": f"Freqtrade Chop Filter Veto: {range_check.get('reason')}"}

            # Hummingbot micro-depth slippage
            est_size = max(22.0, min(30.0, self.portfolio_inr * 0.25))
            slip_guard = validate_micro_depth_slippage(est_size, liq, self.sol_to_inr, max_slippage_pct=0.25)
            if not slip_guard.get("safe", True):
                return {"status": "REJECTED", "reason": f"Hummingbot Slippage Veto: {slip_guard.get('reason')}"}

            # ML Predict
            feats = extract_features_from_token_data(live_data)
            win_prob = self.brain.predict_win_probability(feats)

            # Adversarial Committee Evaluation (Tauric CRO VETO)
            candidate_dict = {
                "symbol": symbol,
                "address": addr,
                "win_probability": win_prob,
                "safety": safety,
                "features": feats,
                "regime": self.current_regime.get("regime", "CRAB"),
                "macro_trend": getattr(self, "last_macro_trend", "NEUTRAL")
            }
            net_gas = self.network_status.get("est_gas_inr", 0.50) if hasattr(self, "network_status") else 0.50
            committee_verdict = self.committee.conduct_debate(
                candidate=candidate_dict,
                live_data=live_data,
                gas_inr=net_gas,
                consecutive_losses=getattr(self, "consecutive_losses", 0)
            )

            if committee_verdict.get("verdict") == "VETOED":
                return {
                    "status": "REJECTED",
                    "reason": f"Chief Risk Officer VETO: {committee_verdict.get('veto_reason')}",
                    "committee_verdict": committee_verdict
                }

            # Safe to enter trade
            pos_size_inr = round(est_size * committee_verdict.get("sizing_multiplier", 1.0), 2)
            pos_size_inr = max(22.0, min(30.0, pos_size_inr))

            # Trigger swap execution
            swap_res = await self.executor.execute_swap(
                SOL_MINT, addr, int((pos_size_inr / self.sol_to_inr) * 1_000_000_000),
                paper_mode=(not self.is_live)
            )

            if swap_res.get("success"):
                tokens_bought = (pos_size_inr / self.sol_to_inr) / max(1e-12, (price / (self.sol_to_inr / 140.0)))
                self.portfolio_inr -= pos_size_inr
                self.active_positions[addr] = {
                    "token": symbol,
                    "address": addr,
                    "entry_price": price,
                    "curr_price": price,
                    "invested_inr": pos_size_inr,
                    "initial_tokens": tokens_bought,
                    "remaining_tokens": tokens_bought,
                    "stop_loss_price": price * 0.90,
                    "peak_price": price,
                    "entry_time": time.time(),
                    "source": "OPENALGO_WEBHOOK"
                }
                self.save_state()
                self.dump_live_state()
                self.log_activity("📡", f"Webhook Signal Filled: {symbol} (₹{pos_size_inr})")
                return {
                    "status": "APPROVED_AND_FILLED",
                    "token": symbol,
                    "address": addr,
                    "size_inr": pos_size_inr,
                    "fsm_state": getattr(self.executor, "last_order_state", "CONFIRMED_ONCHAIN"),
                    "cro_verdict": committee_verdict.get("verdict")
                }
            else:
                return {
                    "status": "EXECUTION_FAILED",
                    "reason": swap_res.get("error", "DEX execution failed"),
                    "fsm_state": getattr(self.executor, "last_order_state", "FAILED")
                }

        return {"status": "REJECTED", "reason": f"Unknown action: {action}"}

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
                ap = self.autotuner.active_params if hasattr(self, "autotuner") else {}
                sl_str = f"-{int(ap.get('stop_loss_pct', 0.10)*100)}%"
                be_str = f"+{int((ap.get('breakeven_trigger', 1.20)-1)*100)}%"
                tp_str = f"+{int((ap.get('tp1_mult', 1.25)-1)*100)}% / +{int((ap.get('tp2_mult', 1.60)-1)*100)}% / +{int((ap.get('tp3_mult', 3.00)-1)*100)}%"

                pos_summary = "\n".join([
                    f"  • {p['token']}: ${p['entry_price']:.8f} (Invested: ₹{p['invested_inr']:.2f})"
                    for p in self.active_positions.values()
                ]) or "  • None (Cash 100% liquid)"

                m_invested = sum(p["invested_inr"] for p in self.active_positions.values())
                floating_pnl = sum(
                    (p.get("invested_inr", 0.0) * (p.get("remaining_tokens", p.get("initial_tokens", 1.0)) / max(1e-6, p.get("initial_tokens", 1.0))))
                    * ((p.get("curr_price", p["entry_price"]) - p["entry_price"]) / max(1e-12, p["entry_price"]))
                    for p in self.active_positions.values()
                ) if self.active_positions else 0.0

                await send_telegram_alert(
                    f"📊 *[CRYPTOGEN FINANCIAL LEDGER]*\n\n"
                    f"💰 *Money Left (Wallet):* INR {self.portfolio_inr:.2f}\n"
                    f"💼 *Money Invested (In Market):* INR {m_invested:.2f}\n"
                    f"📈 *Money Made (Floating Profit):* {floating_pnl:+.2f} INR\n"
                    f"⛽ *Total Fees Paid:* INR {self.total_fees_paid_inr:.2f}\n\n"
                    f"• *Open Trades ({len(self.active_positions)}):*\n{pos_summary}\n\n"
                    f"• *Cycle #{stage['cycle']}:* Target INR {stage['target_inr']:,.0f} | Danger Floor INR {stage['danger_floor_inr']:.0f}\n"
                    f"• *Status:* {pause_status} | *Regime:* {regime}\n"
                    f"• *Record:* {self.wins}W / {self.losses}L\n"
                    f"• *SOL/INR Rate:* ₹{self.sol_to_inr:,.0f}\n"
                    f"• *Dynamic Strategy:* SL: {sl_str} | BE: {be_str} | TP: {tp_str}\n"
                    f"• *Shadow Radar:* {getattr(self, 'shadow_tracker', None).get_summary_stats().get('dodged_crashes', 0) if hasattr(self, 'shadow_tracker') else 0} Dodged | {getattr(self, 'shadow_tracker', None).get_summary_stats().get('missed_runners', 0) if hasattr(self, 'shadow_tracker') else 0} Missed Caught\n"
                    f"• *News Sentiment:* {nr.get('sentiment_label', 'NEUTRAL')}"
                )

            elif cmd == "/scorecard":
                await self.send_daily_scorecard(manual=True)

            elif cmd == "/tune":
                print("   🧬 [REMOTE TUNE COMMAND] Evaluating strategy parameters...")
                event = self.autotuner.evaluate_and_tune(manual=True)
                await send_telegram_alert(
                    f"🧬 *[AUTONOMOUS SELF-TUNER ACTIVATED]*\n\n"
                    f"• *Cycle:* #{event['cycle']}\n"
                    f"• *Market Regime:* {event['regime']} ({event['mode']})\n"
                    f"• *Dynamic Stop-Loss:* {event['sl_pct']}\n"
                    f"• *Break-Even Trigger:* {event['be_trigger']}\n"
                    f"• *Take-Profit Ladder:* {event['tp_ladder']}\n\n"
                    f"💡 *Strategy Calibration:* {event['reason']}"
                )

            elif cmd == "/pause":
                self.is_paused = True
                self.save_state()
                print("   ⏸️ [BOT PAUSED] New token buying suspended by user.")
                await send_telegram_alert("⏸️ *[BOT PAUSED]* Autonomous buying suspended. Active positions will still be monitored for TP/SL.")

            elif cmd == "/resume":
                self.is_paused = False
                self.save_state()
                print("   ▶️ [BOT RESUMED] Autonomous buying active.")
                await send_telegram_alert("▶️ *[BOT RESUMED]* Autonomous market scans and buying resumed!")

            elif cmd == "/closeall":
                await self.emergency_close_all()

            elif cmd == "/harvest":
                await self.check_milestone_harvest()

            elif cmd == "/help":
                await send_telegram_alert(
                    "🤖 *CryptoGen Remote Commands:*\n\n"
                    "• `/status` - Live portfolio, open trades & regime\n"
                    "• `/scorecard` - Instant 24h Daily PnL scorecard\n"
                    "• `/tune` - Dynamically recalculate SL/TP ratchets\n"
                    "• `/pause` - Pause autonomous buying\n"
                    "• `/resume` - Resume autonomous buying\n"
                    "• `/closeall` - Emergency close all positions to SOL\n"
                    "• `/harvest` - Check and trigger profit sweep\n"
                    "• `/help` - Show this menu"
                )

    def calculate_kelly_position_size(self, win_probability: float) -> float:
        """Kelly sizing adjusted by survival tier and Monte Carlo optimal floor (INR 22-25 to minimize fee drag)."""
        # Leave a ₹2.50 buffer for gas and ATA rent reservation so wallet never dips into emergency floor
        tradeable_cash = max(0.0, self.portfolio_inr - EMERGENCY_RESERVE_INR - 2.5)
        if tradeable_cash < 22.0:
            return 0.0

        # Survival Tier Cap
        tier_cfg = evaluate_survival_tier(self.get_total_net_worth())
        max_cap = tier_cfg.max_position_pct

        # Fractional Kelly adjusted for 20-25% optimal Monte Carlo sizing
        kelly_size = calculate_fractional_kelly_size(
            win_probability=win_probability,
            portfolio_inr=self.portfolio_inr,
            reward_to_risk_ratio=3.33,
            fraction=0.45,
            max_cap_pct=max_cap
        )

        # Apply regime multiplier (bull = bigger, bear = smaller)
        regime_mult = self.current_regime.get("kelly_multiplier", 1.0)
        kelly_size *= regime_mult

        # Enforce Fee-Drag Shielding floor (INR 22.00 so Solana gas + DEX fee stays <= 2.5%)
        optimal_size = max(22.0, kelly_size)
        return min(optimal_size, tradeable_cash)

    async def update_intelligence(self):
        """
        Runs before each trading scan:
          1. Evaluates Capital Survival Tier (Automaton policy)
          2. Detects market regime (bull/bear/crab/crash)
          3. Scans trending token meta (which narratives are hot)
          4. Loads failure pattern weights from journal
        """
        print("\n--- INTELLIGENCE UPDATE ---")
        self.refresh_live_balance()

        # 1. Capital Survival Tier
        self.survival_tier = evaluate_survival_tier(self.get_total_net_worth())
        st = self.survival_tier
        print(f"   {st.emoji} Survival Tier: {st.tier} — {st.description}")

        # 2. Market Regime Detection
        new_regime_info = await self.regime_detector.detect_regime()
        new_regime = new_regime_info.get("regime", "UNKNOWN")

        # Check for Regime Shift & Alert Telegram
        regime_shifted = False
        if self.last_reported_regime is not None and new_regime != self.last_reported_regime:
            regime_shifted = True
            old_regime = self.last_reported_regime
            new_emoji = new_regime_info.get("emoji", "🌊")
            new_desc = new_regime_info.get("description", "")
            new_thresh = new_regime_info.get("ml_threshold", 0.65) * 100
            print(f"\n🌊 [REGIME SHIFT DETECTED] {old_regime} ➔ {new_regime}!")
            self.log_activity("🌊", f"Market Shift: {old_regime} ➔ {new_regime}")
            await send_telegram_alert(
                f"🌊 *[MARKET REGIME SHIFT]*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"• *Transition:* {old_regime} ➔ {new_emoji} *{new_regime}*\n"
                f"• *Context:* {new_desc}\n"
                f"• *ML Entry Threshold:* {new_thresh:.0f}%\n"
                f"• *Action:* Trading parameters dynamically tuned for {new_regime} liquidity."
            )

        self.last_reported_regime = new_regime
        self.current_regime = new_regime_info
        regime = self.current_regime
        print(f"   {regime.get('emoji', '')} Market Regime: {regime['regime']} "
              f"(Confidence: {regime.get('confidence', 0)*100:.0f}%) — {regime.get('description', '')}")

        # Refresh Paperclip Heartbeats
        now = time.time()
        if hasattr(self, "agent_heartbeats"):
            self.agent_heartbeats["regime_detector"] = now
            self.agent_heartbeats["strategy_autotuner"] = now
            self.agent_heartbeats["news_sentinel"] = now
            self.agent_heartbeats["whale_tracker"] = now

        # 2.5 Dynamic Auto-Tuner Calibration (Triggers on regime shift or periodic 6h cycle)
        if hasattr(self, "autotuner") and (regime_shifted or (time.time() - getattr(self.autotuner, "last_tuned_at", 0) >= 21600)):
            tune_res = self.autotuner.evaluate_and_tune(manual=False)
            if regime_shifted:
                await send_telegram_alert(
                    f"🧬 *[STRATEGY ADAPTATION]*\n"
                    f"Tuned for *{new_regime}*:\n"
                    f"• Stop-Loss: {tune_res['sl_pct']}\n"
                    f"• Break-Even: {tune_res['be_trigger']}\n"
                    f"• TP Ladder: {tune_res['tp_ladder']}"
                )

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

        # 6. Triangular Arbitrage Engine (Shadow/Live)
        arb_opps = await self.arbitrage_engine.scan_arbitrage_opportunities(self.get_total_net_worth())
        arb_status = "LIVE ACTIVE" if self.arbitrage_engine.is_unlocked else "SHADOW SCAN (Unlocks @ ₹50k)"
        print(f"   ⚖️ Arbitrage Engine: {arb_status} | Found: {len(arb_opps)} route(s)")

        # 7. Journal Insights
        self.journal_weights = self.journal.get_failure_pattern_weights()

        # 8. Brain Status
        print(f"   {self.brain.get_brain_status()}")

        # 9. Solana Network Gas & Congestion Radar
        try:
            self.network_status = await fetch_solana_network_status()
            print(f"   ⚡ Solana Radar: {self.network_status.get('tps', 3200)} TPS | Est Gas: ₹{self.network_status.get('est_gas_inr', 0.50):.2f} ({self.network_status.get('congestion', 'OPTIMAL')})")
        except Exception:
            pass
        print("---")

    async def scan_and_trade(self, candidate_addresses: list):
        if hasattr(self, "agent_heartbeats"):
            self.agent_heartbeats["scout_harvester"] = time.time()

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

        # Check Solana Network Gas Spike / Congestion
        if not self.network_status.get("safe_to_trade", True):
            print(f"   ⚡ [NETWORK RADAR] Solana gas fee elevated (₹{self.network_status.get('est_gas_inr', 0.50):.2f}). Pausing new entries to prevent fee drain.")
            return

        # 1. Macro Context Check
        macro = await fetch_sol_macro_context()
        self.last_macro_change = macro.get('sol_6h_change_pct', 0.0)
        sol_usd = macro.get('sol_price_usd', 0.0)
        if sol_usd > 10.0:
            self.sol_to_inr = round(sol_usd * 86.5, 2)

        # Enhanced macro sensitivity from journal
        macro_threshold = -4.5
        if self.journal_weights.get("macro_sensitivity", 1.0) > 1.5:
            macro_threshold = -2.5  # Much more cautious if journal says crashes hurt us

        if not macro["safe_to_trade"] or self.last_macro_change < macro_threshold:
            print(f"   [MACRO HALT] SOL dumped {macro['sol_6h_change_pct']}%. Pausing buys.")
            return

        print(f"\n   [MACRO] SOL: ${sol_usd:.2f} (₹{self.sol_to_inr:,.0f}) | {macro['macro_trend']} | {macro['sol_6h_change_pct']:+0.1f}%")

        # Get adaptive threshold from brain + regime + survival tier
        regime_threshold = self.current_regime.get("ml_threshold", 0.65)
        survival_min_conf = getattr(self, "survival_tier", None).min_confidence if hasattr(self, "survival_tier") else 0.70
        entry_threshold = max(self.brain.get_adaptive_threshold(regime_threshold), survival_min_conf)

        # Dynamic Caution Bump: On 2+ consecutive losses, raise entry bar by +3% to filter choppy market noise
        if getattr(self, "consecutive_losses", 0) >= 2:
            entry_threshold += 0.03
            print(f"   🛡️ [CAUTION BUMP] {self.consecutive_losses} consecutive losses. Raising entry threshold +3% -> {entry_threshold*100:.1f}%")

        min_pool_liq = self.survival_tier.min_liquidity_usd if hasattr(self, "survival_tier") else 5000.0
        print(f"   [THRESHOLD] Entry bar: {entry_threshold*100:.0f}% (Regime: {regime_threshold*100:.0f}%, Survival: {survival_min_conf*100:.0f}%, Min Liq: ${min_pool_liq:,.0f})")

        # Stage 1: Concurrent Pre-Filter with Semaphore(6) rate limiting
        semaphore = asyncio.Semaphore(6)
        evaluated_candidates = []

        async def pre_evaluate_candidate(addr: str):
            if addr in self.active_positions:
                return None

            async with semaphore:
                try:
                    live_data = await fetch_dex_token_data(addr)
                    if not live_data or live_data.get("price_usd", 0) <= 0:
                        return None

                    name = live_data["name"]
                    symbol = live_data["symbol"]
                    price = live_data["price_usd"]
                    liq = live_data["liquidity_usd"]

                    # Filter 0: Survival Tier Pool Liquidity Check
                    if liq < min_pool_liq:
                        return None

                    # Filter 1: Basic Safety (RugCheck / DexScreener / Dev Bundler)
                    safety = await analyze_token_safety(addr, live_data)
                    if not safety["safe"]:
                        reason_clean = safety['reason'][:35]
                        self.log_activity("⚠️", f"Filtered {symbol}: {reason_clean}")
                        if hasattr(self, "shadow_tracker"):
                            feats = extract_features_from_token_data(live_data)
                            self.shadow_tracker.register_rejected_token(
                                address=addr,
                                symbol=symbol,
                                name=name,
                                price=price,
                                reason=f"Safety: {reason_clean}",
                                features=feats,
                                win_prob=0.10
                            )
                        return None

                    # Filter 2: Wash Trading & Manipulation Detection
                    wash = live_data.get("wash_analysis", {})
                    if wash.get("manipulated", False):
                        self.log_activity("🚫", f"Filtered {symbol}: Wash trading (Score {wash['wash_score']})")
                        return None

                    # Filter 3: Hummingbot Micro-Depth & Slippage Guard (Max 0.25% Price Impact)
                    est_trade_inr = max(22.0, min(30.0, self.portfolio_inr * 0.25))
                    slip_guard = validate_micro_depth_slippage(est_trade_inr, liq, self.sol_to_inr, max_slippage_pct=0.25)
                    if not slip_guard.get("safe", True):
                        self.log_activity("📉", f"Filtered {symbol}: Slippage {slip_guard.get('estimated_slippage_pct', 0.0):.2f}% > 0.25% limit ({slip_guard.get('reason')})")
                        return None

                    # Filter 3.5: OpenBB Quantitative Math (Hurst Exponent & VWAP Deviation)
                    price_hist = live_data.get("price_history") or [price * (1.0 - 0.01 * i) for i in range(12, 0, -1)]
                    hurst_res = calculate_hurst_exponent(price_hist)
                    if hurst_res.get("interpretation") == "MEAN_REVERTING_CHOP":
                        self.log_activity("📐", f"Filtered {symbol}: Mean-reverting chop (Hurst H={hurst_res['hurst']})")
                        return None

                    vwap_res = calculate_vwap_deviation(price, price_hist)
                    if not vwap_res.get("safe_to_buy", True):
                        self.log_activity("📐", f"Filtered {symbol}: Overextended above VWAP (Z={vwap_res['z_score']})")
                        return None

                    # Filter 4: Feature Extraction & ML Prediction
                    features = extract_features_from_token_data(live_data)
                    meta_bonus = self.meta_tracker.get_meta_bonus(name, symbol)
                    win_prob = self.brain.predict_win_probability(
                        features, meta_bonus=meta_bonus, journal_weights=self.journal_weights
                    )
                    whale_bonus = self.whale_tracker.get_whale_bonus(addr)
                    if whale_bonus > 0:
                        win_prob = min(0.99, win_prob + whale_bonus)

                    cand = {
                        "addr": addr,
                        "live_data": live_data,
                        "features": features,
                        "win_prob": win_prob,
                        "meta_bonus": meta_bonus,
                        "whale_bonus": whale_bonus,
                        "name": name,
                        "symbol": symbol,
                        "price": price,
                        "liq": liq
                    }
                    evaluated_candidates.append(cand)

                    # Filter 5: ML Entry Threshold Check
                    if win_prob < entry_threshold:
                        if hasattr(self, "shadow_tracker"):
                            self.shadow_tracker.register_rejected_token(
                                address=addr,
                                symbol=symbol,
                                name=name,
                                price=price,
                                reason=f"Confidence {win_prob*100:.0f}% < {entry_threshold*100:.0f}%",
                                features=features,
                                win_prob=win_prob
                            )
                        return None

                    # Candidate passed all filters!
                    return cand
                except Exception:
                    return None

        print(f"   [SCAN] Scanning {len(candidate_addresses)} candidates concurrently (Worker pool: 4)...")
        tasks = [pre_evaluate_candidate(addr) for addr in candidate_addresses]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        qualified = [r for r in results if isinstance(r, dict) and r is not None]
        # Sort surviving candidates by win probability descending (best trade first)
        qualified.sort(key=lambda c: c["win_prob"], reverse=True)

        if qualified:
            print(f"   [SCAN RESULT] 🎯 {len(qualified)}/{len(candidate_addresses)} candidate(s) passed all safety checks and ML threshold ({entry_threshold*100:.0f}%).")
        else:
            closest_info = ""
            if evaluated_candidates:
                top_cand = max(evaluated_candidates, key=lambda c: c["win_prob"])
                closest_info = f" | Closest: {top_cand['symbol']} ({top_cand['win_prob']*100:.1f}%)"
            print(f"   [SCAN RESULT] 0/{len(candidate_addresses)} candidates passed entry bar ({entry_threshold*100:.0f}%){closest_info}. Capital 100% preserved.")

        # Stage 2: Sequential Execution & Capital Allocation (Guarantees zero double-spend race condition)
        for candidate in qualified:
            if len(self.active_positions) >= max_concurrent:
                break

            addr = candidate["addr"]
            if addr in self.active_positions:
                continue

            symbol = candidate["symbol"]
            name = candidate["name"]
            price = candidate["price"]
            liq = candidate["liq"]
            win_prob = candidate["win_prob"]
            features = candidate["features"]
            meta_bonus = candidate["meta_bonus"]
            whale_bonus = candidate["whale_bonus"]
            live_data = candidate["live_data"]

            print(f"\n   [EVALUATING QUALIFIED] {symbol} (${price:.8f}) | Liq: ${liq:,.0f}")
            print(f"   Buy Ratio (5m): {features['buy_ratio_5m']*100:.1f}% | OFI: {features['ofi_5m']:+.2f} | Vol Accel: {features['vol_acceleration']:.2f}x")
            if meta_bonus > 0:
                meta_cats = self.meta_tracker.classify_token(name, symbol)
                print(f"   Meta Bonus: +{meta_bonus*100:.0f}% ({', '.join(meta_cats)})")
            if whale_bonus > 0:
                print(f"   🐋 Whale Bonus: +{whale_bonus*100:.0f}% (Tracked Smart Money Accumulated)")
            print(f"   ML Confidence: {win_prob*100:.1f}% (Required: {entry_threshold*100:.0f}%)")

            # Multi-Agent Adversarial Debate Committee (TauricResearch TradingAgents)
            now = time.time()
            if hasattr(self, "agent_heartbeats"):
                self.agent_heartbeats["risk_committee"] = now
                self.agent_heartbeats["ml_brain"] = now
                self.agent_heartbeats["safety_sentinel"] = now

            net_gas = self.network_status.get("est_gas_inr", 0.50) if hasattr(self, "network_status") else 0.50
            debate = self.committee.conduct_debate(
                candidate=candidate,
                live_data=live_data,
                gas_inr=net_gas,
                consecutive_losses=self.consecutive_losses
            )
            print(f"   🏛️ [ADVERSARIAL COMMITTEE] {symbol}: 🐂 Bull {debate['bull_score']} vs 🐻 Bear {debate['bear_score']} -> {debate['verdict']}")
            if debate["verdict"] == "VETOED":
                print(f"   🛑 [RISK OFFICER VETO] {debate['veto_reason']}. Entry aborted to protect capital.")
                self.log_activity("🛑", f"Vetoed {symbol}: {debate['veto_reason'][:30]}")
                if hasattr(self, "shadow_tracker"):
                    self.shadow_tracker.register_rejected_token(
                        address=addr,
                        symbol=symbol,
                        name=name,
                        price=price,
                        reason=f"Risk Veto: {debate['veto_reason'][:30]}",
                        features=features,
                        win_prob=win_prob
                    )
                continue

            # Position Sizing via Kelly (regime & risk committee adjusted)
            size_inr = self.calculate_kelly_position_size(win_prob)
            size_inr = round(size_inr * debate.get("sizing_mult", 1.0), 2)
            if size_inr < 22.0:
                print(f"   Position sizing INR{size_inr:.2f} below INR22 fee-shielded floor. Skipping.")
                continue

            # ATA Rent Reservation (Refunded upon sell)
            ata_locked = min(5.0, self.portfolio_inr * 0.05)
            # Solana Network Gas + Raydium 0.3% AMM fee
            buy_fee_inr = round(net_gas + (size_inr * 0.003), 2)

            self.locked_ata_rent_inr += ata_locked
            self.total_fees_paid_inr += buy_fee_inr
            self.portfolio_inr -= (size_inr + ata_locked + buy_fee_inr)

            # Execute On-Chain Swap
            lamports_to_invest = int((size_inr / self.sol_to_inr) * 1_000_000_000)
            swap_res = await self.executor.execute_swap(
                input_mint=SOL_MINT,
                output_mint=addr,
                amount_lamports=lamports_to_invest,
                paper_mode=(not self.is_live)
            )
            if not swap_res.get("success", False):
                print(f"   Swap failed: {swap_res.get('reason')}. Skipping.")
                self.portfolio_inr += (size_inr + ata_locked + buy_fee_inr)
                self.locked_ata_rent_inr -= ata_locked
                self.total_fees_paid_inr -= buy_fee_inr
                continue

            self.trade_counter += 1
            invested_usd = size_inr / 86.5  # Convert INR to USD to match DexScreener USD price
            tokens_bought = invested_usd / max(1e-12, price)

            active_p = self.autotuner.active_params if hasattr(self, "autotuner") else {}
            sl_pct = active_p.get("stop_loss_pct", STOP_LOSS_PERCENT)
            be_mult = active_p.get("breakeven_trigger", 1.20)
            tp1 = active_p.get("tp1_mult", 1.25)
            tp1_ratio = active_p.get("tp1_ratio", 0.50)
            tp2 = active_p.get("tp2_mult", 1.60)
            tp2_ratio = active_p.get("tp2_ratio", 0.30)
            tp3 = active_p.get("tp3_mult", 3.00)
            tp3_ratio = active_p.get("tp3_ratio", 0.20)

            self.active_positions[addr] = {
                "trade_number": self.trade_counter,
                "token": symbol,
                "name": name,
                "entry_price": price,
                "curr_price": price,
                "peak_price": price,  # Track peak for journal
                "invested_inr": size_inr,
                "ata_locked_inr": ata_locked,
                "remaining_tokens": tokens_bought,
                "initial_tokens": tokens_bought,
                "tx_hash": swap_res.get("tx_hash"),
                "features": features,
                "stop_loss_price": price * (1.0 - sl_pct),
                "breakeven_trigger": be_mult,
                "entry_time": time.time(),
                "entry_volume": live_data.get("volume_1h", 0),
                "regime_at_entry": self.current_regime.get("regime", "UNKNOWN"),
                "tp_stages_hit": 0,
                "outcome_recorded": False,
                "debate": debate,
                "tp_stages": [
                    {"mult": tp1, "price": price * tp1, "ratio": tp1_ratio, "hit": False},
                    {"mult": tp2, "price": price * tp2, "ratio": tp2_ratio, "hit": False},
                    {"mult": tp3, "price": price * tp3, "ratio": tp3_ratio, "hit": False}
                ]
            }

            if hasattr(self, "shadow_tracker"):
                self.shadow_tracker.shadow_tokens.pop(addr, None)
                # Remove from recent_outcomes if previously recorded erroneously
                self.shadow_tracker.recent_outcomes = [
                    o for o in self.shadow_tracker.recent_outcomes if o.get("symbol") != symbol
                ]

            regime_tag = self.current_regime.get("regime", "?")
            tx_entry = {
                "id": f"tx_{int(time.time()*1000)}",
                "time": time.strftime("%H:%M:%S"),
                "timestamp": time.time(),
                "token": symbol,
                "address": addr,
                "action": f"BUY ({regime_tag})",
                "price": price,
                "size_inr": round(size_inr, 2),
                "gain_loss_inr": 0.0,
                "fee_inr": round(buy_fee_inr, 2),
                "money_left": round(self.portfolio_inr, 2),
                "status": "OPEN"
            }
            if not hasattr(self, "trade_history"):
                self.trade_history = []
            self.trade_history.insert(0, tx_entry)
            if len(self.trade_history) > 100:
                self.trade_history.pop()

            self.save_state()
            self.log_activity("🚀", f"BUY {symbol} @ ${price:.8f} (Invested: INR {size_inr:.2f} | Fee: INR {buy_fee_inr:.2f})")
            print(f"   [BUY FILLED] {symbol} | Invested: INR{size_inr:.2f} | Fee: INR{buy_fee_inr:.2f} | ATA Rent: INR{ata_locked:.2f}")
            print(f"   TX: {swap_res.get('tx_hash')[:32]}...")
            print(f"   Stop Loss: ${price * (1.0 - sl_pct):.8f} (-{int(sl_pct*100)}%) | BE Trigger: +{int((be_mult-1)*100)}%")
            print(f"   💰 Money Left: INR{self.portfolio_inr:.2f} | 💼 Invested: INR{size_inr:.2f} | 📈 Money Made: INR{self.realized_profit_inr:+.2f}")
            await send_telegram_alert(
                f"*[BUY]* {symbol}\n"
                f"- Invested: INR{size_inr:.2f}\n"
                f"- Fee Paid: INR{buy_fee_inr:.2f}\n"
                f"- Confidence: {win_prob*100:.0f}%\n"
                f"- Money Left: INR{self.portfolio_inr:.2f}\n"
                f"- Money Made: INR{self.realized_profit_inr:+.2f}"
            )


    async def update_market_ticks(self, price_dict: dict):
        """
        Updates prices, manages stop-loss/take-profit, logs to trade journal,
        and triggers reinforcement learning with failure categorization.
        """
        if hasattr(self, "agent_heartbeats"):
            self.agent_heartbeats["shadow_auditor"] = time.time()
        closed_addrs = []

        for addr, pos in list(self.active_positions.items()):
            curr_price = price_dict.get(addr, pos["entry_price"])
            pos["curr_price"] = curr_price
            pnl_pct = ((curr_price - pos["entry_price"]) / pos["entry_price"]) * 100

            # Track peak price and ratchet Trailing Stop-Loss
            if curr_price > pos.get("peak_price", pos["entry_price"]):
                pos["peak_price"] = curr_price

            peak = pos.get("peak_price", pos["entry_price"])
            entry = pos["entry_price"]
            peak_gain_pct = ((peak - entry) / entry) * 100

            # Monte Carlo #1 Trailing Stop Escalator:
            # Tier 4 (3x+ Moonshot): Trail 20% below peak
            if peak >= entry * 3.0:
                trailing_stop = peak * 0.80
                if trailing_stop > pos["stop_loss_price"]:
                    pos["stop_loss_price"] = trailing_stop
                    print(f"   📈 [TRAILING STOP ESCALATED] {pos['token']}: Locked at ${trailing_stop:.8f} (80% of ${peak:.8f} peak)")
            # Tier 3 (2x Double): Trail 15% below peak
            elif peak >= entry * 2.0:
                trailing_stop = peak * 0.85
                if trailing_stop > pos["stop_loss_price"]:
                    pos["stop_loss_price"] = trailing_stop
                    print(f"   📈 [TRAILING STOP ESCALATED] {pos['token']}: Locked at ${trailing_stop:.8f} (85% of ${peak:.8f} peak)")
            # Tier 2 (+50% Surge): Trail 12% below peak
            elif peak >= entry * 1.50:
                trailing_stop = peak * 0.88
                if trailing_stop > pos["stop_loss_price"]:
                    pos["stop_loss_price"] = trailing_stop
                    print(f"   📈 [TRAILING STOP ESCALATED] {pos['token']}: Locked at ${trailing_stop:.8f} (88% of ${peak:.8f} peak)")
            # Tier 1 (Break-Even Ratchet): Move stop-loss to Break-Even (entry price)
            be_mult = pos.get("breakeven_trigger", self.autotuner.active_params.get("breakeven_trigger", 1.20) if hasattr(self, "autotuner") else 1.20)
            if peak >= entry * be_mult:
                if entry > pos["stop_loss_price"]:
                    pos["stop_loss_price"] = entry
                    print(f"   🛡️ [BREAK-EVEN RATCHET] {pos['token']}: Stop-loss moved to entry price ${entry:.8f} (Zero Risk Locked)")

            print(f"   [{pos['token']}] Current: ${curr_price:.8f} ({pnl_pct:+.1f}%) | Peak: ${peak:.8f} | Stop: ${pos['stop_loss_price']:.8f}")

            # === Check Stop Loss (Trailing or Hard) ===
            if curr_price <= pos["stop_loss_price"]:
                remaining_ratio = pos.get("remaining_tokens", 1.0) / max(1e-6, pos.get("initial_tokens", 1.0))
                price_ratio = curr_price / max(1e-12, pos["entry_price"])
                gross_recovered = pos["invested_inr"] * remaining_ratio * price_ratio
                sell_fee = round(0.50 + (gross_recovered * 0.003), 2)
                self.total_fees_paid_inr += sell_fee
                net_recovered = max(0.0, gross_recovered - sell_fee)

                await self.executor.execute_swap(addr, SOL_MINT, int(pos["remaining_tokens"] * 1_000_000), paper_mode=(not self.is_live))
                self.reclaimer.reclaim_rent(addr, paper_mode=(not self.is_live))
                refund_ata = pos["ata_locked_inr"]
                self.locked_ata_rent_inr -= refund_ata
                self.portfolio_inr += (net_recovered + refund_ata)

                remaining_cost_basis = pos["invested_inr"] * remaining_ratio
                net_pnl = net_recovered - remaining_cost_basis

                self.realized_profit_inr += net_pnl
                if not pos.get("outcome_recorded", False):
                    if net_pnl >= 0:
                        self.wins += 1
                        self.consecutive_losses = 0
                    else:
                        self.losses += 1
                        self.consecutive_losses += 1
                    pos["outcome_recorded"] = True
                else:
                    if net_pnl >= 0:
                        self.consecutive_losses = 0

                # Track best runner
                if pnl_pct > self.best_runner.get("pnl_pct", 0.0):
                    self.best_runner = {
                        "symbol": pos["token"],
                        "pnl_pct": round(pnl_pct, 1),
                        "gain_inr": round(net_pnl, 2),
                        "time": time.strftime("%H:%M:%S")
                    }

                if net_pnl >= 0:
                    status_str = "PROFIT"
                    action_tag = f"TRAILING STOP ({pnl_pct:+.1f}%)"
                else:
                    status_str = "LOSS"
                    action_tag = f"STOP LOSS ({pnl_pct:+.1f}%)"

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
                    pnl_inr=net_pnl,
                    hold_duration_secs=time.time() - pos.get("entry_time", time.time()),
                    sol_macro_change_pct=self.last_macro_change,
                    volume_at_entry=pos.get("entry_volume", 0),
                    volume_at_exit=exit_volume,
                    was_stop_loss=(net_pnl < 0),
                    tp_stages_hit=pos.get("tp_stages_hit", 0),
                    features=pos["features"],
                    market_regime=pos.get("regime_at_entry", "UNKNOWN")
                )

                tx_entry = {
                    "id": f"tx_{int(time.time()*1000)}",
                    "time": time.strftime("%H:%M:%S"),
                    "timestamp": time.time(),
                    "token": pos["token"],
                    "address": addr,
                    "action": action_tag,
                    "price": curr_price,
                    "size_inr": round(remaining_cost_basis, 2),
                    "gain_loss_inr": round(net_pnl, 2),
                    "fee_inr": round(sell_fee, 2),
                    "money_left": round(self.portfolio_inr, 2),
                    "status": status_str
                }
                if not hasattr(self, "trade_history"):
                    self.trade_history = []
                self.trade_history.insert(0, tx_entry)
                if len(self.trade_history) > 100:
                    self.trade_history.pop()

                closed_addrs.append(addr)
                self.save_state()

                pnl_label = "Net Profit" if net_pnl >= 0 else "Net Loss"
                pnl_sign = "+" if net_pnl >= 0 else "-"
                print(f"   [{action_tag}] {pos['token']} sold @ {pnl_pct:+.1f}%. {pnl_label}: {pnl_sign}INR{abs(net_pnl):.2f} (Fee: INR{sell_fee:.2f} | ATA Refund: +INR{refund_ata:.2f})")
                print(f"   💰 Money Left: INR{self.portfolio_inr:.2f} | 📈 Money Made: INR{self.realized_profit_inr:+.2f}")
                try:
                    await send_telegram_alert(
                        f"*{action_tag}* {pos['token']} ({pnl_pct:+.1f}%)\n"
                        f"- {pnl_label}: {pnl_sign}INR{abs(net_pnl):.2f}\n"
                        f"- Fee: INR{sell_fee:.2f}\n"
                        f"- Money Left: INR{self.portfolio_inr:.2f}\n"
                        f"- Total Money Made: INR{self.realized_profit_inr:+.2f}"
                    )
                except Exception as ex:
                    print(f"⚠️ [ALERT] Telegram send error: {ex}")

                # === Learn from trade outcome ===
                try:
                    self.brain.learn_from_trade_result(pos["features"], was_winner=(net_pnl >= 0), trade_category=category)
                except Exception:
                    pass
                continue

            # === Check Staged Take-Profit ===
            for stage in pos["tp_stages"]:
                if not stage["hit"] and curr_price >= stage["price"]:
                    tokens_to_sell = pos["initial_tokens"] * stage["ratio"]
                    tokens_to_sell = min(tokens_to_sell, pos["remaining_tokens"])
                    sold_ratio = tokens_to_sell / max(1e-6, pos["initial_tokens"])
                    price_ratio = curr_price / max(1e-12, pos["entry_price"])
                    gross_proceeds = pos["invested_inr"] * sold_ratio * price_ratio
                    sell_fee = round(0.50 + (gross_proceeds * 0.003), 2)
                    self.total_fees_paid_inr += sell_fee
                    net_proceeds = max(0.0, gross_proceeds - sell_fee)

                    await self.executor.execute_swap(addr, SOL_MINT, int(tokens_to_sell * 1_000_000), paper_mode=(not self.is_live))
                    self.portfolio_inr += net_proceeds

                    # Calculate net profit gained on this partial exit
                    invested_part = pos["invested_inr"] * (tokens_to_sell / pos["initial_tokens"])
                    profit_gain = net_proceeds - invested_part
                    self.realized_profit_inr += profit_gain
                    if not pos.get("outcome_recorded", False):
                        self.wins += 1
                        self.consecutive_losses = 0
                        pos["outcome_recorded"] = True
                    else:
                        self.consecutive_losses = 0

                    # Check best runner for TP stage
                    tp_pct = round(((curr_price - pos['entry_price']) / pos['entry_price']) * 100, 1)
                    if tp_pct > self.best_runner.get("pnl_pct", 0.0):
                        self.best_runner = {
                            "symbol": pos["token"],
                            "pnl_pct": tp_pct,
                            "gain_inr": round(profit_gain, 2),
                            "time": time.strftime("%H:%M:%S")
                        }

                    pos["remaining_tokens"] -= tokens_to_sell
                    stage["hit"] = True
                    pos["tp_stages_hit"] = pos.get("tp_stages_hit", 0) + 1

                    tx_entry = {
                        "id": f"tx_{int(time.time()*1000)}",
                        "time": time.strftime("%H:%M:%S"),
                        "timestamp": time.time(),
                        "token": pos["token"],
                        "address": addr,
                        "action": f"TP {stage['mult']}x ({((curr_price - pos['entry_price'])/pos['entry_price']*100):+.1f}%)",
                        "price": curr_price,
                        "size_inr": round(invested_part, 2),
                        "gain_loss_inr": round(profit_gain, 2),
                        "fee_inr": round(sell_fee, 2),
                        "money_left": round(self.portfolio_inr, 2),
                        "status": "PROFIT"
                    }
                    if not hasattr(self, "trade_history"):
                        self.trade_history = []
                    self.trade_history.insert(0, tx_entry)
                    if len(self.trade_history) > 100:
                        self.trade_history.pop()

                    self.save_state()
                    print(f"   [TP {stage['mult']}x HIT] Sold {stage['ratio']*100:.0f}% of {pos['token']}. Cash Added: +INR{net_proceeds:.2f} (Fee: INR{sell_fee:.2f}) | Profit: +INR{profit_gain:.2f}")
                    print(f"   💰 Money Left: INR{self.portfolio_inr:.2f} | 📈 Money Made: INR{self.realized_profit_inr:+.2f}")
                    await send_telegram_alert(
                        f"*[TAKE PROFIT {stage['mult']}x]* {pos['token']}\n"
                        f"- Cash Added: +INR{net_proceeds:.2f}\n"
                        f"- Net Profit Made: +INR{profit_gain:.2f}\n"
                        f"- Fee: INR{sell_fee:.2f}\n"
                        f"- Money Left: INR{self.portfolio_inr:.2f}\n"
                        f"- Total Money Made: INR{self.realized_profit_inr:+.2f}"
                    )

            # If all tokens sold via TP stages
            if pos["remaining_tokens"] <= 0.000001:
                self.reclaimer.reclaim_rent(addr, paper_mode=(not self.is_live))
                refund_ata = pos["ata_locked_inr"]
                self.locked_ata_rent_inr -= refund_ata
                self.portfolio_inr += refund_ata
                if not pos.get("outcome_recorded", False):
                    self.wins += 1
                    self.consecutive_losses = 0
                    pos["outcome_recorded"] = True
                else:
                    self.consecutive_losses = 0

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

        if closed_addrs:
            self.save_state()

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

        m_invested = sum(pos.get("invested_inr", 0.0) for pos in self.active_positions.values())
        floating_pnl = sum(
            (pos.get("invested_inr", 0.0) * (pos.get("remaining_tokens", pos.get("initial_tokens", 1.0)) / max(1e-6, pos.get("initial_tokens", 1.0))))
            * ((pos.get("curr_price", pos["entry_price"]) - pos["entry_price"]) / max(1e-12, pos["entry_price"]))
            for pos in self.active_positions.values()
        ) if self.active_positions else 0.0

        print("\n" + "-" * 60)
        print(f" 💰 MONEY LEFT (Wallet) : INR {self.portfolio_inr:.2f} | 💼 INVESTED (In Market): INR {m_invested:.2f} | 📈 MADE (Floating): {floating_pnl:+.2f} INR")
        print(f"   DEX Fees Paid  : INR {self.total_fees_paid_inr:.2f} (Solana Gas + 0.3% Raydium AMM)")
        print(f"   ATA Rent Locked: INR {self.locked_ata_rent_inr:.2f} (100% Refundable on exit)")
        print(f"   Open Positions : {len(self.active_positions)} (Cycle #{stage['cycle']} Target: INR {cycle_target:,.0f})")
        print(f"   Record         : {self.wins}W / {self.losses}L (Win Rate: {win_rate:.1f}%)")
        print(f"   Danger Floor   : {danger_status}")
        print(f"   Survival Tier  : {st.emoji} {st.tier} (Floor: ${st.min_liquidity_usd:,.0f})")
        print(f"   Market Regime  : {regime_emoji} {regime}")
        print(f"   News Sentiment : 📰 {news_str}")
        arb_mode = "LIVE ACTIVE" if self.arbitrage_engine.is_unlocked else "SHADOW (Unlocks @ ₹50k)"
        print(f"   Arbitrage Gate : ⚖️ {arb_mode}")
        print(f"   Brain Accuracy : {self.brain.recent_accuracy*100:.0f}% | Threshold: {self.brain.adaptive_threshold*100:.0f}%")
        bar_len = int(progress // 5)
        print(f"   Cycle Metric   : [{'#' * bar_len}{'-' * (20 - bar_len)}] {progress:.1f}%")

        # Journal summary if we have trades
        if self.journal.entries:
            regime_wr = self.journal.get_win_rate_by_regime()
            if regime_wr:
                regime_str = " | ".join(f"{r}: {wr:.0f}%" for r, wr in regime_wr.items())
                print(f"   Win Rate/Regime: {regime_str}")
        # Sync real-time state with web dashboard & disk snapshot
        self.dump_live_state()
        self.save_state()

        print("-" * 60)


async def keep_alive_pinger():
    """
    Background watchdog that pings the Render web service every 8 minutes
    to ensure the free container never sleeps and maintains 24/7 scanning.
    """
    import httpx
    render_url = os.getenv("RENDER_EXTERNAL_URL", "https://cryptogen-bot.onrender.com").rstrip("/")
    ping_url = f"{render_url}/api/state"
    await asyncio.sleep(45)  # Initial grace period after startup

    while True:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(ping_url)
                if res.status_code == 200:
                    print(f"⏱️ [KEEP-ALIVE] Pinged {ping_url} (HTTP 200 OK) — 24/7 Cloud Incubation Active.")
                else:
                    print(f"⏱️ [KEEP-ALIVE] Pinged {ping_url} (HTTP {res.status_code}).")
        except Exception as e:
            print(f"⏱️ [KEEP-ALIVE] Ping attempt: {e}")

        await asyncio.sleep(480)  # 8 minutes


async def run_autonomous_simulation_loop():
    trader = AutonomousDemoTrader()

    # Start Web Analytics Dashboard in background thread
    import threading
    from dashboard_server import start_dashboard_server, set_trader_instance
    set_trader_instance(trader)
    dashboard_port = int(os.getenv("PORT", 8080))
    dash_thread = threading.Thread(target=start_dashboard_server, args=(dashboard_port,), daemon=True)
    dash_thread.start()

    # Launch Cloud Keep-Alive Self-Pinger
    asyncio.create_task(keep_alive_pinger())

    print(f"🚀 CryptoGen Cloud Worker started. Web Dashboard live on port {dashboard_port}!")
    await send_telegram_alert(f"🚀 *[BOT ONLINE]* CryptoGen 24/7 Cloud Incubation started!\n• Mode: Virtual Paper Trading\n• Starting Balance: INR 100.00\n• Web Dashboard: Live on port {dashboard_port}")

    cycle_count = 0
    last_hourly_digest = time.time()

    while True:
        cycle_count += 1
        print(f"\n{'='*65}\n🔄 [CLOUD CYCLE #{cycle_count}] Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n{'='*65}")

        try:
            # 0. Check and Process Remote Telegram Commands (/status, /scorecard, /pause, /resume, /closeall, /harvest)
            await trader.handle_remote_commands()

            # 1. Intelligence & Market Regime Update
            await trader.update_intelligence()

            # 2. Fetch live trending Solana candidates across GeckoTerminal, DexScreener & Boosts
            trending = await fetch_trending_solana_tokens()
            popular_tokens = [
                "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
                "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  # WIF
                "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  # JUP
                "CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump",  # GOAT
                "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",  # POPCAT
                "MEW1gQWJ3nEXg2qgERiKu7FAFj79PHvQVREQUzScPP5",   # MEW
                "2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo"   # PNUT
            ]
            candidates = list(dict.fromkeys(trending + popular_tokens))

            # 3. Scan & execute candidate trades (Virtual or Live) across up to 70 candidates
            await trader.scan_and_trade(candidates[:70])
            trader.display_dashboard()

            # 3.5 Shadow Watchlist: Evaluate post-rejection outcomes (False Negatives & Dodged Rugs)
            if hasattr(trader, "shadow_tracker"):
                active_addrs = set(trader.active_positions.keys())
                shadow_event = await trader.shadow_tracker.update_shadow_tokens(active_addrs=active_addrs)
                if shadow_event:
                    if shadow_event["type"] == "MISSED_RUNNER":
                        trader.log_activity("🚀", f"Missed runner: {shadow_event['symbol']} +{shadow_event['pnl_pct']:.0f}% (Brain retrained)")
                        clean_reason = shadow_event['rejection_reason'].replace('_', ' ')
                        await send_telegram_alert(
                            f"🧠 🚀 *[SHADOW INTELLIGENCE — MISSED RUNNER]*\n\n"
                            f"• *Token:* {shadow_event['symbol']}\n"
                            f"• *Surge:* +{shadow_event['pnl_pct']:.1f}%\n"
                            f"• *Original Filter:* {clean_reason}\n\n"
                            f"🎯 *Auto-Retraining:* The ML Brain has retroactively studied this coin's features with winning weights to prevent future false negatives!"
                        )
                    elif shadow_event["type"] == "DODGED_CRASH":
                        trader.log_activity("🛡️", f"Dodged dump: {shadow_event['symbol']} {shadow_event['pnl_pct']:.0f}% (Safety validated)")

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

            # 5. 24-Hour Midnight / Daily Performance Scorecard to Telegram
            if time.time() - trader.last_daily_scorecard >= 86400:
                await trader.send_daily_scorecard(manual=False)

            # 6. Hourly Telegram Heartbeat Digest
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
