"""
CryptoGen Trade Journal — Failure-Aware Intelligence Module

Tags every closed trade with a failure/success category so the bot
understands WHY it lost, not just THAT it lost.

Categories:
  - RUG_PULL:       Price dropped >80% within minutes (scam token)
  - LATE_ENTRY:     Entered after peak; price was already declining
  - LOW_VOLUME_DUMP: Volume dried up after entry, no buyers left
  - MARKET_CRASH:   SOL macro dropped >4%, dragging all alts down
  - STOP_LOSS_NORMAL: Standard stop-loss hit in normal conditions
  - EARLY_EXIT:     Sold too early, missed further upside
  - PERFECT_TRADE:  Hit 5x+ take profit
  - GOOD_TRADE:     Hit 2x take profit
  - BREAKEVEN:      Exited near entry price
"""

import os
import json
import time
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

JOURNAL_FILE = os.path.join(os.path.dirname(__file__), "trade_journal.json")


class TradeJournal:
    def __init__(self):
        self.entries = []
        self._load()
        # Running failure pattern stats
        self.failure_counts = {}
        self._recompute_stats()

    def _load(self):
        if os.path.exists(JOURNAL_FILE):
            try:
                with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                    self.entries = json.load(f)
            except Exception:
                self.entries = []

    def _save(self):
        self.entries = self.entries[-200:]
        with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, indent=2, ensure_ascii=False)

    def _recompute_stats(self):
        self.failure_counts = {}
        for e in self.entries:
            cat = e.get("category", "UNKNOWN")
            self.failure_counts[cat] = self.failure_counts.get(cat, 0) + 1

    def categorize_trade(
        self,
        entry_price: float,
        exit_price: float,
        peak_price: float,
        pnl_pct: float,
        hold_duration_secs: float,
        sol_macro_change_pct: float,
        volume_at_entry: float,
        volume_at_exit: float,
        was_stop_loss: bool,
        tp_stages_hit: int
    ) -> str:
        """
        Automatically determines WHY a trade ended the way it did.
        Returns a category string.
        """
        # === LOSS CATEGORIES ===
        if pnl_pct <= -70:
            return "RUG_PULL"

        if sol_macro_change_pct <= -4.0 and pnl_pct < -10:
            return "MARKET_CRASH"

        if volume_at_exit < volume_at_entry * 0.15 and pnl_pct < -10:
            return "LOW_VOLUME_DUMP"

        if peak_price > entry_price * 1.3 and exit_price < entry_price:
            return "LATE_ENTRY"

        if was_stop_loss:
            return "STOP_LOSS_NORMAL"

        # === WIN CATEGORIES ===
        if tp_stages_hit >= 2:
            return "PERFECT_TRADE"

        if tp_stages_hit == 1:
            return "GOOD_TRADE"

        if -5 <= pnl_pct <= 5:
            return "BREAKEVEN"

        if pnl_pct > 5:
            return "GOOD_TRADE"

        return "STOP_LOSS_NORMAL"

    def log_trade(
        self,
        token_symbol: str,
        token_address: str,
        entry_price: float,
        exit_price: float,
        peak_price: float,
        pnl_pct: float,
        pnl_inr: float,
        hold_duration_secs: float,
        sol_macro_change_pct: float,
        volume_at_entry: float,
        volume_at_exit: float,
        was_stop_loss: bool,
        tp_stages_hit: int,
        features: dict,
        market_regime: str = "UNKNOWN"
    ):
        category = self.categorize_trade(
            entry_price, exit_price, peak_price, pnl_pct,
            hold_duration_secs, sol_macro_change_pct,
            volume_at_entry, volume_at_exit,
            was_stop_loss, tp_stages_hit
        )

        entry = {
            "timestamp": time.time(),
            "token": token_symbol,
            "address": token_address,
            "category": category,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "peak_price": peak_price,
            "pnl_pct": round(pnl_pct, 2),
            "pnl_inr": round(pnl_inr, 2),
            "hold_duration_secs": round(hold_duration_secs, 1),
            "sol_macro_change_pct": round(sol_macro_change_pct, 2),
            "volume_at_entry": volume_at_entry,
            "volume_at_exit": volume_at_exit,
            "was_stop_loss": was_stop_loss,
            "tp_stages_hit": tp_stages_hit,
            "market_regime": market_regime,
            "features": features
        }

        self.entries.append(entry)
        self._save()
        self._recompute_stats()

        emoji = {
            "RUG_PULL": "💀", "LATE_ENTRY": "⏰", "LOW_VOLUME_DUMP": "📉",
            "MARKET_CRASH": "🌊", "STOP_LOSS_NORMAL": "🛑", "EARLY_EXIT": "😤",
            "PERFECT_TRADE": "🏆", "GOOD_TRADE": "✅", "BREAKEVEN": "➖"
        }.get(category, "❓")

        print(f"   📓 [JOURNAL] {emoji} {category}: {token_symbol} ({pnl_pct:+.1f}%)")
        return category

    def get_failure_pattern_weights(self) -> dict:
        """
        Returns adjustment weights for the ML brain based on past failure patterns.
        
        If the bot keeps getting rug-pulled → increase safety strictness
        If the bot keeps entering late → require stronger momentum
        If low-volume dumps are common → require higher minimum volume
        """
        total = len(self.entries)
        if total < 5:
            return {}  # Not enough data to draw conclusions

        weights = {}
        rug_rate = self.failure_counts.get("RUG_PULL", 0) / total
        late_rate = self.failure_counts.get("LATE_ENTRY", 0) / total
        low_vol_rate = self.failure_counts.get("LOW_VOLUME_DUMP", 0) / total
        crash_rate = self.failure_counts.get("MARKET_CRASH", 0) / total

        # If >20% of trades are rug pulls, tighten safety
        if rug_rate > 0.20:
            weights["safety_strictness"] = 1.5  # 50% stricter
            print(f"   🧠 [JOURNAL INSIGHT] High rug-pull rate ({rug_rate*100:.0f}%). Tightening safety filters.")

        # If >25% are late entries, require stronger fresh momentum
        if late_rate > 0.25:
            weights["momentum_threshold"] = 1.3  # 30% higher momentum needed
            print(f"   🧠 [JOURNAL INSIGHT] Too many late entries ({late_rate*100:.0f}%). Raising momentum bar.")

        # If >20% are low-volume dumps, require higher volume
        if low_vol_rate > 0.20:
            weights["min_volume_multiplier"] = 1.5  # 50% more volume needed
            print(f"   🧠 [JOURNAL INSIGHT] Low-volume dumps ({low_vol_rate*100:.0f}%). Requiring more volume.")

        # If >30% are market crashes, be more cautious during uncertain macro
        if crash_rate > 0.30:
            weights["macro_sensitivity"] = 2.0  # Double the macro caution
            print(f"   🧠 [JOURNAL INSIGHT] Market crash losses ({crash_rate*100:.0f}%). Increasing macro sensitivity.")

        return weights

    def get_win_rate_by_regime(self) -> dict:
        """Returns win rate breakdown by market regime."""
        regimes = {}
        for e in self.entries:
            regime = e.get("market_regime", "UNKNOWN")
            if regime not in regimes:
                regimes[regime] = {"wins": 0, "losses": 0}
            if e["pnl_pct"] > 0:
                regimes[regime]["wins"] += 1
            else:
                regimes[regime]["losses"] += 1

        result = {}
        for regime, stats in regimes.items():
            total = stats["wins"] + stats["losses"]
            result[regime] = round(stats["wins"] / total * 100, 1) if total > 0 else 0.0
        return result

    def get_summary(self) -> str:
        """Returns a human-readable summary of the trade journal."""
        total = len(self.entries)
        if total == 0:
            return "No trades recorded yet."

        wins = sum(1 for e in self.entries if e["pnl_pct"] > 0)
        losses = total - wins
        avg_win = 0.0
        avg_loss = 0.0
        win_trades = [e for e in self.entries if e["pnl_pct"] > 0]
        loss_trades = [e for e in self.entries if e["pnl_pct"] <= 0]
        if win_trades:
            avg_win = sum(e["pnl_pct"] for e in win_trades) / len(win_trades)
        if loss_trades:
            avg_loss = sum(e["pnl_pct"] for e in loss_trades) / len(loss_trades)

        lines = [
            f"Total Trades: {total} | Wins: {wins} | Losses: {losses}",
            f"Win Rate: {wins/total*100:.1f}%",
            f"Avg Win: {avg_win:+.1f}% | Avg Loss: {avg_loss:+.1f}%",
            "Failure Breakdown:"
        ]
        for cat, count in sorted(self.failure_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {cat}: {count} ({count/total*100:.0f}%)")

        return "\n".join(lines)
