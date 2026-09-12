import asyncio
import os
import sys
import time

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from coindcx_client import CoinDCXClient
from coindcx_strategy import CoinDCXStrategy, calculate_rsi, calculate_ema, calculate_orderbook_imbalance
from coindcx_paper_trader import CoinDCXPaperTrader


async def test_live_data():
    print("--- 1. Testing Live CoinDCX Data Ingestion ---")
    client = CoinDCXClient()
    markets = await client.get_inr_markets()
    print(f"✅ Found {len(markets)} active INR markets on CoinDCX")
    for m in markets[:3]:
        print(f"   {m['market']}: Last=₹{m['last_price']:,.2f}, 24h Vol={m['volume']:,.2f}, Chg={m['change_24h']:+.2f}%")

    candles = await client.get_candles("I-SOL_INR", interval="1h", limit=100)
    print(f"✅ Fetched {len(candles)} 1h candles for SOL/INR")
    assert len(candles) >= 50, "Expected at least 50 candles"

    orderbook = await client.get_orderbook("I-SOL_INR")
    print(f"✅ Fetched SOL/INR Orderbook: {len(orderbook['bids'])} bids, {len(orderbook['asks'])} asks. Best Bid=₹{orderbook['best_bid']:,.2f}")
    assert len(orderbook["bids"]) > 0, "Orderbook bids should not be empty"


async def test_strategy_and_indicators():
    print("\n--- 2. Testing Indicator & Probability Engine ---")
    client = CoinDCXClient()
    candles = await client.get_candles("I-SOL_INR", interval="1h", limit=100)
    orderbook = await client.get_orderbook("I-SOL_INR")

    strategy = CoinDCXStrategy(entry_confidence_threshold=0.75)
    analysis = strategy.analyze_market(candles, orderbook)

    print(f"✅ SOL/INR Analysis Result:")
    print(f"   Price: ₹{analysis['current_price']:,.2f}")
    print(f"   RSI(14): {analysis['rsi']}")
    print(f"   EMA(20): ₹{analysis['ema20']:,.2f} | EMA(50): ₹{analysis['ema50']:,.2f} ({analysis['trend']})")
    print(f"   Order Book Imbalance: {analysis['obi']:+.2f} (Bid/Ask Ratio: {analysis['bid_ask_ratio']:.2f}x)")
    print(f"   Win Probability: {analysis['win_probability']*100:.1f}%")
    print(f"   Signal: {analysis['signal']} (Reasons: {analysis['reasons']})")


async def test_paper_trader_cycle():
    print("\n--- 3. Testing Paper Trader Cycle ---")
    # Use isolated state file for testing
    trader = CoinDCXPaperTrader(initial_capital=100.0, entry_threshold=0.75)
    cycle_res = await trader.run_cycle()
    print(f"✅ Paper Trader Cycle Completed: Cash=₹{cycle_res['cash_inr']:.2f}, HasPosition={cycle_res['has_position']}, Trades={cycle_res['trades']}")


async def backtest_historical_candles(pair: str = "I-SOL_INR"):
    print(f"\n--- 4. Historical Backtest on CoinDCX 500-Candle Stream ({pair}) ---")
    client = CoinDCXClient()
    candles = await client.get_candles(pair=pair, interval="1h", limit=500)
    if len(candles) < 100:
        print("⚠️ Not enough candles for backtest")
        return

    strategy = CoinDCXStrategy(entry_confidence_threshold=0.70)
    capital = 100.0
    position = None
    trades = []
    fees_paid = 0.0

    for i in range(55, len(candles)):
        slice_candles = candles[:i]
        curr = candles[i]
        curr_price = float(curr["close"])
        high_price = float(curr["high"])
        low_price = float(curr["low"])

        if position:
            # Check TP (+25%) on candle high
            if high_price >= position["target_price"]:
                exit_price = position["target_price"]
                gross = position["quantity"] * exit_price
                fee = gross * 0.001
                fees_paid += fee
                net = gross - fee
                profit = net - position["invested"]
                capital += net
                trades.append({"type": "WIN_TP25", "profit": profit, "return_pct": 25.0})
                position = None
            # Check SL (-5%) on candle low
            elif low_price <= position["stop_price"]:
                exit_price = position["stop_price"]
                gross = position["quantity"] * exit_price
                fee = gross * 0.001
                fees_paid += fee
                net = gross - fee
                loss = net - position["invested"]
                capital += net
                trades.append({"type": "LOSS_SL5", "profit": loss, "return_pct": -5.0})
                position = None
        else:
            # Evaluate entry
            analysis = strategy.analyze_market(slice_candles, orderbook=None)
            if analysis["signal"] == "BUY" and capital >= 50.0:
                trade_size = capital
                fee = trade_size * 0.001
                fees_paid += fee
                net_size = trade_size - fee
                qty = net_size / curr_price
                position = {
                    "entry_price": curr_price,
                    "target_price": curr_price * 1.25,
                    "stop_price": curr_price * 0.95,
                    "invested": trade_size,
                    "quantity": qty
                }
                capital = 0.0

    print(f"📊 Backtest Results ({pair} - 500 Hours):")
    print(f"   Initial Capital: ₹100.00")
    print(f"   Final Capital: ₹{capital + (position['quantity']*candles[-1]['close'] if position else 0.0):.2f}")
    print(f"   Total Trades Executed: {len(trades)}")
    wins = [t for t in trades if t["profit"] > 0]
    losses = [t for t in trades if t["profit"] <= 0]
    print(f"   Wins: {len(wins)} | Losses: {len(losses)}")
    if trades:
        win_rate = (len(wins) / len(trades)) * 100.0
        total_pnl = sum(t["profit"] for t in trades)
        print(f"   Win Rate: {win_rate:.1f}%")
        print(f"   Net Realized PnL: ₹{total_pnl:+.2f}")
        print(f"   Total Exchange Fees Paid: ₹{fees_paid:.2f} (0.1% per trade)")


async def main():
    await test_live_data()
    await test_strategy_and_indicators()
    await test_paper_trader_cycle()
    await backtest_historical_candles("I-SOL_INR")
    await backtest_historical_candles("I-BTC_INR")


if __name__ == "__main__":
    asyncio.run(main())
