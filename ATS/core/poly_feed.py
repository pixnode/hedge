import asyncio
import json
import logging
import time
import websockets
from dataclasses import dataclass

logger = logging.getLogger("poly_feed")
logger.setLevel(logging.WARNING)

@dataclass
class OrderBookEvent:
    asset_id: str
    ask: float
    bid: float
    timestamp: float

class PolyWebsocketFeed:
    def __init__(self, ws_url: str, queue: asyncio.Queue):
        self.ws_url = ws_url
        self.queue = queue
        self.monitored_tokens = set()
        self.latest_data = {} # Maps token_id -> {"ask": float, "bid": float}
        
        self.running = False
        self.ws_connection = None

    async def update_subscription(self, tokens: list):
        """
        Updates the active subscription. 
        Ensures memory is cleaned up by removing tokens not in the new list.
        """
        new_set = set(tokens)
        
        # Memory Leak Prevention: Remove stale token data
        stale_tokens = set(self.latest_data.keys()) - new_set
        for token in stale_tokens:
            self.latest_data.pop(token, None)
            
        self.monitored_tokens = new_set
        
        if self.ws_connection:
            sub_msg = {
                "type": "market",
                "assets_ids": list(self.monitored_tokens)
            }
            try:
                await self.ws_connection.send(json.dumps(sub_msg))
            except Exception as e:
                logger.error(f"Failed to subscribe: {e}")

    async def connect_and_listen(self):
        self.running = True
        while self.running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    self.ws_connection = ws
                    if self.monitored_tokens:
                        await self.update_subscription(list(self.monitored_tokens))
                    
                    async for msg in ws:
                        if not self.running:
                            break
                        try:
                            data = json.loads(msg)
                        except json.JSONDecodeError:
                            logger.error(f"Poly WS received non-JSON: {msg[:100]}...")
                            continue
                        self._process_message(data)
                        
            except Exception as e:
                logger.error(f"WebSocket error: {e}. Reconnecting in 2s...")
                await asyncio.sleep(2)

    def _process_message(self, data):
        # Proteksi List/Dict (L2 JSON Structure Variation)
        if isinstance(data, list):
            for item in data:
                self._process_single_message(item)
        elif isinstance(data, dict):
            self._process_single_message(data)

    def _process_single_message(self, data: dict):
        asset_id = data.get("asset_id")
        if not asset_id or asset_id not in self.monitored_tokens:
            return

        if asset_id not in self.latest_data:
            self.latest_data[asset_id] = {"ask": 0.0, "bid": 0.0}

        asks = data.get("asks", [])
        bids = data.get("bids", [])
        
        # Extract Best Ask
        if not asks:
            self.latest_data[asset_id]["ask"] = 0.0
        else:
            try:
                best_ask = min([float(ask["price"]) for ask in asks if float(ask["size"]) > 0])
                self.latest_data[asset_id]["ask"] = best_ask
            except ValueError:
                self.latest_data[asset_id]["ask"] = 0.0

        # Extract Best Bid
        if not bids:
            self.latest_data[asset_id]["bid"] = 0.0
        else:
            try:
                best_bid = max([float(bid["price"]) for bid in bids if float(bid["size"]) > 0])
                self.latest_data[asset_id]["bid"] = best_bid
            except ValueError:
                self.latest_data[asset_id]["bid"] = 0.0
            
        # Emit event for the specific asset
        event = OrderBookEvent(
            asset_id=asset_id, 
            ask=self.latest_data[asset_id]["ask"], 
            bid=self.latest_data[asset_id]["bid"],
            timestamp=time.time()
        )
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            pass
