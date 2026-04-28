import asyncio
import json
import websockets
import time

async def test_polymarket_ws():
    # We will try the 3 most common formats to see which one works
    url = "wss://clob.polymarket.com/ws/market"
    test_tokens = ["21742468351821030310237512140417242111166052067160216140502013023345100000000"] # Example BTC Token
    
    formats = [
        {"name": "V3 Official", "payload": {"type": "market", "assets_ids": test_tokens}},
        {"name": "Standard Subscribe", "payload": {"type": "subscribe", "assets_ids": test_tokens}},
        {"name": "Legacy", "payload": {"type": "market", "asset_ids": test_tokens}},
    ]

    print(f"--- WebSocket Diagnostics ---")
    print(f"Target URL: {url}\n")

    for fmt in formats:
        print(f"Testing {fmt['name']} format...")
        try:
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps(fmt['payload']))
                
                # Wait for 3 seconds to see responses
                start_time = time.time()
                while time.time() - start_time < 3:
                    try:
                        resp = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        print(f"  [SUCCESS] Received: {resp[:100]}...")
                        if "INVALID OPERATION" not in resp:
                            print(f"  ⭐ VALID FORMAT FOUND: {fmt['name']}")
                            return
                    except asyncio.TimeoutError:
                        break
        except Exception as e:
            print(f"  [ERROR] {e}")
        print("-" * 30)

if __name__ == "__main__":
    asyncio.run(test_polymarket_ws())
