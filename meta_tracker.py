"""
CryptoGen Meta Tracker — Narrative & Category Intelligence

Detects which token categories/narratives are currently hot on Solana:
  - AI tokens, animal/meme tokens, political tokens, gaming tokens, etc.
  
The bot biases toward tokens matching the current hot meta, since
meme coins run in waves — riding the current narrative is critical.

Works by:
  1. Crawling DexScreener trending tokens
  2. Classifying each by name/symbol pattern matching
  3. Tracking which categories have the most volume & gainers
  4. Providing a "meta score" bonus for tokens matching hot categories
"""

import httpx
import re
import time
import os
import json
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

META_HISTORY_FILE = os.path.join(os.path.dirname(__file__), "meta_history.json")

# Category detection patterns (name/symbol keyword matching)
CATEGORY_PATTERNS = {
    "AI": [
        r"\bai\b", r"\bgpt\b", r"\bneural\b", r"\bbot\b", r"\bagent\b",
        r"\bmachine\b", r"\brobot\b", r"\bllm\b", r"\bsentient\b", r"\bcognit"
    ],
    "ANIMAL": [
        r"\bdog\b", r"\bcat\b", r"\bfrog\b", r"\bpepe\b", r"\bshib\b",
        r"\bdoge\b", r"\bwif\b", r"\bbonk\b", r"\bape\b", r"\bmonkey\b",
        r"\bbear\b", r"\bbull\b", r"\bbird\b", r"\bfish\b", r"\bpeng"
    ],
    "POLITICAL": [
        r"\btrump\b", r"\bbiden\b", r"\bmaga\b", r"\bvote\b", r"\belect",
        r"\bfreedom\b", r"\bpatriot\b", r"\bamerica\b", r"\busa\b"
    ],
    "CULTURE": [
        r"\bmoon\b", r"\brocket\b", r"\bdiamond\b", r"\bgm\b", r"\bwagmi\b",
        r"\bhodl\b", r"\brug\b", r"\bpump\b", r"\bfomo\b", r"\byolo\b",
        r"\bfloki\b", r"\belon\b", r"\bmusk\b"
    ],
    "GAMING": [
        r"\bgame\b", r"\bplay\b", r"\bquest\b", r"\bknight\b", r"\bsword\b",
        r"\blevel\b", r"\bxp\b", r"\bguild\b", r"\bnft\b"
    ],
    "DEFI": [
        r"\bswap\b", r"\byield\b", r"\bstake\b", r"\bpool\b", r"\bfarm\b",
        r"\bvault\b", r"\blend\b", r"\bdex\b", r"\bliquid"
    ],
    "FOOD": [
        r"\bpizza\b", r"\bsushi\b", r"\bcake\b", r"\bburger\b", r"\btaco\b",
        r"\bcheese\b", r"\bbread\b", r"\bnoodle"
    ]
}


