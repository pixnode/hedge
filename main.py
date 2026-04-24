import asyncio
import logging
from config import config
from poly_feed import PolyWebsocketFeed
from executor import OrderExecutor
from temporal_engine import TemporalEngine
from ui import UI

# Disable basic logging output to not mess up the rich UI
logging.getLogger("poly_feed").setLevel(logging.ERROR)
logging.getLogger("executor").setLevel(logging.ERROR)
logging.getLogger("temporal_engine").setLevel(logging.ERROR)

async def main():
    queue = asyncio.Queue()
    
    feed = PolyWebsocketFeed(config.POLY_WS_URL, queue)
    executor = OrderExecutor(config)
    engine = TemporalEngine(queue, feed, executor)
    ui = UI(engine)

    # Start all concurrent tasks
    await asyncio.gather(
        feed.connect_and_listen(),
        engine.run(),
        ui.render_ui()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("ATS Shutting Down...")
