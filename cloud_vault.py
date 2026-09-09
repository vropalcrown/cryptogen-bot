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
_CACHED_CLOUD_STATE: Dict[str, Any] = {}


def load_cloud_state_sync() -> Dict[str, Any]:
    """
    Synchronously fetches the persistent cloud backup on startup.
    Returns dictionary of state or empty dict if unreachable.
    """
    global _CACHED_CLOUD_STATE
    try:
        with httpx.Client(timeout=6.0) as client:
            res = client.get(VAULT_URL)
            if res.status_code == 200:
                data = res.json().get("data", {})
                _CACHED_CLOUD_STATE.update(data)
                print(f"☁️ [CLOUD VAULT] Restored persistent cloud state (Dodged: {data.get('dodged_crashes', 0)}).")
                return data
    except Exception as e:
        print(f"☁️ [CLOUD VAULT] Offline or startup timeout: {e}")
    return _CACHED_CLOUD_STATE


async def load_cloud_state_async() -> Dict[str, Any]:
    """
    Asynchronously fetches persistent cloud state.
    """
    global _CACHED_CLOUD_STATE
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            res = await client.get(VAULT_URL)
            if res.status_code == 200:
                data = res.json().get("data", {})
                _CACHED_CLOUD_STATE.update(data)
                return data
    except Exception:
        pass
    return _CACHED_CLOUD_STATE


async def save_cloud_state_async(data_payload: Dict[str, Any], debounce_secs: int = 15, force: bool = False):
    """
    Background non-blocking task that pushes state updates to the cloud vault.
    Merges data_payload into _CACHED_CLOUD_STATE so no subsystem overwrites another.
    """
    global _LAST_CLOUD_SYNC_TIME, _CACHED_CLOUD_STATE
    now = time.time()
    if not force and (now - _LAST_CLOUD_SYNC_TIME < debounce_secs):
        # Even if debounced, keep cache updated locally
        _CACHED_CLOUD_STATE.update(data_payload)
        return

    _LAST_CLOUD_SYNC_TIME = now
    _CACHED_CLOUD_STATE.update(data_payload)
    try:
        payload = {
            "name": "cryptogen_state",
            "data": _CACHED_CLOUD_STATE
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.put(VAULT_URL, json=payload)
            if res.status_code == 200:
                pass
    except Exception:
        pass


def save_cloud_state_fire_and_forget(data_payload: Dict[str, Any], force: bool = False):
    """
    Schedules an async save task without blocking current execution.
    """
    global _CACHED_CLOUD_STATE
    _CACHED_CLOUD_STATE.update(data_payload)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(save_cloud_state_async(data_payload, force=force))
        else:
            asyncio.run(save_cloud_state_async(data_payload, force=force))
    except Exception:
        pass
