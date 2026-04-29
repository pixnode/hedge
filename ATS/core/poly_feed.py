import asyncio
import json
import logging
import time
import websockets
import requests
from dataclasses import dataclass

logger = logging.getLogger("poly_feed")
logger.setLevel(logging.INFO)

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
        self.last_subscribed_tokens = set()
        self.latest_data = {} # Maps token_id -> {"ask": float, "bid": float}
        
        self.running = False
        self.ws_connection = None

    async def update_subscription(self, tokens: list):
        if not tokens:
            return
            
        new_set = set(tokens)
        # Optimization: Only send update if tokens actually changed
        if new_set == self.last_subscribed_tokens:
            return
            
        self.monitored_tokens = new_set
        
        if self.ws_connection:
            sub_msg = {
                "operation": "subscribe",
                "assets_ids": [str(t) for t in self.monitored_tokens]
            }
            try:
                outgoing_json = json.dumps(sub_msg)
                print(f"DEBUG: Updating Poly Sub (Update Op): {outgoing_json}")
                await self.ws_connection.send(outgoing_json)
                self.last_subscribed_tokens = set(self.monitored_tokens)
            except Exception as e:
                print(f"DEBUG: Update Sub Failed: {e}")

    async def connect_and_listen(self):
        self.running = True
        while self.running:
            try:
                # Wait until we actually have tokens
                while self.running and not self.monitored_tokens:
                    await asyncio.sleep(1)
                
                if not self.running: break
                
                print(f"DEBUG: Connecting to Poly WS: {self.ws_url}")
                async with websockets.connect(self.ws_url) as ws:
                    print(f"DEBUG: Poly WS Handshake Success")
                    self.ws_connection = ws
                    
                    # Grace period for connection stability
                    await asyncio.sleep(1.0)
                    
                    # Initial Subscription - Using "initial_dump" for faster data arrival
                    sub_msg = {
                        "type": "market",
                        "assets_ids": [str(t) for t in self.monitored_tokens]
                    }
                    outgoing_json = json.dumps(sub_msg)
                    print(f"DEBUG: Sending Initial Sub: {outgoing_json}")
                    await ws.send(outgoing_json)
                    self.last_subscribed_tokens = set(self.monitored_tokens)
                    
                    async for msg in ws:
                        if not self.running:
                            break
                        try:
                            data = json.loads(msg)
                            self._process_message(data)
                        except json.JSONDecodeError:
                            if "INVALID" in msg or "ERROR" in msg:
                                print(f"DEBUG: Server Alert: {msg}")
                            continue
                        
            except Exception as e:
                self.ws_connection = None
                self.last_subscribed_tokens = set() # Reset on error to force re-sub
                print(f"DEBUG: Poly WS Loop Error: {e}")
                await asyncio.sleep(5)

    def _process_message(self, data):
        if isinstance(data, list):
            for item in data:
                self._process_single_message(item)
        elif isinstance(data, dict):
            # Check for L2 format wrap
            if "event_type" in data:
                self._process_single_message(data)
            elif "asset_id" in data:
                self._process_single_message(data)

    def _process_single_message(self, data: dict):
        asset_id = data.get("asset_id")
        if not asset_id:
            return

        if str(asset_id) not in [str(t) for t in self.monitored_tokens]:
            return

        if asset_id not in self.latest_data:
            self.latest_data[asset_id] = {"ask": 0.0, "bid": 0.0}

        # Handling both L2 and Book format
        asks = data.get("asks") or data.get("ask", [])
        bids = data.get("bids") or data.get("bid", [])
        
        updated = False
        if asks and isinstance(asks, list):
            try:
                self.latest_data[asset_id]["ask"] = min([float(ask["price"]) for ask in asks if float(ask["size"]) > 0])
                updated = True
            except: pass

        if bids and isinstance(bids, list):
            try:
                self.latest_data[asset_id]["bid"] = max([float(bid["price"]) for bid in bids if float(bid["size"]) > 0])
                updated = True
            except: pass
            
        if updated:
            event = OrderBookEvent(
                asset_id=asset_id, 
                ask=self.latest_data[asset_id]["ask"], 
                bid=self.latest_data[asset_id]["bid"],
                timestamp=time.time()
            )
            try:
                self.queue.put_nowait(event)
            except: pass
