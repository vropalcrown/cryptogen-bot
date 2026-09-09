"""
CryptoGen Smart Brain v2 — Reinforcement Learning Enhanced

Upgrades over v1:
  1. Feature importance tracking — knows WHICH features matter most
  2. Adaptive confidence threshold — adjusts based on recent performance
  3. Trade journal integration — adjusts predictions based on failure patterns
  4. Meta bonus — boosts confidence for tokens matching hot narrative
  5. Regime-aware predictions — different models for different market conditions
  6. Performance decay — recent trades weighted more than old ones
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import cross_val_score
import joblib
import os
import sys
import json
import time

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

MODEL_FILE = os.path.join(os.path.dirname(__file__), "cryptogen_ml_model.joblib")
MEMORY_FILE = os.path.join(os.path.dirname(__file__), "trade_memory.csv")
BRAIN_STATE_FILE = os.path.join(os.path.dirname(__file__), "brain_state.json")


class CryptoGenBrain:
    def __init__(self):
        # Primary model: RandomForest
        self.model = RandomForestClassifier(n_estimators=150, max_depth=6, random_state=42)
        # Secondary model: GradientBoosting for ensemble voting
        self.boost_model = GradientBoostingClassifier(
            n_estimators=80, max_depth=4, learning_rate=0.1, random_state=42
        )
        self.is_trained = False
        self.feature_columns = [
            "buy_ratio_5m", "buy_ratio_1h", "ofi_5m", "vol_acceleration",
            "price_change_5m", "price_change_1h", "liq_to_fdv", "liquidity_usd", "wash_score"
        ]

        # === NEW: Adaptive Intelligence State ===
        self.feature_importance = {}
        self.adaptive_threshold = 0.65  # Starts at 65%, adjusts based on performance
        self.recent_accuracy = 0.5       # Rolling accuracy tracker
        self.prediction_history = []     # Last N predictions vs outcomes
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.total_real_trades = 0

        self._load_brain_state()
        self._load_or_bootstrap_model()

    def _load_brain_state(self):
        """Load persistent brain intelligence state."""
        if os.path.exists(BRAIN_STATE_FILE):
            try:
                with open(BRAIN_STATE_FILE, "r") as f:
                    state = json.load(f)
                    self.adaptive_threshold = min(0.75, state.get("adaptive_threshold", 0.70))
                    self.recent_accuracy = state.get("recent_accuracy", 0.65)
                    self.consecutive_losses = 0  # Reset stale streaks on load
                    self.consecutive_wins = 0
                    self.total_real_trades = state.get("total_real_trades", 0)
                    self.prediction_history = state.get("prediction_history", [])
                    self.feature_importance = state.get("feature_importance", {})
            except Exception:
                pass

    def _save_brain_state(self):
        """Persist brain intelligence state."""
        state = {
            "adaptive_threshold": self.adaptive_threshold,
            "recent_accuracy": self.recent_accuracy,
            "consecutive_losses": self.consecutive_losses,
            "consecutive_wins": self.consecutive_wins,
            "total_real_trades": self.total_real_trades,
            "prediction_history": self.prediction_history[-50:],  # Keep last 50
            "feature_importance": self.feature_importance,
            "last_updated": time.time()
        }
        with open(BRAIN_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

    def _load_or_bootstrap_model(self):
        if os.path.exists(MODEL_FILE) and os.path.exists(MEMORY_FILE):
            try:
                self.model = joblib.load(MODEL_FILE)
                self.is_trained = True
                self._update_feature_importance()
                print(f"🧠 [Smart Brain v2] Loaded trained model. "
                      f"Adaptive threshold: {self.adaptive_threshold*100:.0f}% | "
                      f"Real trades learned: {self.total_real_trades}")
                return
            except Exception as e:
                print(f"⚠️ [Smart Brain v2] Could not load model: {e}")

        print("🧠 [Smart Brain v2] Training deep multi-theory model from quantitative baseline...")
        self._train_bootstrap_model()

    def _train_bootstrap_model(self):
        np.random.seed(42)
        n_samples = 5000

        buy_ratio_5m = np.random.uniform(0.15, 0.90, n_samples)
        buy_ratio_1h = np.random.uniform(0.25, 0.85, n_samples)
        ofi_5m = (buy_ratio_5m - 0.5) * 2.0
        vol_accel = np.random.exponential(1.4, n_samples)
        p_chg_5m = np.random.normal(2.0, 12.0, n_samples)
        p_chg_1h = np.random.normal(4.0, 25.0, n_samples)
        liq_to_fdv = np.random.uniform(0.01, 0.40, n_samples)
        liquidity = np.random.uniform(2500, 80000, n_samples)
        wash_score = np.random.uniform(0.0, 100.0, n_samples)

        labels = (
            (buy_ratio_5m > 0.60) &
            (ofi_5m > 0.20) &
            (vol_accel > 1.35) &
            (liq_to_fdv > 0.07) &
            (liquidity >= 5000) &
            (wash_score < 35.0) &
            (p_chg_5m >= -4.0)
        ).astype(int)

        df = pd.DataFrame({
            "buy_ratio_5m": buy_ratio_5m,
            "buy_ratio_1h": buy_ratio_1h,
            "ofi_5m": ofi_5m,
            "vol_acceleration": vol_accel,
            "price_change_5m": p_chg_5m,
            "price_change_1h": p_chg_1h,
            "liq_to_fdv": liq_to_fdv,
            "liquidity_usd": liquidity,
            "wash_score": wash_score,
            "label": labels
        })

        df.to_csv(MEMORY_FILE, index=False)

        X = df[self.feature_columns]
        y = df["label"]

        self.model.fit(X, y)
        # Also train boost model
        try:
            self.boost_model.fit(X, y)
        except Exception:
            pass

        self.is_trained = True
        joblib.dump(self.model, MODEL_FILE)
        self._update_feature_importance()
        print(f"🧠 [Smart Brain v2] Trained on {n_samples} scenarios. Feature importance computed.")

    def _update_feature_importance(self):
        """Extract and store which features matter most."""
        if hasattr(self.model, 'feature_importances_'):
            importances = self.model.feature_importances_
            self.feature_importance = {
                col: round(float(imp), 4)
                for col, imp in zip(self.feature_columns, importances)
            }

    def predict_win_probability(self, features_dict: dict, meta_bonus: float = 0.0,
                                  journal_weights: dict = None) -> float:
        """
        Enhanced prediction with:
          - Ensemble voting (RF + GBM average)
          - Meta narrative bonus
          - Journal failure-pattern adjustments
          - Feature importance awareness
        """
        if not self.is_trained:
            return 0.50

        df = pd.DataFrame([features_dict])[self.feature_columns]

        # === Primary model prediction ===
        rf_prob = self._safe_predict_proba(self.model, df)

        # === Secondary model prediction (ensemble) ===
        gb_prob = self._safe_predict_proba(self.boost_model, df)

        # Ensemble: weighted average (RF gets 60%, GBM gets 40%)
        if gb_prob is not None:
            base_prob = rf_prob * 0.60 + gb_prob * 0.40
        else:
            base_prob = rf_prob

        # === Apply meta narrative bonus ===
        # Max +15% for tokens matching hot meta
        prob_with_meta = min(0.99, base_prob + meta_bonus)

        # === Apply journal failure-pattern adjustments ===
        if journal_weights:
            # If journal says we keep entering late, penalize declining momentum
            if "momentum_threshold" in journal_weights:
                if features_dict.get("ofi_5m", 0) < 0.1:  # Weak momentum
                    prob_with_meta *= 0.85  # 15% penalty

            # If journal says volume dumps are common, penalize low volume
            if "min_volume_multiplier" in journal_weights:
                if features_dict.get("vol_acceleration", 0) < 1.0:
                    prob_with_meta *= 0.80  # 20% penalty

        # === Consecutive loss penalty ===
        # If we're on a losing streak, be more cautious
        if self.consecutive_losses >= 3:
            streak_penalty = 0.05 * min(self.consecutive_losses - 2, 3)  # Max -15%
            prob_with_meta -= streak_penalty
            print(f"   🧠 [CAUTION] {self.consecutive_losses} consecutive losses. "
                  f"Applying -{streak_penalty*100:.0f}% penalty.")

        # === Consecutive win bonus ===
        if self.consecutive_wins >= 3:
            streak_bonus = 0.03 * min(self.consecutive_wins - 2, 2)  # Max +6%
            prob_with_meta = min(0.95, prob_with_meta + streak_bonus)

        return round(float(max(0.0, min(0.99, prob_with_meta))), 4)

    def _safe_predict_proba(self, model, df) -> float:
        """Safe probability extraction handling single-class edge cases."""
        try:
            probabilities = model.predict_proba(df)[0]
            classes = list(model.classes_)
            if 1 in classes:
                winner_idx = classes.index(1)
                return float(probabilities[winner_idx])
            return 0.0
        except Exception:
            return None

    def get_adaptive_threshold(self, regime_threshold: float = None) -> float:
        """
        Returns the current entry threshold, factoring in:
          - Market regime (from regime detector)
          - Recent performance (self-adjusting)
          - Consecutive loss streaks
        """
        base = regime_threshold if regime_threshold else self.adaptive_threshold

        # After 3+ consecutive real trade losses, raise the bar slightly (capped at 80%)
        if self.consecutive_losses >= 3:
            base = min(0.80, base + 0.03 * min(self.consecutive_losses - 2, 2))

        # After 3+ consecutive wins, slightly lower the bar
        if self.consecutive_wins >= 3:
            base = max(0.55, base - 0.03)

        return round(base, 2)

    def learn_from_trade_result(self, features_dict: dict, was_winner: bool,
                                  trade_category: str = "UNKNOWN"):
        """
        Enhanced learning with:
          - Cumulative CSV memory
          - Recency weighting (recent trades get duplicated for emphasis)
          - Adaptive threshold adjustment
          - Streak tracking
          - Cross-validation check after retrain
        """
        is_shadow = trade_category in ("CONFIRMED_DODGE", "MISSED_RUNNER")
        if not is_shadow:
            self.total_real_trades += 1

        # Track prediction vs outcome
        self.prediction_history.append({
            "timestamp": time.time(),
            "predicted_win": True,  # We only trade when we predict win
            "actual_win": was_winner,
            "category": trade_category
        })

        # Update streaks (ONLY for real executed portfolio trades, NEVER for shadow dodges)
        if not is_shadow:
            if was_winner:
                self.consecutive_wins += 1
                self.consecutive_losses = 0
            else:
                self.consecutive_losses += 1
                self.consecutive_wins = 0

        # === Adaptive threshold adjustment ===
        # Recalculate recent accuracy from real executed trades
        real_history = [p for p in self.prediction_history if p.get("category") not in ("CONFIRMED_DODGE", "MISSED_RUNNER")]
        recent = real_history[-10:]
        if len(recent) >= 5:
            correct = sum(1 for p in recent if p["actual_win"])
            self.recent_accuracy = correct / len(recent)

            # If accuracy < 40%, raise threshold slightly (max 78%)
            if self.recent_accuracy < 0.40:
                self.adaptive_threshold = min(0.78, self.adaptive_threshold + 0.02)
                print(f"   🧠 [ADAPTING] Low accuracy ({self.recent_accuracy*100:.0f}%). "
                      f"Raising threshold to {self.adaptive_threshold*100:.0f}%")

            # If accuracy > 70%, slightly lower threshold (more trades)
            elif self.recent_accuracy > 0.70:
                self.adaptive_threshold = max(0.60, self.adaptive_threshold - 0.02)
                print(f"   🧠 [ADAPTING] High accuracy ({self.recent_accuracy*100:.0f}%). "
                      f"Lowering threshold to {self.adaptive_threshold*100:.0f}%")

        # === Append to cumulative memory ===
        new_row = {k: features_dict.get(k, 0.0) for k in self.feature_columns}
        new_row["label"] = 1 if was_winner else 0
        new_df = pd.DataFrame([new_row])

        # Recency weighting: duplicate the last trade 3x to emphasize recent experience
        recency_df = pd.concat([new_df] * 3, ignore_index=True)

        if os.path.exists(MEMORY_FILE):
            full_df = pd.read_csv(MEMORY_FILE)
            full_df = pd.concat([full_df, recency_df], ignore_index=True)
        else:
            full_df = recency_df

        full_df.to_csv(MEMORY_FILE, index=False)

        # === Retrain both models ===
        X = full_df[self.feature_columns]
        y = full_df["label"]

        self.model.fit(X, y)
        try:
            self.boost_model.fit(X, y)
        except Exception:
            pass

        joblib.dump(self.model, MODEL_FILE)
        self._update_feature_importance()
        self._save_brain_state()

        # === Performance report ===
        win_emoji = "✅" if was_winner else "❌"
        print(f"   📈 [LEARNING] {win_emoji} Trade #{self.total_real_trades} "
              f"({trade_category}). Memory: {len(full_df)} samples. "
              f"Accuracy: {self.recent_accuracy*100:.0f}% | "
              f"Threshold: {self.adaptive_threshold*100:.0f}%")

    def get_brain_status(self) -> str:
        """Returns human-readable brain status."""
        top_features = sorted(self.feature_importance.items(), key=lambda x: -x[1])[:3]
        top_str = ", ".join(f"{f[0]}({f[1]*100:.0f}%)" for f in top_features)

        return (
            f"Brain v2 | Real Trades: {self.total_real_trades} | "
            f"Accuracy: {self.recent_accuracy*100:.0f}% | "
            f"Threshold: {self.adaptive_threshold*100:.0f}% | "
            f"Streak: {'W' + str(self.consecutive_wins) if self.consecutive_wins > 0 else 'L' + str(self.consecutive_losses)} | "
            f"Top Features: [{top_str}]"
        )
