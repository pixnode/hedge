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
    up_ask: float
    down_ask: float
    timestamp: float

class PolyWebsocketFeed:
    def __init__(self, ws_url: str, queue: asyncio.Queue):
        self.ws_url = ws_url
        self.queue = queue
        self.up_token = None
        self.down_token = None
        
        self.up_ask = 0.0
        self.down_ask = 0.0
        
        self.running = False
        self.ws_connection = None

    async def update_subscription(self, up_token: str, down_token: str):
        self.up_token = up_token
        self.down_token = down_token
        self.up_ask = 0.0
        self.down_ask = 0.0
        
        if self.ws_connection:
            sub_msg = {
                "assets_ids": [self.up_token, self.down_token],
                "type": "market"
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
                    if self.up_token and self.down_token:
                        await self.update_subscription(self.up_token, self.down_token)
                    
                    async for msg in ws:
                        if not self.running:
                            break
                        data = json.loads(msg)
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
        if not asset_id or asset_id not in (self.up_token, self.down_token):
            return

        asks = data.get("asks", [])
        
        # Validasi Likuiditas Dicabut (Phantom Spread fix)
        if not asks:
            if asset_id == self.up_token:
                self.up_ask = 0.0
            elif asset_id == self.down_token:
                self.down_ask = 0.0
            return

        try:
            best_ask = min([float(ask["price"]) for ask in asks if float(ask["size"]) > 0])
        except ValueError:
            if asset_id == self.up_token:
                self.up_ask = 0.0
            elif asset_id == self.down_token:
                self.down_ask = 0.0
            return
            
        if asset_id == self.up_token:
            self.up_ask = best_ask
        elif asset_id == self.down_token:
            self.down_ask = best_ask

        # Hanya isi queue jika kedua ask > 0
        if self.up_ask > 0 and self.down_ask > 0:
            event = OrderBookEvent(up_ask=self.up_ask, down_ask=self.down_ask, timestamp=time.time())
            try:
                self.queue.put_nowait(event)
            except asyncio.QueueFull:
                pass
