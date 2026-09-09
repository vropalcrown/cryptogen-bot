import httpx
import base64
import os
import json
import asyncio
from dotenv import load_dotenv

load_dotenv()

JUPITER_QUOTE_API = "https://api.jup.ag/swap/v1/quote"
JUPITER_SWAP_API = "https://api.jup.ag/swap/v1/swap"
SOL_MINT = "So11111111111111111111111111111111111111112"

class SolanaOnChainExecutor:
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
                print(f"🔑 [On-Chain Executor] Wallet loaded: {self.wallet_pubkey[:6]}...{self.wallet_pubkey[-6:]}")
            except Exception as e:
                print(f"⚠️ [On-Chain Executor] Error parsing private key: {e}")

    async def get_swap_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount_lamports: int,
        slippage_bps: int = 150 # 1.5% slippage
    ) -> dict:
        """
        Queries Jupiter v6 API for optimal swap route.
        """
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount_lamports,
            "slippageBps": slippage_bps
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.get(JUPITER_QUOTE_API, params=params)
                if res.status_code == 200:
                    return res.json()
            except Exception as e:
                print(f"⚠️ [Jupiter API] Error fetching quote: {e}")
        return None

    async def execute_swap(
        self,
        input_mint: str,
        output_mint: str,
        amount_lamports: int,
        paper_mode: bool = True
    ) -> dict:
        """
        Builds, cryptographically signs, and broadcasts a live Solana transaction.
        """
        # Step 1: Fetch Jupiter quote
        quote = await self.get_swap_quote(input_mint, output_mint, amount_lamports)
        if not quote:
            return {"success": False, "reason": "Failed to obtain Jupiter swap route"}

        out_amount = int(quote.get("outAmount", 0))

        # Paper Mode: Return simulated hash without burning real SOL
        if paper_mode or not self.keypair:
            simulated_tx = "SIMULATED_ONCHAIN_TX_" + str(amount_lamports) + "_" + str(out_amount)
            return {
                "success": True,
                "mode": "PAPER_TRADING",
                "tx_hash": simulated_tx,
                "in_amount": amount_lamports,
                "out_amount": out_amount,
                "price_impact_pct": float(quote.get("priceImpactPct", 0.0))
            }

        # Step 2: Request serialized transaction from Jupiter
        payload = {
            "quoteResponse": quote,
            "userPublicKey": self.wallet_pubkey,
            "wrapAndUnwrapSol": True,
            "prioritizationFeeLamports": "auto" # Dynamic priority fee for fast inclusion
        }

        async with httpx.AsyncClient(timeout=12.0) as client:
            swap_res = await client.post(JUPITER_SWAP_API, json=payload)
            if swap_res.status_code != 200:
                return {"success": False, "reason": f"Jupiter swap build error: {swap_res.text}"}

            swap_json = swap_res.json()
            swap_tx_b64 = swap_json.get("swapTransaction")

        # Step 3: Deserialization & Cryptographic Signature
        try:
            from solders.transaction import VersionedTransaction
            raw_tx_bytes = base64.b64decode(swap_tx_b64)
            tx = VersionedTransaction.from_bytes(raw_tx_bytes)

            # Cryptographically sign transaction message with Keypair
            signature = self.keypair.sign_message(bytes(tx.message))
            signed_tx = VersionedTransaction.populate(tx.message, [signature])
            signed_tx_b64 = base64.b64encode(bytes(signed_tx)).decode("utf-8")

            # Step 4: Broadcast to Solana RPC
            rpc_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendTransaction",
                "params": [
                    signed_tx_b64,
                    {"encoding": "base64", "skipPreflight": False, "maxRetries": 3}
                ]
            }

            async with httpx.AsyncClient(timeout=15.0) as client:
                rpc_res = await client.post(self.rpc_url, json=rpc_payload)
                rpc_json = rpc_res.json()
                
                if "result" in rpc_json:
                    tx_hash = rpc_json["result"]
                    print(f"🚀 [ON-CHAIN BROADCAST SUCCESS] TX Hash: {tx_hash}")
                    return {
                        "success": True,
                        "mode": "LIVE_MAINNET",
                        "tx_hash": tx_hash,
                        "solscan_url": f"https://solscan.io/tx/{tx_hash}"
                    }
                else:
                    return {"success": False, "reason": f"RPC error: {rpc_json.get('error')}"}

        except Exception as e:
            return {"success": False, "reason": f"Signing error: {str(e)}"}
