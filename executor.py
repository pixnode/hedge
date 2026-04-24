import asyncio
import logging
from py_clob_client.client import ClobClient
from config import Config

logger = logging.getLogger("executor")
logger.setLevel(logging.WARNING)

class OrderExecutor:
    def __init__(self, config: Config):
        # We wrap in try-except so it doesn't crash if py_clob_client is not installed locally
        try:
            self.client = ClobClient(
                host=config.CLOB_HOST,
                key=config.POLYMARKET_PRIVATE_KEY if config.POLYMARKET_PRIVATE_KEY else "0x" + "0"*64,
                chain_id=137, 
                signature_type=1,
                funder=config.POLYMARKET_PRIVATE_KEY if config.POLYMARKET_PRIVATE_KEY else "0x" + "0"*64
            )
            self.client.set_api_creds(
                self.client.create_api_key() if not config.POLY_API_KEY else {
                    "apiKey": config.POLY_API_KEY,
                    "secret": config.POLY_API_SECRET,
                    "passphrase": config.POLY_API_PASSPHRASE
                }
            )
        except Exception as e:
            logger.error(f"Failed to initialize ClobClient: {e}")
            self.client = None
        
    def _execute_sync(self, token_id: str, side: str, limit_price: float, size: float):
        if not self.client:
            return {"status": "FAILED", "error": "ClobClient not initialized"}
        try:
            order_args = {
                "token_id": token_id,
                "price": limit_price,
                "size": size,
                "side": "BUY" # Side is always BUY for taking long exposure on either UP or DOWN token
            }
            resp = self.client.create_and_post_order(order_args)
            
            if resp and resp.get("success"):
                return {
                    "status": "FILLED",
                    "filled_price": limit_price,
                    "tx_hash": resp.get("orderID", "unknown")
                }
            else:
                return {"status": "FAILED", "error": str(resp)}
                
        except Exception as e:
            return {"status": "FAILED", "error": str(e)}

    async def execute(self, token_id: str, side: str, current_ask: float, size: float, config: Config):
        # Removal of slippage: Using current_ask as the limit price directly
        limit_price = round(current_ask, 3)
        if limit_price > 0.99:
            limit_price = 0.99
            
        result = await asyncio.to_thread(self._execute_sync, token_id, side, limit_price, size)
        return result
