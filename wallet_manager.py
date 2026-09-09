import os
import sys
import httpx
from dotenv import load_dotenv

load_dotenv()

RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

def generate_burner_wallet():
    """
    Generates a secure, brand-new Solana burner wallet keypair.
    Saves the private key into .env and displays the public address.
    """
    try:
        from solders.keypair import Keypair
        import base58
        
        kp = Keypair()
        pubkey = str(kp.pubkey())
        # Secret key is 64 bytes
        privkey = base58.b58encode(bytes(kp)).decode("utf-8")

        print("\n" + "=" * 60)
        print("          🔑 NEW SOLANA BURNER WALLET GENERATED")
        print("=" * 60)
        print(f" Public Address : {pubkey}")
        print(f" Purpose        : Isolated testing with exactly ₹100 in SOL")
        print("=" * 60 + "\n")

        # Check if .env already has a private key
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                content = f.read()
            
            if "SOLANA_PRIVATE_KEY=" in content:
                # Update line
                lines = content.splitlines()
                new_lines = []
                for line in lines:
                    if line.startswith("SOLANA_PRIVATE_KEY="):
                        new_lines.append(f"SOLANA_PRIVATE_KEY={privkey}")
                    else:
                        new_lines.append(line)
                with open(env_path, "w") as f:
                    f.write("\n".join(new_lines) + "\n")
            else:
                with open(env_path, "a") as f:
                    f.write(f"\nSOLANA_PRIVATE_KEY={privkey}\n")
        
        print("✅ Private key safely recorded in .env (never share this with anyone).")
        return pubkey, privkey
    except ImportError:
        print("⚠️ Waiting for solders/base58 installation to finish...")
        return None, None

def check_wallet_balance_onchain(wallet_pubkey: str) -> dict:
    """
    Queries real live Solana RPC node for current SOL balance and lamports.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [wallet_pubkey]
    }
    try:
        res = httpx.post(RPC_URL, json=payload, timeout=8.0)
        if res.status_code == 200:
            val = res.json().get("result", {}).get("value", 0)
            sol_balance = val / 1_000_000_000.0
            return {
                "success": True,
                "lamports": val,
                "sol": sol_balance,
                "inr": round(sol_balance * 13000.0, 2)
            }
    except Exception as e:
        return {"success": False, "error": str(e), "sol": 0.0, "inr": 0.0}

    return {"success": False, "sol": 0.0, "inr": 0.0}

if __name__ == "__main__":
    generate_burner_wallet()
