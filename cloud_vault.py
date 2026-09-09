"""
CryptoGen 24/7 Cloud State Vault

Provides permanent off-container cloud persistence for:
  • Shadow Radar intelligence metrics (dodged rugs, missed runners)
  • ML Brain training weights & experience replay
  • Cumulative compounding cycle metrics (portfolio INR, wins/losses)

Ensures that when Render redeploys or restarts ephemeral Docker containers,
all accumulated quantitative data and history are instantly restored.
"""

import os
import sys
import json
import time
import httpx
import asyncio
from typing import Dict, Any, Optional

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

VAULT_ID = "ff808181a067127101a08701b5305a0d"
VAULT_URL = f"https://api.restful-api.dev/objects/{VAULT_ID}"

_LAST_CLOUD_SYNC_TIME = 0
_SYNC_LOCK = asyncio.Lock()


def load_cloud_state_sync() -> Dict[str, Any]:
    """
    Synchronously fetches the persistent cloud backup on startup.
    Returns dictionary of state or empty dict if unreachable.
    """
    try:
        with httpx.Client(timeout=6.0) as client:
            res = client.get(VAULT_URL)
            if res.status_code == 200:
                data = res.json().get("data", {})
                print(f"☁️ [CLOUD VAULT] Restored persistent cloud state (Dodged: {data.get('dodged_crashes', 0)}).")
                return data
    except Exception as e:
        print(f"☁️ [CLOUD VAULT] Offline or startup timeout: {e}")
    return {}


async def load_cloud_state_async() -> Dict[str, Any]:
    """
    Asynchronously fetches persistent cloud state.
    """
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            res = await client.get(VAULT_URL)
            if res.status_code == 200:
                return res.json().get("data", {})
    except Exception:
        pass
    return {}


async def save_cloud_state_async(data_payload: Dict[str, Any], debounce_secs: int = 15):
    """
    Background non-blocking task that pushes state updates to the cloud vault.
    Debounced to respect rate limits.
    """
    global _LAST_CLOUD_SYNC_TIME
    now = time.time()
    if now - _LAST_CLOUD_SYNC_TIME < debounce_secs:
        return

    _LAST_CLOUD_SYNC_TIME = now
    try:
        payload = {
            "name": "cryptogen_state",
            "data": data_payload
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.put(VAULT_URL, json=payload)
            if res.status_code == 200:
                # Successfully saved
                pass
    except Exception:
        pass


def save_cloud_state_fire_and_forget(data_payload: Dict[str, Any]):
    """
    Schedules an async save task without blocking current execution.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(save_cloud_state_async(data_payload))
        else:
            asyncio.run(save_cloud_state_async(data_payload))
    except Exception:
        pass
