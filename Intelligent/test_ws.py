import asyncio
import json
import websockets
import time

async def test_polymarket_ws():
    # THE CORRECT DOMAIN FOUND IN CONFIG
    url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    test_token_id = "21742468351821030310237512140417242111166052067160216140502013023345100000000"

    formats = [
        {"name": "V3 Official (assets_ids)", "payload": {"type": "market", "assets_ids": [test_token_id]}},
        {"name": "Standard (asset_ids)", "payload": {"type": "market", "asset_ids": [test_token_id]}},
        {"name": "New Subscribe", "payload": {"type": "subscribe", "assets_ids": [test_token_id]}},
    ]

    print(f"--- WebSocket Diagnostics v3 ---")
    print(f"Target URL: {url}\n")

    for fmt in formats:
        print(f"Testing {fmt['name']}...")
        try:
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps(fmt['payload']))
                
                start_time = time.time()
                while time.time() - start_time < 3:
                    try:
                        resp = await asyncio.wait_for(ws.recv(), timeout=1.5)
                        print(f"    [SUCCESS] Received: {resp[:100]}...")
                        if "INVALID OPERATION" not in resp and "error" not in resp.lower():
                            print(f"    ⭐ VALID FORMAT FOUND: {fmt['name']}")
                            return
                    except asyncio.TimeoutError:
                        break
        except Exception as e:
            print(f"    [ERROR] {e}")
        print("-" * 30)

if __name__ == "__main__":
    asyncio.run(test_polymarket_ws())
