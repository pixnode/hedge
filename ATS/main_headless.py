"""
ATS v1.0 Headless Mode — For PM2 / Background Daemon
Runs the engine and WebSocket feed without the Rich UI.
Use this when deploying via PM2 where no interactive terminal is available.
"""
import asyncio
import logging
from core.config import config
from core.poly_feed import PolyWebsocketFeed
from core.executor import OrderExecutor
from core.temporal_engine import TemporalEngine

# Setup basic logging to stdout for PM2 log capture
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)

async def main():
    queue = asyncio.Queue()
    
    feed = PolyWebsocketFeed(config.POLY_WS_URL, queue)
    executor = OrderExecutor(config)
    engine = TemporalEngine(queue, feed, executor)

    print(f"[ATS] Headless mode started (PAPER={config.PAPER_TRADING_MODE})")
    print(f"[ATS] Entry Target: {config.TARGET_MAX_ENTRY} | Max Cost: {config.MAX_HEDGE_COST} | Slippage: {config.ABSOLUTE_SLIPPAGE}")
    print(f"[ATS] Shares: {config.BASE_TRADE_USD} | Panic: T-{config.GOLDEN_WINDOW_END_SEC}s")
    print(f"[ATS] Trade log: trades.csv | Exec log: ats_execution.log")
    print(f"[ATS] Waiting for first window...", flush=True)

    await asyncio.gather(
        feed.connect_and_listen(),
        engine.run()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[ATS] Shutting down...")
