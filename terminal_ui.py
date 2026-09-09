"""
CryptoGen Terminal UI (TUI) — Cyber-Quant Command Center
Live terminal monitor for CryptoGen v2 autonomous trading engine.

Usage:
  python terminal_ui.py
  python terminal_ui.py --local   (reads local live_state.json)
"""

import sys
import os
import time
import json
import httpx
import argparse

# Enable ANSI colors on Windows
if sys.platform == "win32":
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ANSI Color Codes
C_RESET   = "\033[0m"
C_BOLD    = "\033[1m"
C_DIM     = "\033[2m"
C_CYAN    = "\033[36m"
C_GREEN   = "\033[32m"
C_YELLOW  = "\033[33m"
C_RED     = "\033[31m"
C_PURPLE  = "\033[35m"
C_BLUE    = "\033[34m"
C_WHITE   = "\033[97m"
C_BG_DARK = "\033[40m"
CLEAR_SCREEN = "\033[2J\033[H"

RENDER_API_URL = "https://cryptogen-bot.onrender.com/api/state"
LOCAL_STATE_FILE = os.path.join(os.path.dirname(__file__), "live_state.json")

def draw_progress_bar(current, target, width=28):
    if target <= 0:
        return "[" + " " * width + "] 0.0%"
    pct = min(1.0, max(0.0, current / target))
    filled = int(round(width * pct))
    bar = f"{C_CYAN}{'█' * filled}{C_DIM}{'░' * (width - filled)}{C_RESET}"
    return f"[{bar}] {C_BOLD}{pct*100:.1f}%{C_RESET}"

