import asyncio
import json
import websockets
import time

async def test_polymarket_ws():
    # Trying different URLs and Channel-based formats
    urls = ["wss://clob.polymarket.com/ws/market", "wss://clob.polymarket.com/ws"]
    test_market_id = "0x2723326162130233451000000000000000000000000000000000000000000000" # Dummy Hex
    test_token_id = "21742468351821030310237512140417242111166052067160216140502013023345100000000"

    formats = [
        {"name": "Channel Market (Token)", "payload": {"type": "subscribe", "channel": "market", "assets_ids": [test_token_id]}},
        {"name": "Channel Market (MarketID)", "payload": {"type": "subscribe", "channel": "market", "market_ids": [test_market_id]}},
        {"name": "Direct Market Type", "payload": {"type": "market", "assets_ids": [test_token_id]}},
    ]

    print(f"--- WebSocket Diagnostics v2 ---")

    for url in urls:
        print(f"\nTarget URL: {url}")
        for fmt in formats:
            print(f"  Testing {fmt['name']}...")
            try:
                async with websockets.connect(url) as ws:
                    await ws.send(json.dumps(fmt['payload']))
                    
                    start_time = time.time()
                    while time.time() - start_time < 2:
                        try:
                            resp = await asyncio.wait_for(ws.recv(), timeout=1.0)
                            print(f"    [SUCCESS] Received: {resp[:100]}...")
                            if "INVALID OPERATION" not in resp and "error" not in resp.lower():
                                print(f"    ⭐ VALID COMBINATION FOUND!")
                                print(f"    URL: {url}")
                                print(f"    Format: {fmt['name']}")
                                return
                        except asyncio.TimeoutError:
                            break
            except Exception as e:
                print(f"    [ERROR] {e}")
        print("-" * 30)

if __name__ == "__main__":
    asyncio.run(test_polymarket_ws())