class MetaTracker:
    def __init__(self):
        self.current_meta = {}       # {category: score}
        self.hot_categories = []     # Sorted list of hot categories
        self.meta_history = []
        self._load_history()

    def _load_history(self):
        if os.path.exists(META_HISTORY_FILE):
            try:
                with open(META_HISTORY_FILE, "r") as f:
                    self.meta_history = json.load(f)
                    # Restore last known meta if recent enough
                    if self.meta_history:
                        last = self.meta_history[-1]
                        if time.time() - last.get("timestamp", 0) < 3600:  # < 1 hour old
                            self.current_meta = last.get("scores", {})
                            self._update_hot_list()
            except Exception:
                self.meta_history = []

    def _save_history(self):
        self.meta_history = self.meta_history[-100:]
        with open(META_HISTORY_FILE, "w") as f:
            json.dump(self.meta_history, f)

    def classify_token(self, name: str, symbol: str) -> list:
        """Classify a token into categories based on name/symbol."""
        text = f"{name} {symbol}".lower()
        categories = []

        for category, patterns in CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text):
                    categories.append(category)
                    break

        return categories if categories else ["OTHER"]

    async def scan_trending_meta(self) -> dict:
        """
        Scans DexScreener trending tokens and determines which
        categories/narratives are currently hot.
        """
        category_scores = {}

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                # Get trending token profiles
                res = await client.get("https://api.dexscreener.com/token-profiles/latest/v1")
                if res.status_code == 200:
                    tokens = res.json()
                    sol_tokens = [t for t in tokens if t.get("chainId") == "solana"]

                    for token_info in sol_tokens[:30]:
                        # Get detailed pair data
                        addr = token_info.get("tokenAddress", "")
                        if not addr:
                            continue

                        # Try to get token details from search
                        try:
                            detail_res = await client.get(
                                f"https://api.dexscreener.com/latest/dex/tokens/{addr}",
                                timeout=6.0
                            )
                            if detail_res.status_code != 200:
                                continue

                            pairs = detail_res.json().get("pairs", [])
                            if not pairs:
                                continue

                            pair = pairs[0]
                            name = pair.get("baseToken", {}).get("name", "")
                            symbol = pair.get("baseToken", {}).get("symbol", "")
                            volume_1h = float(pair.get("volume", {}).get("h1", 0) or 0)
                            price_change_1h = float(pair.get("priceChange", {}).get("h1", 0) or 0)

                            # Classify
                            cats = self.classify_token(name, symbol)

                            for cat in cats:
                                if cat not in category_scores:
                                    category_scores[cat] = {
                                        "count": 0, "total_volume": 0.0,
                                        "gainers": 0, "avg_change": 0.0,
                                        "tokens": []
                                    }
                                category_scores[cat]["count"] += 1
                                category_scores[cat]["total_volume"] += volume_1h
                                if price_change_1h > 5.0:
                                    category_scores[cat]["gainers"] += 1
                                category_scores[cat]["avg_change"] += price_change_1h
                                category_scores[cat]["tokens"].append(symbol)

                        except Exception:
                            continue

                        # Small delay to avoid rate limiting
                        import asyncio
                        await asyncio.sleep(0.3)

        except Exception as e:
            print(f"   [META] Scan error: {e}")

        # Calculate composite meta score for each category
        for cat, data in category_scores.items():
            if data["count"] > 0:
                data["avg_change"] = data["avg_change"] / data["count"]

            # Composite score: weighted by count, volume, and gainers
            score = (
                data["count"] * 10 +
                min(data["total_volume"] / 1000, 100) +
                data["gainers"] * 20 +
                max(0, data["avg_change"]) * 2
            )
            category_scores[cat]["meta_score"] = round(score, 1)

        self.current_meta = category_scores
        self._update_hot_list()

        # Save to history
        self.meta_history.append({
            "timestamp": time.time(),
            "scores": {k: v.get("meta_score", 0) for k, v in category_scores.items()},
            "hot": self.hot_categories[:3]
        })
        self._save_history()

        return category_scores

    def _update_hot_list(self):
        """Sort categories by meta score to find the hottest."""
        if isinstance(self.current_meta, dict):
            # Handle both formats: {cat: score_number} and {cat: {meta_score: x}}
            scores = {}
            for cat, val in self.current_meta.items():
                if isinstance(val, dict):
                    scores[cat] = val.get("meta_score", 0)
                else:
                    scores[cat] = val
            self.hot_categories = sorted(scores, key=lambda c: scores[c], reverse=True)

    def get_meta_bonus(self, token_name: str, token_symbol: str) -> float:
        """
        Returns a bonus multiplier (0.0 to 0.15) for the ML confidence
        if the token matches the current hot meta.
        
        Hot meta #1 → +0.15 bonus
        Hot meta #2 → +0.10 bonus
        Hot meta #3 → +0.05 bonus
        No match    → +0.00
        """
        if not self.hot_categories:
            return 0.0

        cats = self.classify_token(token_name, token_symbol)

        for cat in cats:
            if cat in self.hot_categories[:1]:
                return 0.15
            if cat in self.hot_categories[1:2]:
                return 0.10
            if cat in self.hot_categories[2:3]:
                return 0.05

        return 0.0

    def get_hot_summary(self) -> str:
        """Returns human-readable meta summary."""
        if not self.hot_categories:
            return "No meta data yet. Run a scan first."

        lines = ["Current Hot Meta (Solana):"]
        for i, cat in enumerate(self.hot_categories[:5]):
            meta = self.current_meta.get(cat, {})
            if isinstance(meta, dict):
                score = meta.get("meta_score", 0)
                count = meta.get("count", 0)
                tokens = meta.get("tokens", [])[:3]
            else:
                score = meta
                count = 0
                tokens = []

            rank_emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i]
            token_str = ", ".join(tokens) if tokens else "N/A"
            lines.append(f"  {rank_emoji} {cat}: Score {score:.0f} ({count} tokens) [{token_str}]")

        return "\n".join(lines)