def fetch_state(use_local=False):
    if use_local and os.path.exists(LOCAL_STATE_FILE):
        try:
            with open(LOCAL_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    try:
        with httpx.Client(timeout=4.0) as client:
            res = client.get(RENDER_API_URL)
            if res.status_code == 200:
                return res.json()
    except Exception:
        # Fallback to local if remote times out
        if os.path.exists(LOCAL_STATE_FILE):
            try:
                with open(LOCAL_STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return None

def render_tui(state):
    if not state:
        print(f"\n{C_YELLOW}⏳ Connecting to CryptoGen Cloud Engine...{C_RESET}")
        return

    net_worth = state.get("net_worth", 100.0)
    liquid_cash = state.get("liquid_cash", net_worth)
    cycle = state.get("cycle", 1)
    target_inr = state.get("target_inr", 1000.0)
    danger_floor = state.get("danger_floor_inr", 50.0)
    survival_tier = state.get("survival_tier", "🟢 NORMAL")
    regime = state.get("regime", "🟠 CRAB")
    sentiment = state.get("news_sentiment", "NEUTRAL")
    wins = state.get("wins", 0)
    losses = state.get("losses", 0)
    positions = state.get("positions", [])
    activity = state.get("activity_feed", [])
    shadow = state.get("shadow_stats", {})
    sol_inr = state.get("sol_to_inr", 9000.0)
    is_paused = state.get("is_paused", False)
    mode_str = f"{C_YELLOW}[PAUSED]{C_RESET}" if is_paused else f"{C_GREEN}[LIVE ACTIVE]{C_RESET}"

    now_str = time.strftime("%Y-%m-%d %H:%M:%S")

    out = []
    out.append(CLEAR_SCREEN)
    out.append(f"{C_BOLD}{C_CYAN}╔{'═' * 76}╗{C_RESET}")
    out.append(f"{C_BOLD}{C_CYAN}║{C_WHITE}  ⚡ CRYPTOGEN v2 — AUTONOMOUS QUANT TERMINAL COMMAND CENTER             {C_CYAN}║{C_RESET}")
    out.append(f"{C_BOLD}{C_CYAN}║{C_DIM}  Solana Micro-Capital Quant Engine  •  Cloud Incubation  •  {now_str} {C_CYAN}║{C_RESET}")
    out.append(f"{C_BOLD}{C_CYAN}╠{'═' * 76}╣{C_RESET}")

    # Top Metrics Line
    bar = draw_progress_bar(net_worth, target_inr, width=20)
    out.append(f"{C_CYAN}║{C_RESET} {C_BOLD}Portfolio Net Worth:{C_RESET} {C_GREEN}₹{net_worth:,.2f}{C_RESET}  {C_DIM}|{C_RESET}  {C_BOLD}Liquid Cash:{C_RESET} ₹{liquid_cash:,.2f}  {C_DIM}|{C_RESET}  {C_BOLD}Status:{C_RESET} {mode_str}   {C_CYAN}║{C_RESET}")
    out.append(f"{C_CYAN}║{C_RESET} {C_BOLD}Cycle #{cycle} Progress:{C_RESET}    {bar}  Target: {C_BOLD}₹{target_inr:,.0f}{C_RESET} (Floor: ₹{danger_floor:,.0f}) {C_CYAN}║{C_RESET}")
    out.append(f"{C_CYAN}╠{'═' * 76}╣{C_RESET}")

    # Radar & Market Condition Line
    out.append(f"{C_CYAN}║{C_RESET} {C_BOLD}Market Regime:{C_RESET} {regime:<14} {C_DIM}|{C_RESET} {C_BOLD}Survival Tier:{C_RESET} {survival_tier:<12} {C_DIM}|{C_RESET} {C_BOLD}SOL/INR:{C_RESET} ₹{sol_inr:,.0f} {C_CYAN}║{C_RESET}")
    out.append(f"{C_CYAN}║{C_RESET} {C_BOLD}News Sentiment:{C_RESET} {sentiment:<13} {C_DIM}|{C_RESET} {C_BOLD}Win/Loss:{C_RESET} {C_GREEN}{wins}W{C_RESET} / {C_RED}{losses}L{C_RESET}        {C_DIM}|{C_RESET} {C_BOLD}Positions:{C_RESET} {len(positions)} active   {C_CYAN}║{C_RESET}")
    out.append(f"{C_CYAN}╠{'═' * 76}╣{C_RESET}")

    # Shadow Lookback Intelligence Box
    active_sh = shadow.get("active_monitoring", 0)
    dodged = shadow.get("dodged_crashes", 0)
    missed = shadow.get("missed_runners", 0)
    retrained = shadow.get("auto_retrained", 0)
    out.append(f"{C_CYAN}║{C_RESET} {C_BOLD}{C_PURPLE}🎯 SHADOW LOOKBACK INTELLIGENCE (FALSE-NEGATIVE RADAR):{C_RESET}                      {C_CYAN}║{C_RESET}")
    out.append(f"{C_CYAN}║{C_RESET}   • Dodged Scams: {C_GREEN}{C_BOLD}{dodged}{C_RESET}   • Missed Runners: {C_YELLOW}{C_BOLD}{missed}{C_RESET}   • Active Tracking: {active_sh}   • Retrains: {retrained}  {C_CYAN}║{C_RESET}")

    recent_sh = shadow.get("recent_outcomes", [])
    if recent_sh:
        top_sh = recent_sh[0]
        sh_icon = "🛡️" if top_sh.get("type") == "DODGED_CRASH" else "🚀"
        sh_text = f"Latest: {sh_icon} {top_sh.get('symbol')} ({top_sh.get('pnl_pct'):+.1f}%) -> {top_sh.get('reason')}"[:70]
        out.append(f"{C_CYAN}║{C_RESET}   {C_DIM}{sh_text:<72}{C_RESET} {C_CYAN}║{C_RESET}")
    out.append(f"{C_CYAN}╠{'═' * 76}╣{C_RESET}")

    # Active Positions Section
    out.append(f"{C_CYAN}║{C_RESET} {C_BOLD}💼 ACTIVE POSITIONS ({len(positions)}):{C_RESET}{' ' * 51}{C_CYAN}║{C_RESET}")
    if not positions:
        out.append(f"{C_CYAN}║{C_RESET}   {C_DIM}Scanning live Solana DEX pairs... (Cash 100% liquid & safe){C_RESET}          {C_CYAN}║{C_RESET}")
    else:
        out.append(f"{C_CYAN}║{C_RESET}   {C_BOLD}{'TOKEN':<12} {'INVESTED':<12} {'ENTRY':<16} {'STOP-LOSS':<16} {'PNL':<10}{C_RESET}{C_CYAN}║{C_RESET}")
        for p in positions[:4]:
            pnl = p.get("pnl_pct", 0.0)
            pnl_col = C_GREEN if pnl >= 0 else C_RED
            pnl_sign = "+" if pnl >= 0 else ""
            line = f"   {p.get('token','?'):<12} ₹{p.get('invested_inr',0):<11.2f} ${p.get('entry_price',0):<15.8f} ${p.get('stop_loss',0):<15.8f} {pnl_col}{pnl_sign}{pnl:.1f}%{C_RESET}"
            out.append(f"{C_CYAN}║{C_RESET}{line:<74}{C_CYAN}║{C_RESET}")

    out.append(f"{C_CYAN}╠{'═' * 76}╣{C_RESET}")

    # Live Activity Feed Section
    out.append(f"{C_CYAN}║{C_RESET} {C_BOLD}⚡ LIVE QUANT ACTIVITY FEED (Real-Time Telemetry):{C_RESET}                        {C_CYAN}║{C_RESET}")
    if not activity:
        out.append(f"{C_CYAN}║{C_RESET}   {C_DIM}Listening for live engine ticks...{C_RESET}{' ' * 38}{C_CYAN}║{C_RESET}")
    else:
        for item in activity[:6]:
            icon = item.get("icon", "⚡")
            msg = item.get("message", "")[:56]
            t = item.get("time", "")
            feed_line = f"   {icon} [{t}] {msg}"
            out.append(f"{C_CYAN}║{C_RESET} {feed_line:<73} {C_CYAN}║{C_RESET}")

    out.append(f"{C_BOLD}{C_CYAN}╚{'═' * 76}╝{C_RESET}")
    out.append(f"{C_DIM}Press Ctrl+C to exit  •  Auto-refreshing every 2.5s  •  CryptoGen Quant Engine{C_RESET}")

    print("\n".join(out))

def main():
    parser = argparse.ArgumentParser(description="CryptoGen Terminal Command Center")
    parser.add_argument("--local", action="store_true", help="Read from local live_state.json instead of Render API")
    args = parser.parse_args()

    print(f"{C_BOLD}{C_CYAN}🚀 Launching CryptoGen Terminal Command Center...{C_RESET}")
    time.sleep(0.5)

    try:
        while True:
            state = fetch_state(use_local=args.local)
            render_tui(state)
            time.sleep(2.5)
    except KeyboardInterrupt:
        print(f"\n\n{C_GREEN}👋 Exited CryptoGen Terminal Command Center. Bot continues 24/7 in cloud!{C_RESET}\n")

if __name__ == "__main__":
    main()
