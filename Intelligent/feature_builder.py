import asyncio
import json
import websockets
import logging
import time

logger = logging.getLogger("intelligent.features")

class FeatureBuilder:
    def __init__(self, symbol="BTCUSDT"):
        self.symbol = symbol.lower()
        self.ws_url = f"wss://stream.binance.com:9443/ws/{self.symbol}@aggTrade/{self.symbol}@depth20@100ms"
        
        # Live Metrics
        self.cvd = 0.0
        self.ob_imbalance = 0.0
        self.last_update = 0
        
        self.running = False

    async def start(self):
        """Starts the Binance WebSocket stream to build features."""
        self.running = True
        while self.running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    logger.info(f"Feature Builder connected to Binance: {self.symbol.upper()}")
                    while self.running:
                        msg = await ws.recv()
                        try:
                            data = json.loads(msg)
                        except json.JSONDecodeError:
                            logger.error(f"Binance WS received non-JSON: {msg[:100]}...")
                            continue
                        self._process_message(data)
            except Exception as e:
                logger.error(f"Binance WS Error: {e}. Reconnecting...")
                await asyncio.sleep(5)

    def _process_message(self, data):
        stream = data.get("e")
        
        # 1. Process aggTrade for CVD
        if stream == "aggTrade":
            price = float(data.get("p"))
            qty = float(data.get("q"))
            is_buyer_maker = data.get("m") # True = Sell, False = Buy
            
            if not is_buyer_maker: # Market Buy
                self.cvd += qty
            else: # Market Sell
                self.cvd -= qty
                
        # 2. Process Depth for Imbalance
        elif "depth" in data.get("s", "").lower() or not stream: # Depth update
            bids = data.get("b", [])
            asks = data.get("a", [])
            
            if bids and asks:
                best_bid_vol = sum(float(b[1]) for b in bids[:5])
                best_ask_vol = sum(float(a[1]) for a in asks[:5])
                
                total = best_bid_vol + best_ask_vol
                if total > 0:
                    self.ob_imbalance = (best_bid_vol - best_ask_vol) / total
        
        self.last_update = time.time()

    def get_snapshot(self, up_token=None, down_token=None):
        """Returns the current technical features for the Gate."""
        features = {
            "cvd": round(self.cvd, 2),
            "ob_imbalance": round(self.ob_imbalance, 4),
            "up_token_id": up_token,
            "down_token_id": down_token,
            "timestamp": self.last_update
        }
        return features

    def reset_cvd(self):
        """Resets CVD every window if needed (or keep cumulative)."""
        self.cvd = 0.0

if __name__ == "__main__":
    fb = FeatureBuilder()
    async def test():
        asyncio.create_task(fb.start())
        while True:
            await asyncio.sleep(5)
            print(f"Features: {fb.get_snapshot()}")
            
    try:
        asyncio.run(test())
    except KeyboardInterrupt:
        pass
