"""
CryptoGen Real-Time News Sentinel

Ingests breaking crypto headlines via public RSS feeds (CoinTelegraph, Decrypt)
with zero API keys or costs.

Features:
  1. Panic Detection: Spot breaking market shocks (hacks, SEC lawsuits, outages, bans)
     and trigger an Emergency Buying Halt to prevent trading into dumps.
  2. Sentiment Scoring: Compute rolling macro news sentiment (-1.0 to +1.0).
  3. Narrative Extraction: Extract trending keywords from breaking news to feed
     into MetaTracker for narrative-boosted meme coin selection.
"""

import httpx
import xml.etree.ElementTree as ET
import time
import re
from typing import Dict, List, Tuple

# Critical emergency triggers that specifically halt trades
CRITICAL_PANIC_KEYWORDS = [
    "solana down", "solana outage", "solana halt", "network downtime",
    "sec emergency", "sec sues binance", "sec sues coinbase",
    "market crash", "crypto bloodbath", "flash crash", "usdt depeg",
    "binance halts", "freeze withdrawals", "liquidation cascade"
]

# General bearish keywords that influence sentiment score
GENERAL_BEARISH_KEYWORDS = [
    "hack", "hacked", "exploit", "exploited", "fraud", "lawsuit",
    "indictment", "arrested", "plunge", "ban", "prohibit", "subpoena",
    "investigation", "downturn", "bearish"
]

# Bullish keywords that boost sentiment
BULLISH_KEYWORDS = [
    "all-time high", "ath", "surge", "surges", "rally", "rallies",
    "breakout", "bull run", "etf approved", "approval", "adoption",
    "institutional buy", "record high", "soars", "moon"
]

# Narrative keywords to look out for
NARRATIVE_PATTERNS = {
    "AI": [r"\bai\b", r"\bartificial intelligence\b", r"\bchatgpt\b", r"\bopenai\b", r"\bdeepseek\b", r"\bagent\b"],
    "POLITICAL": [r"\btrump\b", r"\belection\b", r"\bwhite house\b", r"\bcongress\b", r"\bbiden\b"],
    "ANIMAL": [r"\bdogecoin\b", r"\bshiba\b", r"\bbonk\b", r"\bpepe\b", r"\bmemecoin\b", r"\bmeme coin\b"],
    "SOLANA": [r"\bsolana\b", r"\bsol\b", r"\bjupiter\b", r"\braydium\b"],
    "MACRO": [r"\bfed\b", r"\brate cut\b", r"\binflation\b", r"\binterest rate\b"]
}

FEEDS = [
    {"name": "CoinTelegraph", "url": "https://cointelegraph.com/rss"},
    {"name": "Decrypt", "url": "https://decrypt.co/feed"}
]

class NewsSentinel:
    def __init__(self):
        self.cached_headlines: List[Dict] = []
        self.last_fetch_time = 0.0
        self.cache_ttl_seconds = 180.0  # Fetch fresh headlines every 3 minutes
        self.current_sentiment = 0.0
        self.is_panic_active = False
        self.active_panic_reason = ""
        self.detected_news_narratives = []

    async def fetch_latest_headlines(self) -> List[Dict]:
        """Fetches and parses headlines from top crypto feeds."""
        if time.time() - self.last_fetch_time < self.cache_ttl_seconds and self.cached_headlines:
            return self.cached_headlines

        headlines = []
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
            for feed in FEEDS:
                try:
                    res = await client.get(feed["url"])
                    if res.status_code == 200:
                        root = ET.fromstring(res.content)
                        for item in root.findall(".//item")[:8]:
                            title_elem = item.find("title")
                            link_elem = item.find("link")
                            pub_elem = item.find("pubDate")

                            title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                            link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""

                            if title:
                                headlines.append({
                                    "source": feed["name"],
                                    "title": title,
                                    "link": link,
                                    "time": pub_elem.text if pub_elem is not None else ""
                                })
                except Exception:
                    continue

        if headlines:
            self.cached_headlines = headlines
            self.last_fetch_time = time.time()

        return self.cached_headlines

    async def analyze_market_news(self) -> Dict:
        """
        Analyzes the latest headlines for:
          - Emergency Panic / Circuit Breakers
          - Overall Market Sentiment (-1.0 to +1.0)
          - Hot News Narratives
        """
        headlines = await self.fetch_latest_headlines()
        if not headlines:
            return {
                "sentiment_score": 0.0,
                "sentiment_label": "NEUTRAL",
                "panic_halt": False,
                "panic_reason": "",
                "news_narratives": [],
                "headline_count": 0
            }

        panic_hits = []
        bullish_count = 0
        bearish_count = 0
        narrative_counts = {k: 0 for k in NARRATIVE_PATTERNS.keys()}

        for h in headlines:
            title_lower = h["title"].lower()

            # 1. Critical Emergency Panic (hard circuit breaker)
            for kw in CRITICAL_PANIC_KEYWORDS:
                if kw in title_lower:
                    panic_hits.append(f"{kw.upper()}: '{h['title']}'")
                    bearish_count += 3
                    break

            # 2. General Bearish Sentiment
            for kw in GENERAL_BEARISH_KEYWORDS:
                if kw in title_lower:
                    bearish_count += 1
                    break

            # 3. Bullish Sentiment
            for kw in BULLISH_KEYWORDS:
                if kw in title_lower:
                    bullish_count += 1
                    break

            # Check narratives
            for narrative, patterns in NARRATIVE_PATTERNS.items():
                for pat in patterns:
                    if re.search(pat, title_lower):
                        narrative_counts[narrative] += 1
                        break

        # Calculate sentiment score (-1.0 to +1.0)
        total_signals = bullish_count + bearish_count
        if total_signals > 0:
            raw_sentiment = (bullish_count - bearish_count) / total_signals
        else:
            raw_sentiment = 0.0

        self.current_sentiment = round(raw_sentiment, 2)
        self.is_panic_active = len(panic_hits) >= 2  # 2 or more panic headlines trigger hard halt
        self.active_panic_reason = " | ".join(panic_hits[:2]) if panic_hits else ""

        # Top detected narratives in news
        sorted_narratives = [k for k, v in sorted(narrative_counts.items(), key=lambda x: -x[1]) if v > 0]
        self.detected_news_narratives = sorted_narratives

        label = "BULLISH" if self.current_sentiment > 0.15 else ("BEARISH" if self.current_sentiment < -0.15 else "NEUTRAL")

        return {
            "sentiment_score": self.current_sentiment,
            "sentiment_label": label,
            "panic_halt": self.is_panic_active,
            "panic_reason": self.active_panic_reason,
            "news_narratives": sorted_narratives,
            "headline_count": len(headlines),
            "top_headline": headlines[0]["title"] if headlines else ""
        }
