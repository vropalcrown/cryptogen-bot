"""
CryptoGen Shadow Tracker — False-Negative & Lookback Intelligence Module

Monitors rejected token candidates over a 2-hour post-rejection window to detect:
  1. Missed Runners (False Negatives): Rejected coins that surged >+50% safely
     -> Retrains ML Brain with was_winner=True to overcome hesitation.
  2. Dodged Crashes (True Negatives): Rejected coins that collapsed >-35% or rugged
     -> Validates risk engine and reinforces was_winner=False.
"""

import os
import sys
import json
import time
import asyncio
from typing import Dict, Any, Optional

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from data_collector import fetch_dex_token_data

SHADOW_STATE_FILE = os.path.join(os.path.dirname(__file__), "shadow_state.json")


class ShadowTracker:
    def __init__(self, brain=None, notifier=None):
        self.brain = brain
        self.notifier = notifier
        self.shadow_tokens: Dict[str, Dict[str, Any]] = {}
        self.total_tracked = 0
        self.dodged_crashes = 0
        self.missed_runners = 0
        self.auto_retrained = 0
        self.recent_outcomes = []
        self._load_state()

    def _load_state(self):
        """Loads persistent shadow monitoring state."""
        if os.path.exists(SHADOW_STATE_FILE):
            try:
                with open(SHADOW_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.shadow_tokens = data.get("shadow_tokens", {})
                    self.total_tracked = data.get("total_tracked", 0)
                    self.dodged_crashes = data.get("dodged_crashes", 0)
                    self.missed_runners = data.get("missed_runners", 0)
                    self.auto_retrained = data.get("auto_retrained", 0)
                    self.recent_outcomes = data.get("recent_outcomes", [])
            except Exception as e:
                print(f"⚠️ [SHADOW STATE LOAD] Starting fresh: {e}")

    def save_state(self):
        """Persists shadow monitoring state to disk."""
        try:
            # Keep only last 40 active or recently resolved tokens
            if len(self.shadow_tokens) > 40:
                sorted_tokens = sorted(
                    self.shadow_tokens.items(),
                    key=lambda x: x[1].get("rejection_time", 0)
                )
                self.shadow_tokens = dict(sorted_tokens[-40:])

            data = {
                "shadow_tokens": self.shadow_tokens,
                "total_tracked": self.total_tracked,
                "dodged_crashes": self.dodged_crashes,
                "missed_runners": self.missed_runners,
                "auto_retrained": self.auto_retrained,
                "recent_outcomes": self.recent_outcomes[-20:],
                "last_updated": time.time()
            }
            tmp = SHADOW_STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, SHADOW_STATE_FILE)
        except Exception as e:
            print(f"⚠️ [SHADOW STATE SAVE ERROR] {e}")

    def register_rejected_token(
        self,
        address: str,
        symbol: str,
        name: str,
        price: float,
        reason: str,
        features: dict,
        win_prob: float
    ):
        """
        Adds a candidate rejected by ML or safety filters to the shadow watchlist.
        """
        if not address or price <= 0:
            return

        # Don't overwrite if actively monitoring
        if address in self.shadow_tokens:
            existing = self.shadow_tokens[address]
            if existing.get("status") == "MONITORING":
                return

        self.total_tracked += 1
        self.shadow_tokens[address] = {
            "address": address,
            "symbol": symbol,
            "name": name,
            "rejection_price": price,
            "rejection_time": time.time(),
            "rejection_reason": reason,
            "features": features,
            "initial_confidence": round(win_prob, 4),
            "peak_price": price,
            "lowest_price": price,
            "last_checked_price": price,
            "last_checked_time": time.time(),
            "status": "MONITORING",
            "pnl_pct": 0.0
        }
        self.save_state()

    async def update_shadow_tokens(self) -> Optional[dict]:
        """
        Periodically inspects a batch of shadow tokens to track performance.
        Returns notification details if a significant event (runner or crash) was resolved.
        """
        now = time.time()
        active_items = [
            (addr, t) for addr, t in self.shadow_tokens.items()
            if t.get("status") == "MONITORING"
        ]

        if not active_items:
            return None

        # Sort by oldest last_checked_time, evaluate up to 3 per cycle to respect API limits
        active_items.sort(key=lambda x: x[1].get("last_checked_time", 0))
        batch = active_items[:3]

        resolved_event = None

        for addr, item in batch:
            try:
                live_data = await fetch_dex_token_data(addr)
                item["last_checked_time"] = now

                entry_p = item["rejection_price"]
                if not live_data or live_data.get("price_usd", 0) <= 0:
                    curr_p = 0.0
                    liq = 0.0
                else:
                    curr_p = live_data["price_usd"]
                    liq = live_data.get("liquidity_usd", 0.0)

                item["last_checked_price"] = curr_p
                item["peak_price"] = max(item["peak_price"], curr_p)
                item["lowest_price"] = min(item["lowest_price"], curr_p) if curr_p > 0 else 0.0

                if entry_p > 0:
                    pnl_pct = ((curr_p - entry_p) / entry_p) * 100.0
                else:
                    pnl_pct = 0.0
                item["pnl_pct"] = round(pnl_pct, 2)

                age_secs = now - item["rejection_time"]

                # Case 1: Missed Runner (Gained > +50% with healthy liquidity > $5k)
                if pnl_pct >= 50.0 and liq >= 5000:
                    item["status"] = "MISSED_RUNNER"
                    self.missed_runners += 1
                    self.auto_retrained += 1
                    
                    outcome_entry = {
                        "time": time.strftime("%H:%M:%S"),
                        "symbol": item["symbol"],
                        "type": "MISSED_RUNNER",
                        "pnl_pct": item["pnl_pct"],
                        "reason": f"Surged +{item['pnl_pct']:.1f}% after {item['rejection_reason']}"
                    }
                    self.recent_outcomes.insert(0, outcome_entry)

                    # Trigger ML Retrain with winning label
                    if self.brain and hasattr(self.brain, "learn_from_trade_result"):
                        print(f"\n   🧠 [SHADOW BRAIN RETRAIN] Missed runner {item['symbol']} (+{item['pnl_pct']:.1f}%). Learning winning pattern!")
                        self.brain.learn_from_trade_result(
                            item["features"],
                            was_winner=True,
                            trade_category="MISSED_RUNNER"
                        )

                    resolved_event = {
                        "type": "MISSED_RUNNER",
                        "symbol": item["symbol"],
                        "pnl_pct": item["pnl_pct"],
                        "rejection_reason": item["rejection_reason"]
                    }

                # Case 2: Confirmed Dodged Crash / Rug (Dropped > -35% or liquidity pulled to < $1k)
                elif pnl_pct <= -35.0 or (liq < 1000 and entry_p > 0):
                    item["status"] = "DODGED_CRASH"
                    self.dodged_crashes += 1
                    
                    outcome_entry = {
                        "time": time.strftime("%H:%M:%S"),
                        "symbol": item["symbol"],
                        "type": "DODGED_CRASH",
                        "pnl_pct": item["pnl_pct"],
                        "reason": f"Dumped {item['pnl_pct']:.1f}% (Safety Validated!)"
                    }
                    self.recent_outcomes.insert(0, outcome_entry)

                    # Trigger ML Retrain with losing label to reinforce avoidance
                    if self.brain and hasattr(self.brain, "learn_from_trade_result"):
                        self.brain.learn_from_trade_result(
                            item["features"],
                            was_winner=False,
                            trade_category="CONFIRMED_DODGE"
                        )

                # Case 3: Expired after 2 hours (7200s) without dramatic breakout
                elif age_secs >= 7200:
                    item["status"] = "EXPIRED"

                await asyncio.sleep(0.5)

            except Exception as e:
                item["last_checked_time"] = now

        self.save_state()
        return resolved_event

    def get_summary_stats(self) -> dict:
        """Returns clean telemetry metrics for Web UI & Telegram."""
        active_cnt = sum(1 for t in self.shadow_tokens.values() if t.get("status") == "MONITORING")
        return {
            "active_monitoring": active_cnt,
            "total_tracked": self.total_tracked,
            "dodged_crashes": self.dodged_crashes,
            "missed_runners": self.missed_runners,
            "auto_retrained": self.auto_retrained,
            "recent_outcomes": self.recent_outcomes[:6]
        }
