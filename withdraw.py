import sys
import os
import httpx
import base64
from dotenv import load_dotenv

load_dotenv()

RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
PRIVKEY = os.getenv("SOLANA_PRIVATE_KEY", "").strip()

def withdraw_all(destination_pubkey: str):
    """
    Transfers all SOL from the burner wallet back to your personal wallet.
    """
    if not PRIVKEY:
        print("❌ No private key found in .env.")
        return

    try:
        import base58
        from solders.keypair import Keypair
        from solders.pubkey import Pubkey
        from solders.system_program import transfer, TransferParams
        from solders.message import Message
        from solders.transaction import Transaction
        from solders.hash import Hash

        raw = base58.b58decode(PRIVKEY)
        keypair = Keypair.from_bytes(raw)
        dest = Pubkey.from_string(destination_pubkey)

        # 1. Check current balance
        res = httpx.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": 1, "method": "getBalance",
            "params": [str(keypair.pubkey())]
        })
        balance_lamports = res.json().get("result", {}).get("value", 0)

        if balance_lamports <= 5000:
            print(f"⚠️ Wallet has only {balance_lamports / 1e9:.6f} SOL. Insufficient for gas.")
            return

        # Reserve 5,000 lamports for the transaction fee
        amount_to_send = balance_lamports - 5000

        # 2. Build transfer instruction
        ix = transfer(TransferParams(
            from_pubkey=keypair.pubkey(),
            to_pubkey=dest,
            lamports=amount_to_send
        ))

        # 3. Get recent blockhash
        bh_res = httpx.post(RPC_URL, json={"jsonrpc": "2.0", "id": 1, "method": "getLatestBlockhash"})
        blockhash_str = bh_res.json()["result"]["value"]["blockhash"]
        recent_blockhash = Hash.from_string(blockhash_str)

        msg = Message([ix], keypair.pubkey())
        tx = Transaction([keypair], msg, recent_blockhash)
        raw_b64 = base64.b64encode(bytes(tx)).decode("utf-8")

        # 4. Broadcast
        send_res = httpx.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": 1, "method": "sendTransaction",
            "params": [raw_b64, {"encoding": "base64"}]
        })
        tx_hash = send_res.json().get("result")

        if tx_hash:
            print("\n" + "=" * 60)
            print("          💸 WITHDRAWAL SUCCESSFUL")
            print("=" * 60)
            print(f" Sent           : {amount_to_send / 1e9:.6f} SOL (~₹{(amount_to_send / 1e9) * 13000:.2f})")
            print(f" Destination    : {destination_pubkey}")
            print(f" Solscan Link   : https://solscan.io/tx/{tx_hash}")
            print("=" * 60 + "\n")
        else:
            print(f"❌ Transfer failed: {send_res.text}")

    except Exception as e:
        print(f"❌ Error during withdrawal: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python withdraw.py <YOUR_PERSONAL_SOLANA_ADDRESS>")
    else:
        withdraw_all(sys.argv[1])
