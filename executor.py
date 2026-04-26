import asyncio
import logging
from py_clob_client.client import ClobClient
from config import Config

# Robust Import for OrderArgs
try:
    from py_clob_client.clob_types import OrderArgs
except ImportError:
    OrderArgs = None

logger = logging.getLogger("executor")
logger.setLevel(logging.WARNING)

class OrderExecutor:
    def __init__(self, config: Config):
        try:
            from eth_account import Account
            account = Account.from_key(config.POLYMARKET_PRIVATE_KEY)
            
            funder_addr = config.POLY_PROXY_ADDRESS if config.POLY_PROXY_ADDRESS else account.address
            
            self.client = ClobClient(
                host=config.CLOB_HOST,
                key=config.POLYMARKET_PRIVATE_KEY,
                chain_id=137, 
                signature_type=config.SIGNATURE_TYPE,
                funder=funder_addr
            )
            # API Key Management (Safe Approach)
            if config.POLY_API_KEY:
                try:
                    self.client.set_api_creds({
                        "apiKey": config.POLY_API_KEY,
                        "secret": config.POLY_API_SECRET,
                        "passphrase": config.POLY_API_PASSPHRASE
                    })
                except Exception as e:
                    logger.error(f"API Creds skipping: {e}")
            else:
                try:
                    creds = self.client.create_api_key()
                    self.client.set_api_creds(creds)
                except Exception as e:
                    logger.error(f"API Creation failed: {e}")
                
        except Exception as e:
            import traceback
            logger.error(f"CRITICAL INIT ERROR:\n{traceback.format_exc()}")
            self.client = None
        
    def _execute_sync(self, token_id: str, side: str, limit_price: float, size: float):
        if not self.client:
            return {"status": "FAILED", "error": "ClobClient not initialized"}
        try:
            # Skenario: Library mewajibkan Object (bukan dict) tapi import bisa berbeda versi
            if OrderArgs is not None:
                order_args = OrderArgs(
                    token_id=token_id,
                    price=float(limit_price),
                    size=float(size),
                    side="BUY"
                )
            else:
                # Fallback: Jika OrderArgs tidak bisa diimpor, kita buat Object buatan
                # karena library mencoba memanggil .token_id
                from types import SimpleNamespace
                order_args = SimpleNamespace(
                    token_id=token_id,
                    price=float(limit_price),
                    size=float(size),
                    side="BUY"
                )
            
            # Post order
            resp = self.client.create_and_post_order(order_args)
            
            # Debugging: Catat response jika gagal
            if resp and isinstance(resp, dict) and resp.get("success"):
                return {
                    "status": "FILLED",
                    "filled_price": limit_price,
                    "tx_hash": resp.get("orderID", "unknown")
                }
            else:
                error_msg = resp.get("error") if isinstance(resp, dict) else str(resp)
                logger.error(f"Execution Failed Response: {resp}")
                return {"status": "FAILED", "error": error_msg if error_msg else "Unknown API Error"}
                
        except Exception as e:
            import traceback
            err_detail = traceback.format_exc()
            logger.error(f"CRITICAL EXECUTION ERROR:\n{err_detail}")
            return {"status": "FAILED", "error": str(e)}

    async def execute(self, token_id: str, side: str, current_ask: float, size: float, config: Config):
        # Tambahkan sedikit delay jika gagal agar tidak 'spamming'
        limit_price = round(current_ask + config.ABSOLUTE_SLIPPAGE, 3)
        if limit_price > 0.99: limit_price = 0.99
            
        result = await asyncio.to_thread(self._execute_sync, token_id, side, limit_price, size)
        
        # Cool-down jika gagal
        if result.get("status") == "FAILED":
            await asyncio.sleep(1.0)
            
        return result
