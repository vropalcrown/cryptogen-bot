"""
CryptoGen State Vault (Secure Local & Authenticated Persistence)

Provides atomic on-disk persistence for:
  • Trading state & journal statistics
  • ML Brain training weights & experience replay
  • Cumulative compounding cycle metrics (portfolio INR, wins/losses)

Replaces unauthenticated public sandbox practice APIs with secure local atomic storage
and optional authenticated private storage (via CLOUD_VAULT_URL + CLOUD_VAULT_KEY).
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

VAULT_FILE = os.path.join(os.path.dirname(__file__), "vault_state.json")
PRIVATE_VAULT_URL = os.getenv("CLOUD_VAULT_URL", "").strip()
PRIVATE_VAULT_KEY = os.getenv("CLOUD_VAULT_KEY", "").strip()

_LAST_SYNC_TIME = 0
_CACHED_STATE: Dict[str, Any] = {}


def load_cloud_state_sync() -> Dict[str, Any]:
    """
    Synchronously fetches persistent state from secure local vault.
    """
    global _CACHED_STATE
    if os.path.exists(VAULT_FILE):
        try:
            with open(VAULT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _CACHED_STATE.update(data)
                print(f"🔒 [STATE VAULT] Loaded persistent state ({len(_CACHED_STATE)} keys).")
                return data
        except Exception as e:
            print(f"⚠️ [STATE VAULT] Notice reading local vault: {e}")

    # Optional private authenticated remote fallback
    if PRIVATE_VAULT_URL and PRIVATE_VAULT_KEY:
        try:
            import httpx
            with httpx.Client(timeout=10.0) as client:
                res = client.get(PRIVATE_VAULT_URL, headers={"Authorization": f"Bearer {PRIVATE_VAULT_KEY}"})
                if res.status_code == 200:
                    data = res.json().get("data", {})
                    _CACHED_STATE.update(data)
                    return data
        except Exception:
            pass

    return _CACHED_STATE


async def load_cloud_state_async() -> Dict[str, Any]:
    """
    Asynchronously fetches persistent state.
    """
    return load_cloud_state_sync()


def _write_local_atomic(data: Dict[str, Any]):
    """Safely writes JSON to disk using atomic tempfile replace."""
    tmp_file = f"{VAULT_FILE}.tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        if os.path.exists(VAULT_FILE):
            os.replace(tmp_file, VAULT_FILE)
        else:
            os.rename(tmp_file, VAULT_FILE)
    except Exception as e:
        try:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
        except Exception:
            pass


async def save_cloud_state_async(data_payload: Dict[str, Any], debounce_secs: int = 5, force: bool = False):
    """
    Persists updated state locally and optionally to private authenticated backend.
    """
    global _LAST_SYNC_TIME, _CACHED_STATE
    now = time.time()
    _CACHED_STATE.update(data_payload)

    if not force and (now - _LAST_SYNC_TIME < debounce_secs):
        return

    _LAST_SYNC_TIME = now
    _write_local_atomic(_CACHED_STATE)

    # Optional private authenticated cloud sync
    if PRIVATE_VAULT_URL and PRIVATE_VAULT_KEY:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.put(
                    PRIVATE_VAULT_URL,
                    json={"data": _CACHED_STATE},
                    headers={"Authorization": f"Bearer {PRIVATE_VAULT_KEY}"}
                )
        except Exception:
            pass


def save_cloud_state_fire_and_forget(data_payload: Dict[str, Any], force: bool = False):
    """
    Schedules state save without blocking execution.
    """
    global _CACHED_STATE
    _CACHED_STATE.update(data_payload)
    _write_local_atomic(_CACHED_STATE)
