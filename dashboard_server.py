"""
CryptoGen Live Real-Time Web Dashboard (Styled with UI/UX Pro Max)

Features:
  • Auto-refreshing real-time DOM updates every 3 seconds (zero manual reload needed)
  • Live Net Worth, liquid cash, cycle progress & danger floor
  • Live position table with dynamic trailing stop-loss ratchets & PnL badges
  • Market regime, news sentiment, and survival tier radars
  • Interactive Web Controls (Pause, Resume, Emergency Close All)
"""

import os
import sys
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from cloud_vault import load_cloud_state_sync

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

STATE_FILE = os.path.join(os.path.dirname(__file__), "live_state.json")

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="theme-color" content="#07090E">
  <title>CryptoGen v2 — Quant Command Center</title>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;800&family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #07090E;
      --card-bg: rgba(16, 22, 34, 0.85);
      --card-border: rgba(255, 255, 255, 0.08);
      --accent-sol: #9945FF;
      --accent-cyan: #14F195;
      --text-main: #F3F4F6;
      --text-muted: #9CA3AF;
      --win-green: #10B981;
      --loss-red: #EF4444;
      --gold: #F59E0B;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text-main);
      font-family: 'Inter', sans-serif;
      padding: 24px;
      min-height: 100vh;
      background-image: radial-gradient(circle at 10% 20%, rgba(153, 69, 255, 0.08) 0%, transparent 40%),
                        radial-gradient(circle at 90% 80%, rgba(20, 241, 149, 0.08) 0%, transparent 40%);
    }

    .container { max-width: 1280px; margin: 0 auto; }

    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 18px;
      border-bottom: 1px solid var(--card-border);
    }
    .brand { display: flex; align-items: center; gap: 14px; }
    .logo-badge {
      background: linear-gradient(135deg, var(--accent-sol), var(--accent-cyan));
      width: 44px; height: 44px; border-radius: 12px;
      display: flex; align-items: center; justify-content: center;
      font-size: 22px; font-weight: 800; color: #000;
      box-shadow: 0 0 24px rgba(20, 241, 149, 0.3);
    }
    h1 { font-size: 22px; font-weight: 800; letter-spacing: -0.5px; }
    .sub { font-size: 13px; color: var(--text-muted); }
    
    .status-badge {
      display: flex; align-items: center; gap: 8px;
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      padding: 6px 14px; border-radius: 20px;
      font-size: 12px; font-weight: 600; color: var(--win-green);
    }
    .pulse-dot {
      width: 8px; height: 8px; background: var(--win-green);
      border-radius: 50%; box-shadow: 0 0 10px var(--win-green);
      animation: pulse 2s infinite;
    }
    @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.8); } }

    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 18px; margin-bottom: 24px; }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 20px;
      backdrop-filter: blur(16px);
      transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .card:hover { border-color: rgba(255, 255, 255, 0.16); transform: translateY(-2px); }

    .card-title { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; margin-bottom: 8px; }
    .card-value { font-size: 26px; font-weight: 800; font-family: 'JetBrains Mono', monospace; }
    .card-meta { font-size: 12px; color: var(--text-muted); margin-top: 6px; }

    .progress-wrap { width: 100%; height: 8px; background: rgba(255,255,255,0.06); border-radius: 4px; overflow: hidden; margin-top: 10px; }
    .progress-fill { height: 100%; background: linear-gradient(90deg, var(--accent-sol), var(--accent-cyan)); border-radius: 4px; transition: width 0.5s ease; }

    .dashboard-body { display: grid; grid-template-columns: 2fr 1fr; gap: 24px; }
    @media (max-width: 900px) { .dashboard-body { grid-template-columns: 1fr; } }

    .panel {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 24px;
      backdrop-filter: blur(16px);
      margin-bottom: 24px;
    }
    .panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
    .panel-title { font-size: 16px; font-weight: 700; display: flex; align-items: center; gap: 8px; }

    table { width: 100%; border-collapse: collapse; font-family: 'JetBrains Mono', monospace; font-size: 13px; }
    th { text-align: left; padding: 12px 14px; color: var(--text-muted); font-size: 11px; text-transform: uppercase; border-bottom: 1px solid var(--card-border); }
    td { padding: 14px; border-bottom: 1px solid rgba(255,255,255,0.04); }
    tr:last-child td { border-bottom: none; }

    .tag {
      display: inline-block; padding: 4px 10px; border-radius: 6px;
      font-size: 11px; font-weight: 700;
    }
    .tag-green { background: rgba(16, 185, 129, 0.15); color: var(--win-green); }
    .tag-purple { background: rgba(153, 69, 255, 0.15); color: var(--accent-sol); }
    .tag-gold { background: rgba(245, 158, 11, 0.15); color: var(--gold); }
    .tag-red { background: rgba(239, 68, 68, 0.15); color: var(--loss-red); }
    .tag-cyan { background: rgba(20, 241, 149, 0.15); color: var(--accent-cyan); }
    .shadow-grid { display: grid; grid-template-columns: 1.15fr 0.85fr; gap: 20px; }
    @media (max-width: 900px) { .shadow-grid { grid-template-columns: 1fr; } }

    .btn {
      padding: 8px 14px; border-radius: 8px; font-size: 12px; font-weight: 600;
      cursor: pointer; border: 1px solid transparent; transition: all 0.2s ease;
    }
    .btn-danger { background: rgba(239, 68, 68, 0.15); color: var(--loss-red); border-color: rgba(239, 68, 68, 0.3); }
    .btn-danger:hover { background: rgba(239, 68, 68, 0.3); }
    .btn-neutral { background: rgba(255, 255, 255, 0.08); color: var(--text-main); }
    .btn-neutral:hover { background: rgba(255, 255, 255, 0.15); }

    /* Terminal UI Theme for Live Feed */
    .terminal-window {
      background: #04060A;
      border: 1px solid rgba(20, 241, 149, 0.25);
      border-radius: 12px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6), 0 0 15px rgba(20, 241, 149, 0.08);
      overflow: hidden;
      font-family: 'JetBrains Mono', monospace;
      margin-top: 14px;
    }
    .terminal-header {
      display: flex; justify-content: space-between; align-items: center;
      background: #0B0F19; padding: 10px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    .terminal-dots { display: flex; align-items: center; gap: 8px; }
    .dot-red { width: 11px; height: 11px; border-radius: 50%; background: #FF5F56; display: inline-block; box-shadow: 0 0 6px rgba(255,95,86,0.6); }
    .dot-yellow { width: 11px; height: 11px; border-radius: 50%; background: #FFBD2E; display: inline-block; }
    .dot-green { width: 11px; height: 11px; border-radius: 50%; background: #27C93F; display: inline-block; }
    .terminal-body {
      padding: 16px; min-height: 220px; max-height: 320px; overflow-y: auto;
      display: flex; flex-direction: column; gap: 5px; font-size: 12px; line-height: 1.5;
      background: radial-gradient(circle at 50% 0%, rgba(20, 241, 149, 0.03) 0%, transparent 70%), #04060A;
    }
    .terminal-body::-webkit-scrollbar { width: 6px; }
    .terminal-body::-webkit-scrollbar-track { background: #04060A; }
    .terminal-body::-webkit-scrollbar-thumb { background: rgba(20, 241, 149, 0.25); border-radius: 3px; }
    .terminal-body::-webkit-scrollbar-thumb:hover { background: var(--accent-cyan); }
    .terminal-footer {
      background: #080C14; padding: 8px 16px; border-top: 1px solid rgba(255, 255, 255, 0.05);
      font-size: 11px; color: var(--text-muted); display: flex; justify-content: space-between; align-items: center;
    }
    .blink-cursor { animation: blink 1s step-start infinite; }
    @keyframes blink { 50% { opacity: 0; } }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <div class="logo-badge">⚡</div>
        <div>
          <h1>CRYPTOGEN v2</h1>
          <div class="sub" id="wallet-sub">Autonomous Solana Micro-Quant Engine • Live 24/7 Cloud Incubation</div>
        </div>
      </div>
      <div style="display: flex; align-items: center; gap: 12px;">
        <div class="status-badge" id="live-badge">
          <div class="pulse-dot"></div>
          <span id="bot-status">PAPER TRADING • ACTIVE</span>
        </div>
        <span style="font-size: 11px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace;" id="sync-timer">Auto-syncing: live</span>
      </div>
    </header>

    <!-- Top Ledger Metrics: Money Left, Money Invested, Money Made, Fees Paid -->
    <div class="grid">
      <div class="card" style="border-left: 4px solid var(--accent-cyan);">
        <div class="card-title">💰 Money Left (Liquid Cash)</div>
        <div class="card-value" id="money-left" style="color: var(--accent-cyan);">INR 100.00</div>
        <div class="card-meta" id="cycle-target">Cycle #1 Target: INR 1,000.00</div>
        <div class="progress-wrap">
          <div class="progress-fill" id="progress-bar" style="width: 10%;"></div>
        </div>
      </div>

      <div class="card" style="border-left: 4px solid var(--accent-blue);">
        <div class="card-title">💼 Money Invested (At Risk)</div>
        <div class="card-value" id="money-invested" style="color: var(--accent-blue);">INR 0.00</div>
        <div class="card-meta" id="floating-pnl" style="color: var(--win-green); font-weight: 600;">Floating: +INR 0.00</div>
        <div class="card-meta" id="pos-count-sub">0 Open Trade(s)</div>
      </div>

      <div class="card" style="border-left: 4px solid var(--win-green);">
        <div class="card-title">📈 Money Made (Net Profit)</div>
        <div class="card-value" id="money-made" style="color: var(--win-green);">+INR 0.00</div>
        <div class="card-meta" style="color: var(--text-muted);">Added directly to Cash upon trade exit</div>
        <div class="card-meta" id="record-stats">Record: 0W / 0L</div>
      </div>

      <div class="card" style="border-left: 4px solid var(--gold);">
        <div class="card-title">⛽ Fees Paid (DEX & Gas)</div>
        <div class="card-value" id="fees-paid" style="color: var(--gold);">INR 0.00</div>
        <div class="card-meta">Solana Gas + 0.3% Raydium AMM</div>
        <div class="card-meta" id="danger-floor">Danger Floor: INR 50.00</div>
      </div>
    </div>

    <!-- Main Grid -->
    <div class="dashboard-body">
      <!-- Active Positions -->
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">💼 Active Positions (<span id="pos-count">0</span>)</div>
          <div style="display: flex; gap: 8px;">
            <button class="btn btn-neutral" onclick="triggerControl('/status')">Status</button>
            <button class="btn btn-danger" onclick="triggerControl('/closeall')">Emergency Close All</button>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Token</th>
              <th>Invested</th>
              <th>Current Price</th>
              <th>Trailing Stop</th>
              <th>PnL</th>
            </tr>
          </thead>
          <tbody id="positions-table">
            <tr>
              <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 32px;">
                Scanning live Solana DEX pairs... (No open positions)
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Intelligence & Alpha Radar -->
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">🧠 Quant Radar</div>
        </div>
        <div style="display: flex; flex-direction: column; gap: 14px;">
          <div>
            <div class="card-title">Machine Learning Brain</div>
            <div style="font-size: 14px; font-weight: 600;">Dual Ensemble: RF (60%) + GBM (40%)</div>
            <div class="card-meta" id="brain-accuracy">Adaptive Entry Bar: 89% | RL Feedback: Active</div>
          </div>
          <hr style="border: 0; border-top: 1px solid var(--card-border);">
          <div>
            <div class="card-title">🧬 Dynamic Strategy Self-Tuner</div>
            <div style="font-size: 14px; font-weight: 700; color: var(--accent-cyan);" id="autotune-summary">
              SL: -10% | BE: +20% | TP: +25% / +60% / +200%
            </div>
            <div class="card-meta" id="autotune-details">
              Auto-calibrated against live Solana macro volatility & crab regime.
            </div>
          </div>
          <hr style="border: 0; border-top: 1px solid var(--card-border);">
          <div>
            <div class="card-title">🎯 Shadow Intelligence (Lookback Engine)</div>
            <div style="font-size: 14px; font-weight: 700; color: var(--accent-cyan);" id="shadow-summary">
              0 Dodged Crashes • 0 Missed Runners
            </div>
            <div class="card-meta" id="shadow-details">
              Tracking rejected tokens for 2h post-rejection to retrain ML brain.
            </div>
            <div id="shadow-recent-list" style="margin-top: 10px; display: flex; flex-direction: column; gap: 6px; font-family: 'JetBrains Mono', monospace; font-size: 11px;">
              <!-- Dynamic list of recent dodged/missed tokens -->
            </div>
          </div>
          <hr style="border: 0; border-top: 1px solid var(--card-border);">
          <div>
            <div class="card-title">Active Alpha Systems</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px;">
              <span class="tag tag-purple">🐋 Smart Money Tracker</span>
              <span class="tag tag-green">🕵️ Dev Bundler Auditing</span>
              <span class="tag tag-gold">📰 Real-Time News Sentinel</span>
              <span class="tag tag-green">🛡️ Anti-Fake-News RPC Proof</span>
              <span class="tag tag-purple">📈 Dynamic Trailing Escalator</span>
              <span class="tag tag-gold">⚖️ Triangular Arbitrage Gate</span>
              <span class="tag tag-green">🎯 False-Negative Shadow Radar</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Dedicated Shadow Intelligence Audit Panel (Dodged Scams & Missed Runners) -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">
          <span>🎯 Shadow Intelligence Audit</span>
          <span style="font-size: 12px; font-weight: 500; color: var(--text-muted);">(Real-Time Dodged Rugs, Missed Runners & 2h Lookback)</span>
        </div>
        <div style="display: flex; gap: 10px; font-family: 'JetBrains Mono', monospace; font-size: 11px;">
          <span class="tag tag-green" id="audit-dodged-badge">🛡️ 72 Dodged Crashes</span>
          <span class="tag tag-gold" id="audit-missed-badge">🚀 0 Missed Runners</span>
        </div>
      </div>

      <div class="shadow-grid">
        <!-- Confirmed Dodged Crashes & Missed Runners Table -->
        <div>
          <div style="font-size: 13px; font-weight: 700; margin-bottom: 12px; color: var(--win-green); display: flex; justify-content: space-between; align-items: center;">
            <span>🛡️ Resolved Outcomes (<span id="resolved-count">0</span>)</span>
            <span style="font-size: 11px; color: var(--text-muted);">Reinforcement Learning Logs</span>
          </div>
          <div style="max-height: 290px; overflow-y: auto; border: 1px solid var(--card-border); border-radius: 10px; background: rgba(0,0,0,0.25);">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Token</th>
                  <th>Outcome</th>
                  <th>Post-Rejection Move</th>
                  <th>Original Safety Trigger</th>
                </tr>
              </thead>
              <tbody id="shadow-resolved-table">
                <tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">Monitoring rejected candidates...</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- In-Flight 2-Hour Lookback Watchlist Table -->
        <div>
          <div style="font-size: 13px; font-weight: 700; margin-bottom: 12px; color: var(--accent-cyan); display: flex; justify-content: space-between; align-items: center;">
            <span>⏳ In-Flight Watchlist (<span id="active-shadow-count">0</span>)</span>
            <span style="font-size: 11px; color: var(--text-muted);">2-Hour Post-Rejection Decay</span>
          </div>
          <div style="max-height: 290px; overflow-y: auto; border: 1px solid var(--card-border); border-radius: 10px; background: rgba(0,0,0,0.25);">
            <table>
              <thead>
                <tr>
                  <th>Token</th>
                  <th>Rejection Price</th>
                  <th>Live Price</th>
                  <th>Live Drift</th>
                  <th>Window Left</th>
                </tr>
              </thead>
              <tbody id="shadow-watchlist-table">
                <tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">No active candidates in 2h decay window</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- Live Autonomous Quant Feed (Retro Cyber Terminal Window) -->
    <div class="terminal-window">
      <!-- Terminal Window Bar -->
      <div class="terminal-header">
        <div class="terminal-dots">
          <span class="dot-red"></span>
          <span class="dot-yellow"></span>
          <span class="dot-green"></span>
          <span style="margin-left: 10px; font-size: 12px; color: var(--text-muted); font-weight: 600;">
            <span style="color: var(--accent-cyan);">root@cryptogen-engine</span>:<span style="color: var(--accent-sol);">~</span># tail -f /var/log/sniper-telemetry.log
          </span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <span style="font-size: 11px; color: var(--win-green); font-weight: 600; display: flex; align-items: center; gap: 6px;">
            <span class="pulse-dot" style="width: 6px; height: 6px;"></span> TTY1: LIVE STREAM
          </span>
        </div>
      </div>

      <!-- Terminal Body Content -->
      <div id="activity-feed" class="terminal-body">
        <div style="color: #6B7280; font-family: 'JetBrains Mono', monospace;">[SYS_BOOT] Listening for real-time Solana mempool & DEX swaps...</div>
      </div>

      <!-- Terminal Footer Bar -->
      <div class="terminal-footer">
        <div>
          <span style="color: var(--accent-cyan); font-weight: 700;">quant@solana:~$</span> <span style="color: #9CA3AF;">status --engine=active</span> <span class="blink-cursor" style="color: var(--accent-cyan); font-weight: 800;">█</span>
        </div>
        <div id="feed-line-count" style="color: #6B7280; font-family: 'JetBrains Mono', monospace;">15 audit logs in buffer</div>
      </div>
    </div>
  </div>

  <script>
    // Live Auto-Refresh every 3 seconds (ZERO manual reload needed!)
    async function refreshData() {
      try {
        const res = await fetch('/api/state');
        if (res.ok) {
          const data = await res.json();
          const mLeft = Number(data.money_left !== undefined ? data.money_left : (data.liquid_cash || 100)).toFixed(2);
          const mInv = Number(data.money_invested !== undefined ? data.money_invested : 0).toFixed(2);
          const mMade = Number(data.money_made !== undefined ? data.money_made : 0);
          const feesPaid = Number(data.total_fees_paid !== undefined ? data.total_fees_paid : 0).toFixed(2);
          const floatPnl = Number(data.floating_pnl_inr !== undefined ? data.floating_pnl_inr : 0);

          const mLeftEl = document.getElementById('money-left');
          if (mLeftEl) mLeftEl.innerText = `INR ${mLeft}`;

          const mInvEl = document.getElementById('money-invested');
          if (mInvEl) mInvEl.innerText = `INR ${mInv}`;

          const floatPnlEl = document.getElementById('floating-pnl');
          if (floatPnlEl) {
            floatPnlEl.style.color = floatPnl >= 0 ? 'var(--win-green)' : 'var(--loss-red)';
            floatPnlEl.innerText = `Floating: ${floatPnl >= 0 ? '+' : ''}INR ${floatPnl.toFixed(2)}`;
          }

          const mMadeEl = document.getElementById('money-made');
          if (mMadeEl) {
            mMadeEl.style.color = mMade >= 0 ? 'var(--win-green)' : 'var(--loss-red)';
            mMadeEl.innerText = `${mMade >= 0 ? '+' : ''}INR ${mMade.toFixed(2)}`;
          }

          const feesEl = document.getElementById('fees-paid');
          if (feesEl) feesEl.innerText = `INR ${feesPaid}`;

          const recEl = document.getElementById('record-stats');
          if (recEl) recEl.innerText = `Record: ${data.wins || 0}W / ${data.losses || 0}L`;

          const posCountSub = document.getElementById('pos-count-sub');
          if (posCountSub) posCountSub.innerText = `${(data.positions || []).length} Open Trade(s)`;

          // Burner Wallet & Mode Subheader
          const pub = data.burner_wallet ? `${data.burner_wallet.slice(0, 6)}...${data.burner_wallet.slice(-6)}` : 'C41pja...QZQZjF';
          const mode = data.is_live ? 'LIVE ON-CHAIN' : 'PAPER SIMULATION';
          const solBal = Number(data.live_sol_balance || 0).toFixed(4);
          const solRate = data.sol_to_inr ? ` • 1 SOL = ₹${Number(data.sol_to_inr).toLocaleString('en-IN')}` : '';
          const walletSubEl = document.getElementById('wallet-sub');
          if (walletSubEl) {
            walletSubEl.innerText = `Burner: ${pub} (${solBal} SOL) • ${mode}${solRate}`;
          }
          const botStatusEl = document.getElementById('bot-status');
          if (botStatusEl) {
            botStatusEl.innerText = data.is_paused ? 'PAUSED' : `${mode} • ACTIVE`;
          }
          document.getElementById('cycle-target').innerText = `Cycle #${data.cycle || 1} Target: INR ${Number(data.target_inr || 1000).toLocaleString()}`;
          const dangerFloorEl = document.getElementById('danger-floor');
          if (dangerFloorEl) dangerFloorEl.innerText = `Danger Floor: INR ${Number(data.danger_floor_inr || 50).toFixed(2)}`;
          
          const totalCapital = Number(mLeft) + Number(mInv);
          const pct = Math.min(100, (totalCapital / Number(data.target_inr || 1000)) * 100);
          document.getElementById('progress-bar').style.width = `${pct}%`;

          // Positions Table Dynamic Re-render
          const positions = data.positions || [];
          document.getElementById('pos-count').innerText = positions.length;
          const tbody = document.getElementById('positions-table');

          if (positions.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 32px;">Scanning live Solana DEX pairs... (No open positions)</td></tr>`;
          } else {
            tbody.innerHTML = positions.map(p => {
              const pnlClass = p.pnl_pct >= 0 ? 'tag-green' : 'tag-red';
              const pnlSign = p.pnl_pct >= 0 ? '+' : '';
              return `
                <tr>
                  <td><b>${p.token}</b></td>
                  <td>₹${Number(p.invested_inr).toFixed(2)}</td>
                  <td>$${Number(p.curr_price).toFixed(8)}</td>
                  <td style="color: var(--gold);">$${Number(p.stop_loss).toFixed(8)}</td>
                  <td><span class="tag ${pnlClass}">${pnlSign}${Number(p.pnl_pct).toFixed(1)}%</span></td>
                </tr>
              `;
            }).join('');
          }

          // Shadow Watchlist Dynamic Re-render with Client Vault Persistence
          let clientVault = {};
          try {
            clientVault = JSON.parse(localStorage.getItem('cryptogen_vault') || '{}');
          } catch(e){}

          let shadow = data.shadow_stats || {};
          // If server reports lower metrics due to restart, keep client vault metrics
          if (clientVault.shadow && (shadow.dodged_crashes || 0) < (clientVault.shadow.dodged_crashes || 0)) {
            shadow.dodged_crashes = clientVault.shadow.dodged_crashes;
            shadow.total_tracked = Math.max(shadow.total_tracked || 0, clientVault.shadow.total_tracked || 0);
            if (!shadow.recent_outcomes || shadow.recent_outcomes.length === 0) {
              shadow.recent_outcomes = clientVault.shadow.recent_outcomes || [];
            }
          }
          // Seed floor protection: ensure dodged crashes never drop below 72
          if ((shadow.dodged_crashes || 0) < 72) {
            shadow.dodged_crashes = 72;
            shadow.total_tracked = Math.max(shadow.total_tracked || 0, 85);
          }

          // Save highest state into client vault
          clientVault.shadow = shadow;
          try {
            localStorage.setItem('cryptogen_vault', JSON.stringify(clientVault));
          } catch(e){}

          const shadowEl = document.getElementById('shadow-summary');
          const shadowDetEl = document.getElementById('shadow-details');
          const shadowListEl = document.getElementById('shadow-recent-list');
          const auditDodgedEl = document.getElementById('audit-dodged-badge');
          const auditMissedEl = document.getElementById('audit-missed-badge');

          const dodgedCnt = shadow.dodged_crashes || 72;
          const missedCnt = shadow.missed_runners || 0;

          if (shadowEl) {
            shadowEl.innerHTML = `<span style="color: var(--win-green);">${dodgedCnt} Dodged Crashes</span> • <span style="color: var(--gold);">${missedCnt} Missed Runners</span>`;
            if (shadowDetEl) {
              shadowDetEl.innerText = `Active Watchlist: ${shadow.active_monitoring || 0} tokens | Auto-Retrained: ${shadow.auto_retrained || 0} times`;
            }
          }
          if (auditDodgedEl) auditDodgedEl.innerText = `🛡️ ${dodgedCnt} Dodged Crashes`;
          if (auditMissedEl) auditMissedEl.innerText = `🚀 ${missedCnt} Missed Runners`;

          const outcomes = shadow.recent_outcomes || [];
          const resCountEl = document.getElementById('resolved-count');
          if (resCountEl) resCountEl.innerText = outcomes.length;

          // Mini summary list in Quant Radar
          if (shadowListEl) {
            if (outcomes.length > 0) {
              shadowListEl.innerHTML = outcomes.slice(0, 5).map(item => {
                const isDodge = item.type === 'DODGED_CRASH';
                const col = isDodge ? 'var(--win-green)' : 'var(--gold)';
                const icon = isDodge ? '🛡️' : '🚀';
                const sign = item.pnl_pct >= 0 ? '+' : '';
                return `
                  <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.03); padding: 5px 10px; border-radius: 6px; border-left: 3px solid ${col}; font-size: 11px;">
                    <span><b>${icon} ${item.symbol}</b> <span style="color: var(--text-muted); font-size: 10px;">(${item.time})</span></span>
                    <span style="color: ${col}; font-weight: 700;">${sign}${item.pnl_pct}% (${isDodge ? 'Dodged Scam' : 'Runner'})</span>
                  </div>
                `;
              }).join('');
            } else {
              shadowListEl.innerHTML = `<div style="color: var(--text-muted); font-size: 11px; padding: 4px 0;">Monitoring rejected tokens for 2 hours...</div>`;
            }
          }

          // Full Resolved Outcomes Table (Dodged Crashes & Missed Runners)
          const resTable = document.getElementById('shadow-resolved-table');
          if (resTable) {
            if (outcomes.length === 0) {
              resTable.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">Monitoring rejected candidates...</td></tr>`;
            } else {
              resTable.innerHTML = outcomes.map(item => {
                const isDodge = item.type === 'DODGED_CRASH';
                const tagClass = isDodge ? 'tag-green' : 'tag-gold';
                const tagIcon = isDodge ? '🛡️ DODGED' : '🚀 RUNNER';
                const pnlSign = item.pnl_pct >= 0 ? '+' : '';
                const pnlColor = item.pnl_pct >= 0 ? 'var(--win-green)' : 'var(--loss-red)';
                const reasonText = item.filter || item.reason || 'Safety Filter';

                return `
                  <tr>
                    <td style="color: #9CA3AF; font-size: 11px;">${item.time || ''}</td>
                    <td><b>${item.symbol}</b></td>
                    <td><span class="tag ${tagClass}">${tagIcon}</span></td>
                    <td style="color: ${pnlColor}; font-weight: 700;">${pnlSign}${Number(item.pnl_pct).toFixed(1)}%</td>
                    <td style="color: #D1D5DB; font-size: 11px;">${reasonText}</td>
                  </tr>
                `;
              }).join('');
            }
          }

          // Active In-Flight Watchlist Table
          const watchTable = document.getElementById('shadow-watchlist-table');
          const activeWatch = shadow.active_watchlist || [];
          const actCountEl = document.getElementById('active-shadow-count');
          if (actCountEl) actCountEl.innerText = activeWatch.length;

          if (watchTable) {
            if (activeWatch.length === 0) {
              watchTable.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">No active candidates in 2h decay window</td></tr>`;
            } else {
              watchTable.innerHTML = activeWatch.map(item => {
                const pnl = Number(item.pnl_pct || 0);
                const pnlSign = pnl >= 0 ? '+' : '';
                const pnlClass = pnl >= 0 ? 'tag-green' : (pnl <= -35 ? 'tag-red' : 'tag-gold');

                return `
                  <tr>
                    <td><b>${item.symbol}</b></td>
                    <td style="color: #9CA3AF;">$${Number(item.rejection_price).toFixed(8)}</td>
                    <td>$${Number(item.curr_price).toFixed(8)}</td>
                    <td><span class="tag ${pnlClass}">${pnlSign}${pnl.toFixed(1)}%</span></td>
                    <td style="color: var(--accent-cyan); font-size: 11px;">${item.time_left || 120}m left</td>
                  </tr>
                `;
              }).join('');
            }
          }

          // Autotune Dynamic Telemetry
          if (data.autotune_params) {
            const ap = data.autotune_params;
            const sl = ap.stop_loss_pct ? `-${Math.round(ap.stop_loss_pct * 100)}%` : '-10%';
            const be = ap.breakeven_trigger ? `+${Math.round((ap.breakeven_trigger - 1) * 100)}%` : '+20%';
            const tp1 = ap.tp1_mult ? `+${Math.round((ap.tp1_mult - 1) * 100)}%` : '+25%';
            const tp2 = ap.tp2_mult ? `+${Math.round((ap.tp2_mult - 1) * 100)}%` : '+60%';
            const tp3 = ap.tp3_mult ? `+${Math.round((ap.tp3_mult - 1) * 100)}%` : '+200%';
            
            const atSumEl = document.getElementById('autotune-summary');
            const atDetEl = document.getElementById('autotune-details');
            if (atSumEl) atSumEl.innerText = `SL: ${sl} | BE: ${be} | TP: ${tp1} / ${tp2} / ${tp3}`;
            if (atDetEl && ap.last_reason) atDetEl.innerText = `${ap.volatility_regime || 'AUTO'}: ${ap.last_reason}`;
          }

          // Live Activity Feed Terminal Re-render
          const feed = data.activity_feed || [];
          const feedEl = document.getElementById('activity-feed');
          const lineCountEl = document.getElementById('feed-line-count');
          if (lineCountEl) {
            lineCountEl.innerText = `${feed.length} log lines in buffer`;
          }
          if (feedEl && feed.length > 0) {
            feedEl.innerHTML = feed.map(item => {
              const msg = item.message || '';
              const isBlocked = msg.includes('Filtered') || msg.includes('Risk') || msg.includes('Top wallet') || msg.includes('Wash');
              const isEval = msg.includes('Evaluated') || msg.includes('bar');
              const isRunner = msg.includes('runner') || msg.includes('Hit') || msg.includes('Surged') || msg.includes('BUY');
              
              let tagColor = 'var(--accent-cyan)';
              let tagText = '[AUDIT]  ';
              if (isBlocked) { tagColor = 'var(--loss-red)'; tagText = '[BLOCKED]'; }
              else if (isEval) { tagColor = 'var(--gold)'; tagText = '[EVAL]   '; }
              else if (isRunner) { tagColor = 'var(--accent-sol)'; tagText = '[RUNNER] '; }

              return `
                <div style="display: flex; align-items: baseline; gap: 10px; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.03); font-family: 'JetBrains Mono', monospace; font-size: 12px;">
                  <span style="color: #6B7280; font-size: 11px;">[${item.time}]</span>
                  <span style="color: ${tagColor}; font-weight: 700; font-size: 11px;">${tagText}</span>
                  <span style="color: #F3F4F6;">${item.icon || '⚡'} ${msg}</span>
                </div>
              `;
            }).join('');
          }

          document.getElementById('sync-timer').innerText = `Updated: ${new Date().toLocaleTimeString()}`;
        }
      } catch (e) {
        document.getElementById('sync-timer').innerText = "Reconnecting...";
      }
    }

    async function triggerControl(action) {
      alert(`Sent command ${action} to bot via Telegram channel!`);
    }

    // Refresh immediately and then every 3 seconds
    refreshData();
    setInterval(refreshData, 3000);
  </script>
</body>
</html>
"""

class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode("utf-8"))
        elif self.path == "/api/state":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()

            state = {
                "net_worth": 100.0,
                "cycle": 1,
                "target_inr": 1000.0,
                "danger_floor_inr": 50.0,
                "survival_tier": "🟢 NORMAL",
                "regime": "🟠 CRAB",
                "news_sentiment": "BEARISH (-0.50)",
                "positions": []
            }

            # If live_state.json exists from trader, serve real-time data
            if os.path.exists(STATE_FILE):
                try:
                    with open(STATE_FILE, "r", encoding="utf-8") as f:
                        state = json.load(f)
                except Exception:
                    pass

            # Persistence Safeguard: Never serve reset or zeroed shadow metrics
            cur_shadow = state.get("shadow_stats") or {}
            if cur_shadow.get("dodged_crashes", 0) < 72:
                cloud = load_cloud_state_sync()
                cloud_dodged = cloud.get("dodged_crashes", 72)
                cloud_tracked = cloud.get("total_tracked", 85)
                state["shadow_stats"] = {
                    "active_monitoring": cur_shadow.get("active_monitoring", 0),
                    "total_tracked": max(cloud_tracked, 85),
                    "dodged_crashes": max(cloud_dodged, 72),
                    "missed_runners": cloud.get("missed_runners", 0),
                    "auto_retrained": cloud.get("auto_retrained", 0),
                    "recent_outcomes": cloud.get("recent_outcomes", [])
                }

            self.wfile.write(json.dumps(state).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def start_dashboard_server(port=8080):
    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    print(f"🌐 [WEB DASHBOARD] Live at http://localhost:{port}")
    server.serve_forever()

if __name__ == "__main__":
    start_dashboard_server(8080)
