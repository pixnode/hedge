import asyncio
import time
import random
import logging
from dataclasses import dataclass
import temporal_engine
from temporal_engine import TemporalEngine, OrderBookEvent
from executor import OrderExecutor
from config import config

# Disable logs so console isn't flooded
logging.getLogger("temporal_engine").setLevel(logging.CRITICAL)

class MockExecutor(OrderExecutor):
    def __init__(self):
        super().__init__(config)
        self.trades = 0
        self.total_slippage = 0.0
    
    async def execute(self, token_id: str, side: str, current_ask: float, size: float, config_obj):
        await asyncio.sleep(0.001)  # Simulate network latency
        filled_price = current_ask # No slippage simulation as requested
        
        self.trades += 1
        
        return {
            "status": "FILLED",
            "filled_price": round(filled_price, 3),
            "tx_hash": f"mock_tx_{self.trades}"
        }

class MockFeed:
    async def update_subscription(self, up_token: str, down_token: str):
        pass

async def feed_simulator(queue: asyncio.Queue, engine: TemporalEngine):
    """Feeds artificial crossing data directly into the queue."""
    await asyncio.sleep(1) # Warm up delay
    while True:
        # Generate odds that sum to <= 0.90 to trigger Hedging Logic
        up = round(random.uniform(0.30, 0.45), 2)
        down = round(random.uniform(0.30, 0.45), 2)
        
        queue.put_nowait(OrderBookEvent(up_ask=up, down_ask=down, timestamp=time.time()))
        await asyncio.sleep(0.01) # Ultra fast tick rate

async def force_1000_trades(engine: TemporalEngine, executor: MockExecutor):
    start_time = time.time()
    
    while executor.trades < 1000:
        # Manually reset locks so the engine can continuously take trades within the same window
        if engine.has_up and engine.has_down:
            engine.has_up = False
            engine.has_down = False
            
        await asyncio.sleep(0.05)
        
    end_time = time.time()
    
    print("\n" + "="*45)
    print("BACKTEST PIPELINE SUMMARY")
    print("="*45)
    print(f"Total Executed Trades : {executor.trades}")
    print(f"Win Rate Assumption   : 50.0% (Fully Hedged Arb)")
    print(f"Execution Time        : {(end_time - start_time):.2f} seconds")
    print("="*45 + "\n")
    
    # Kill the process
    import os, sys
    sys.stdout.flush()
    os._exit(0)

async def main():
    queue = asyncio.Queue()
    mock_feed = MockFeed()
    mock_executor = MockExecutor()
    
    engine = TemporalEngine(queue, mock_feed, mock_executor)
    
    # Patch the fetcher to prevent exceptions from internet discovery
    temporal_engine.fetch_token_ids_for_slug = lambda slug: ("0x_MOCK_UP", "0x_MOCK_DOWN")

    print("Starting High-Speed Backtester. Targeting 1000 trades...", flush=True)

    await asyncio.gather(
        engine.run(),
        feed_simulator(queue, engine),
        force_1000_trades(engine, mock_executor)
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Backtest aborted.")
