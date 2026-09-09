import os
import httpx
import base64
from dotenv import load_dotenv

load_dotenv()

TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

class ATARentReclaimer:
    def __init__(self):
        self.rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
        self.private_key_b58 = os.getenv("SOLANA_PRIVATE_KEY", "").strip()
        self.keypair = None
        self.wallet_pubkey = None

        if self.private_key_b58:
            try:
                import base58
                from solders.keypair import Keypair
                raw_bytes = base58.b58decode(self.private_key_b58)
                self.keypair = Keypair.from_bytes(raw_bytes)
                self.wallet_pubkey = str(self.keypair.pubkey())
            except Exception:
                pass

    def find_empty_token_accounts(self) -> list:
        """
        Scans on-chain for Associated Token Accounts owned by the wallet with 0 token balance.
        Each empty account holds 0.00203928 SOL of refundable rent.
        """
        if not self.wallet_pubkey:
            return []

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                self.wallet_pubkey,
                {"programId": TOKEN_PROGRAM_ID},
                {"encoding": "jsonParsed"}
            ]
        }

        try:
            res = httpx.post(self.rpc_url, json=payload, timeout=10.0)
            if res.status_code == 200:
                accounts = res.json().get("result", {}).get("value", [])
                empty_atas = []
                for acc in accounts:
                    info = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                    amount = int(info.get("tokenAmount", {}).get("amount", "0"))
                    if amount == 0:
                        empty_atas.append({
                            "pubkey": acc["pubkey"],
                            "mint": info.get("mint")
                        })
                return empty_atas
        except Exception as e:
            print(f"⚠️ [ATA Scanner] Error querying token accounts: {e}")

        return []

    def reclaim_rent(self, token_account_pubkey: str, paper_mode: bool = True) -> dict:
        """
        Executes close_account instruction to reclaim ~0.002039 SOL back to main balance.
        """
        if paper_mode or not self.keypair:
            return {
                "success": True,
                "reclaimed_sol": 0.00203928,
                "reclaimed_inr": round(0.00203928 * 13000.0, 2),
                "mode": "PAPER_TRADING_RECLAIMED"
            }

        try:
            from solders.pubkey import Pubkey
            from solders.instruction import Instruction, AccountMeta
            from solders.message import Message
            from solders.transaction import Transaction

            token_acc = Pubkey.from_string(token_account_pubkey)
            dest_wallet = self.keypair.pubkey()
            token_prog = Pubkey.from_string(TOKEN_PROGRAM_ID)

            # SPL Token CloseAccount instruction (index 9)
            close_instruction_data = bytes([9])
            keys = [
                AccountMeta(pubkey=token_acc, is_signer=False, is_writable=True),
                AccountMeta(pubkey=dest_wallet, is_signer=False, is_writable=True),
                AccountMeta(pubkey=dest_wallet, is_signer=True, is_writable=False),
            ]
            ix = Instruction(token_prog, close_instruction_data, keys)

            # Build and send transaction
            # Fetch recent blockhash
            res = httpx.post(self.rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": "getLatestBlockhash"})
            blockhash_str = res.json()["result"]["value"]["blockhash"]
            from solders.hash import Hash
            recent_blockhash = Hash.from_string(blockhash_str)

            msg = Message([ix], dest_wallet)
            tx = Transaction([self.keypair], msg, recent_blockhash)
            raw_b64 = base64.b64encode(bytes(tx)).decode("utf-8")

            # Broadcast
            send_res = httpx.post(self.rpc_url, json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendTransaction",
                "params": [raw_b64, {"encoding": "base64"}]
            })
            tx_hash = send_res.json().get("result")
            print(f"💰 [ATA RENT RECLAIMED] 0.002039 SOL refunded! TX: {tx_hash}")
            return {"success": True, "tx_hash": tx_hash, "reclaimed_sol": 0.00203928}
        except Exception as e:
            return {"success": False, "error": str(e)}

if __name__ == "__main__":
    reclaimer = ATARentReclaimer()
    print("Scanning empty token accounts on-chain...")
    empty = reclaimer.find_empty_token_accounts()
    print(f"Found {len(empty)} empty accounts eligible for rent reclaim.")
