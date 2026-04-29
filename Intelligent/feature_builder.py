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
                # Enable ping/pong to keep connection alive
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=10) as ws:
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
        elif "bids" in data or "b" in data: # Depth update (bids/asks present)
            bids = data.get("b", data.get("bids", []))
            asks = data.get("a", data.get("asks", []))
            
            if bids and asks:
                # Get top 5 levels
                best_bid_vol = sum(float(b[1]) for b in bids[:5])
                best_ask_vol = sum(float(a[1]) for a in asks[:5])
                
                total = best_bid_vol + best_ask_vol
                if total > 0:
                    self.ob_imbalance = (best_bid_vol - best_ask_vol) / total
        
        self.last_update = time.time()

    def get_snapshot(self):
        """Returns the current technical features for the Gate."""
        return {
            "cvd": round(self.cvd, 4),
            "ob_imbalance": round(self.ob_imbalance, 4),
            "timestamp": self.last_update
        }

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
