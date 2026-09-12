"""
CoinDCX Quantitative Paper Trader

Executes disciplined paper trading on authentic CoinDCX market data:
  - Starting Capital: ₹100.00
  - Position Sizing: ₹100.00 minimum spot size
  - Fees: 0.10% maker/taker (10 paise per ₹100)
  - Exit Target: 100% Cash-out at +25.0%
  - Stop-Loss: Hard cut at -5.0%
  - Re-Scan Loop: Bank all profits -> Re-scan top INR markets immediately
"""

import os
import sys
import json
import time
import asyncio
from typing import Dict, List, Optional, Any

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from coindcx_client import CoinDCXClient
from coindcx_strategy import CoinDCXStrategy

STATE_FILE = os.path.join(os.path.dirname(__file__), "coindcx_state.json")
JOURNAL_FILE = os.path.join(os.path.dirname(__file__), "coindcx_journal.csv")

TARGETED_PAIRS = [
    ("I-SOL_INR", "SOL"),
    ("I-BTC_INR", "BTC"),
    ("I-ETH_INR", "ETH")
]


class CoinDCXPaperTrader:
    def __init__(self, initial_capital: float = 100.0, entry_threshold: float = 0.75):
        self.client = CoinDCXClient()
        self.strategy = CoinDCXStrategy(entry_confidence_threshold=entry_threshold)
        self.initial_capital = initial_capital

        # State variables
        self.portfolio_inr = initial_capital
        self.active_position: Optional[Dict[str, Any]] = None
        self.trade_history: List[Dict[str, Any]] = []
        self.total_realized_pnl = 0.0
        self.total_fees_paid = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.last_scan_time = 0.0
        self.last_scan_results: List[Dict[str, Any]] = []

        self._load_state()

    def _load_state(self):
        """Load persistent paper state from disk."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.portfolio_inr = data.get("portfolio_inr", self.initial_capital)
                    self.active_position = data.get("active_position", None)
                    self.trade_history = data.get("trade_history", [])
                    self.total_realized_pnl = data.get("total_realized_pnl", 0.0)
                    self.total_fees_paid = data.get("total_fees_paid", 0.0)
                    self.total_trades = data.get("total_trades", 0)
                    self.winning_trades = data.get("winning_trades", 0)
                    self.losing_trades = data.get("losing_trades", 0)
                    self.last_scan_results = data.get("last_scan_results", [])
                    print(f"📄 [CoinDCX Paper] Loaded state: Cash=₹{self.portfolio_inr:.2f}, Active={bool(self.active_position)}")
            except Exception as e:
                print(f"⚠️ [CoinDCX Paper Load Error] {e}")

    def save_state(self):
        """Persist paper state to disk atomically."""
        data = {
            "portfolio_inr": round(self.portfolio_inr, 2),
            "active_position": self.active_position,
            "trade_history": self.trade_history[:50],
            "total_realized_pnl": round(self.total_realized_pnl, 2),
            "total_fees_paid": round(self.total_fees_paid, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate_pct": round((self.winning_trades / max(1, self.total_trades)) * 100.0, 1),
            "last_scan_time": self.last_scan_time,
            "last_scan_results": self.last_scan_results,
            "last_updated": time.time()
        }
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, STATE_FILE)

    def _log_journal(self, trade_dict: Dict[str, Any]):
        """Append closed trade to CSV journal for learning and calibration."""
        file_exists = os.path.exists(JOURNAL_FILE)
        cols = [
            "timestamp", "time_str", "pair", "symbol", "action", "entry_price",
            "exit_price", "size_inr", "pnl_inr", "pnl_pct", "fee_inr", "duration_min",
            "win_probability", "rsi", "obi", "outcome"
        ]
        row = [
            str(trade_dict.get("timestamp", time.time())),
            trade_dict.get("time_str", time.strftime("%Y-%m-%d %H:%M:%S")),
            trade_dict.get("pair", ""),
            trade_dict.get("symbol", ""),
            trade_dict.get("action", ""),
            str(trade_dict.get("entry_price", 0.0)),
            str(trade_dict.get("exit_price", 0.0)),
            str(trade_dict.get("size_inr", 0.0)),
            str(trade_dict.get("pnl_inr", 0.0)),
            str(trade_dict.get("pnl_pct", 0.0)),
            str(trade_dict.get("fee_inr", 0.0)),
            str(trade_dict.get("duration_min", 0.0)),
            str(trade_dict.get("win_probability", 0.0)),
            str(trade_dict.get("rsi", 0.0)),
            str(trade_dict.get("obi", 0.0)),
            trade_dict.get("outcome", "")
        ]
        with open(JOURNAL_FILE, "a", encoding="utf-8") as f:
            if not file_exists:
                f.write(",".join(cols) + "\n")
            f.write(",".join(row) + "\n")

    async def run_cycle(self) -> Dict[str, Any]:
        """Runs one complete scan & position management cycle."""
        self.last_scan_time = time.time()

        # 1. If we have an active position, monitor for +25% Target or -5% Stop-Loss
        if self.active_position:
            await self._manage_active_position()
            # If position was just closed, immediately proceed to re-scan
            if not self.active_position:
                print("🔄 [CoinDCX Paper] Position closed. Triggering immediate re-scan for next setup...")
                await self._scan_and_enter()
        else:
            # 2. No active position: Scan markets and evaluate entry
            await self._scan_and_enter()

        self.save_state()
        return {
            "cash_inr": self.portfolio_inr,
            "has_position": bool(self.active_position),
            "realized_pnl": self.total_realized_pnl,
            "trades": self.total_trades
        }

    async def _manage_active_position(self):
        """Monitors the active open position against live CoinDCX price."""
        pos = self.active_position
        pair = pos["pair"]
        symbol = pos["symbol"]
        entry_price = pos["entry_price"]
        invested_inr = pos["invested_inr"]
        quantity = pos["quantity"]
        target_price = pos["target_price"]
        stop_price = pos["stop_loss_price"]

        # Fetch live candles / orderbook to get exact current price
        orderbook = await self.client.get_orderbook(pair)
        curr_price = orderbook.get("best_bid") or orderbook.get("best_ask")

        if not curr_price or curr_price <= 0:
            # Fallback to latest candle close
            candles = await self.client.get_candles(pair, interval="15m", limit=2)
            if candles:
                curr_price = float(candles[-1]["close"])

        if not curr_price or curr_price <= 0:
            print(f"⚠️ [CoinDCX Paper] Could not fetch live price for {pair}")
            return

        pos["curr_price"] = curr_price
        current_pnl_pct = ((curr_price - entry_price) / entry_price) * 100.0
        pos["current_pnl_pct"] = round(current_pnl_pct, 2)

        print(f"📊 [CoinDCX Paper Position] {symbol} @ ₹{curr_price:,.2f} | Entry: ₹{entry_price:,.2f} | PnL: {current_pnl_pct:+.2f}% (TP: ₹{target_price:,.2f} | SL: ₹{stop_price:,.2f})")

        # CASE 1: TAKE PROFIT HIT (+25%) -> WITHDRAW 100% OF FUNDS
        if curr_price >= target_price:
            gross_proceeds = quantity * curr_price
            exit_fee = round(gross_proceeds * 0.001, 2)  # 0.1% CoinDCX fee
            net_proceeds = round(gross_proceeds - exit_fee, 2)
            net_pnl = round(net_proceeds - invested_inr, 2)
            duration_min = round((time.time() - pos["entry_time"]) / 60.0, 1)

            self.portfolio_inr += net_proceeds
            self.total_realized_pnl += net_pnl
            self.total_fees_paid += (pos["entry_fee"] + exit_fee)
            self.total_trades += 1
            self.winning_trades += 1

            print(f"\n🎯🎯🎯 [COINDCX TAKE-PROFIT HIT] {symbol} reached target (+25%)!")
            print(f"   Exit Price: ₹{curr_price:,.2f} (Target was ₹{target_price:,.2f})")
            print(f"   Invested: ₹{invested_inr:.2f} -> Net Proceeds: ₹{net_proceeds:.2f} (Net Profit: +₹{net_pnl:.2f})")
            print(f"   Fee Paid: ₹{exit_fee:.2f} | Duration: {duration_min} mins")
            print(f"   💰 New Total Liquid Cash: ₹{self.portfolio_inr:.2f}\n")

            trade_record = {
                "timestamp": time.time(),
                "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                "pair": pair,
                "symbol": symbol,
                "action": "TAKE_PROFIT_25",
                "entry_price": entry_price,
                "exit_price": curr_price,
                "size_inr": invested_inr,
                "pnl_inr": net_pnl,
                "pnl_pct": round(current_pnl_pct, 2),
                "fee_inr": round(pos["entry_fee"] + exit_fee, 2),
                "duration_min": duration_min,
                "win_probability": pos.get("win_prob", 0.0),
                "rsi": pos.get("rsi", 0.0),
                "obi": pos.get("obi", 0.0),
                "outcome": "WIN"
            }
            self.trade_history.insert(0, trade_record)
            self._log_journal(trade_record)
            self.active_position = None

        # CASE 2: STOP-LOSS HIT (-5%) -> CUT LOSS TO PRESERVE REMAINING CAPITAL
        elif curr_price <= stop_price:
            gross_proceeds = quantity * curr_price
            exit_fee = round(gross_proceeds * 0.001, 2)
            net_proceeds = round(gross_proceeds - exit_fee, 2)
            net_pnl = round(net_proceeds - invested_inr, 2)
            duration_min = round((time.time() - pos["entry_time"]) / 60.0, 1)

            self.portfolio_inr += net_proceeds
            self.total_realized_pnl += net_pnl
            self.total_fees_paid += (pos["entry_fee"] + exit_fee)
            self.total_trades += 1
            self.losing_trades += 1

            print(f"\n🛡️ [COINDCX STOP-LOSS CUT] {symbol} dropped to -5% stop-loss.")
            print(f"   Exit Price: ₹{curr_price:,.2f} (Stop was ₹{stop_price:,.2f})")
            print(f"   Net Proceeds: ₹{net_proceeds:.2f} (Loss: -₹{abs(net_pnl):.2f})")
            print(f"   💰 Remaining Cash: ₹{self.portfolio_inr:.2f}\n")

            trade_record = {
                "timestamp": time.time(),
                "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                "pair": pair,
                "symbol": symbol,
                "action": "STOP_LOSS_5",
                "entry_price": entry_price,
                "exit_price": curr_price,
                "size_inr": invested_inr,
                "pnl_inr": net_pnl,
                "pnl_pct": round(current_pnl_pct, 2),
                "fee_inr": round(pos["entry_fee"] + exit_fee, 2),
                "duration_min": duration_min,
                "win_probability": pos.get("win_prob", 0.0),
                "rsi": pos.get("rsi", 0.0),
                "obi": pos.get("obi", 0.0),
                "outcome": "LOSS"
            }
            self.trade_history.insert(0, trade_record)
            self._log_journal(trade_record)
            self.active_position = None

    async def _scan_and_enter(self):
        """Scans candidate markets, computes win probability, and enters if bar is met."""
        if self.portfolio_inr < 50.0:
            print(f"⚠️ [CoinDCX Paper] Balance ₹{self.portfolio_inr:.2f} is insufficient for new orders.")
            return

        print(f"\n🔍 [CoinDCX Market Scan] Scanning INR liquid markets (Available Cash: ₹{self.portfolio_inr:.2f})...")
        evaluations = []

        for pair, sym in TARGETED_PAIRS:
            try:
                candles = await self.client.get_candles(pair=pair, interval="1h", limit=100)
                if not candles or len(candles) < 55:
                    continue

                orderbook = await self.client.get_orderbook(pair=pair)
                analysis = self.strategy.analyze_market(candles, orderbook)
                analysis["pair"] = pair
                analysis["symbol"] = sym
                evaluations.append(analysis)

                reasons_str = ", ".join(analysis["reasons"]) if analysis["reasons"] else "Neutral"
                print(f"   {sym}/INR: ₹{analysis['current_price']:,.2f} | RSI={analysis['rsi']} | OBI={analysis['obi']:+.2f} | WinProb={analysis['win_probability']*100:.1f}% -> {analysis['signal']} ({reasons_str})")
            except Exception as e:
                print(f"⚠️ [Scan Error {pair}] {e}")

        self.last_scan_results = evaluations

        # Select highest-probability qualified candidate
        qualified = [e for e in evaluations if e["signal"] == "BUY" and e["win_probability"] >= self.strategy.entry_threshold]
        if not qualified:
            print("⏳ [CoinDCX Decision] No candidate meets ≥75% confidence threshold. Staying 100% safe in cash.\n")
            return

        qualified.sort(key=lambda x: x["win_probability"], reverse=True)
        best = qualified[0]

        # Sizing: Trade full available capital or ₹100 minimum
        trade_size_inr = round(min(self.portfolio_inr, max(100.0, self.portfolio_inr)), 2)
        entry_price = best["current_price"]
        entry_fee = round(trade_size_inr * 0.001, 2)  # 0.1% CoinDCX fee
        net_invested = trade_size_inr - entry_fee
        quantity = net_invested / entry_price

        # Target: +25% | Stop-loss: -5%
        target_price = round(entry_price * 1.25, 2)
        stop_price = round(entry_price * 0.95, 2)

        self.portfolio_inr -= trade_size_inr
        self.active_position = {
            "pair": best["pair"],
            "symbol": best["symbol"],
            "entry_price": entry_price,
            "curr_price": entry_price,
            "invested_inr": trade_size_inr,
            "net_invested": net_invested,
            "quantity": quantity,
            "entry_fee": entry_fee,
            "entry_time": time.time(),
            "target_price": target_price,
            "stop_loss_price": stop_price,
            "current_pnl_pct": 0.0,
            "win_prob": best["win_probability"],
            "rsi": best["rsi"],
            "obi": best["obi"],
            "reasons": best["reasons"]
        }

        print(f"\n🚀🚀🚀 [COINDCX PAPER BUY EXECUTED] Entered {best['symbol']}/INR!")
        print(f"   Size: ₹{trade_size_inr:.2f} (Exchange Fee: ₹{entry_fee:.2f})")
        print(f"   Entry Price: ₹{entry_price:,.2f} | Quantity: {quantity:.6f} {best['symbol']}")
        print(f"   🎯 Target (+25%): ₹{target_price:,.2f}")
        print(f"   🛡️ Stop-Loss (-5%): ₹{stop_price:,.2f}")
        print(f"   Win Probability Score: {best['win_probability']*100:.1f}%\n")
