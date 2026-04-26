import asyncio
import time
import logging
import requests
import json
from config import config
from poly_feed import PolyWebsocketFeed, OrderBookEvent
from executor import OrderExecutor

logger = logging.getLogger("temporal_engine")
logger.setLevel(logging.WARNING)

def fetch_token_ids_for_slug(slug: str):
    url = f"https://gamma-api.polymarket.com/events?slug={slug}"
    try:
        resp = requests.get(url, timeout=5).json()
        if resp and len(resp) > 0:
            markets = resp[0].get("markets", [])
            if markets and len(markets) > 0:
                tokens = markets[0].get("clobTokenIds", [])
                if tokens:
                    if isinstance(tokens, str):
                        try:
                            tokens = json.loads(tokens)
                        except:
                            pass
                    if isinstance(tokens, list) and len(tokens) >= 2:
                        return tokens[0], tokens[1]
    except Exception as e:
        logger.error(f"Failed to fetch tokens for slug {slug}: {e}")
    # CRITICAL FALLBACK FIX: Raise exception instead of returning mock tokens
    raise ValueError(f"CRITICAL: Token discovery failed for {slug}")

class TemporalEngine:
    def __init__(self, queue: asyncio.Queue, feed: PolyWebsocketFeed, executor: OrderExecutor):
        self.queue = queue
        self.feed = feed
        self.executor = executor
        
        self.current_window_slug = ""
        self.window_start_epoch = 0
        
        self.up_token = ""
        self.down_token = ""
        
        # Inventory State
        self.up_invested_usd = 0.0
        self.down_invested_usd = 0.0
        self.has_up = False
        self.has_down = False
        
        self.t_minus = 0
        self.last_up_ask = 0.0
        self.last_down_ask = 0.0
        
        self.executions = []
        self.last_status_time = 0
        
    def log_exec(self, msg: str, send_tele: bool = False):
        # 1. UI Logging (Time Only)
        ts_ui = time.strftime("%H:%M:%S")
        self.executions.append(f"[{ts_ui}] {msg}")
        if len(self.executions) > 10:
            self.executions.pop(0)
            
        # 2. Persistent File Logging (Date & Time)
        try:
            ts_file = time.strftime("%Y-%m-%d %H:%M:%S")
            with open("ats_execution.log", "a", encoding="utf-8") as f:
                f.write(f"[{ts_file}] {msg}\n")
        except Exception:
            pass
            
        # 3. Telegram Notification (Optional)
        if send_tele and config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
            asyncio.create_task(self.send_telegram(f"🎯 ATS Sniper: {msg}"))

    async def send_telegram(self, message: str):
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": config.TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        try:
            await asyncio.to_thread(requests.post, url, json=payload, timeout=5)
        except Exception as e:
            logger.error(f"Telegram Failed: {e}")

    async def run(self):
        self.log_exec("🚀 Warrior Engine Active - Listening for Events...")
        while True:
            try:
                # 1. Wait for data event (Zero Latency)
                event: OrderBookEvent = await self.queue.get()
                current_epoch = int(time.time())
                
                # 2. Window Management Logic
                new_window_start = current_epoch - (current_epoch % 300)
                if new_window_start != self.window_start_epoch:
                    self.window_start_epoch = new_window_start
                    self.current_window_slug = f"btc-updown-5m-{self.window_start_epoch}"
                    self.up_invested_usd = 0.0
                    self.down_invested_usd = 0.0
                    self.has_up = False
                    self.has_down = False
                    self.executions.clear()
                    self.log_exec(f"🔄 New Window: {self.current_window_slug}", send_tele=True)
                    
                    try:
                        self.up_token, self.down_token = await asyncio.to_thread(fetch_token_ids_for_slug, self.current_window_slug)
                        self.log_exec(f"📡 Tokens -> UP: {self.up_token[:6]}, DOWN: {self.down_token[:6]}")
                        if hasattr(self.feed, 'update_subscription'):
                            await self.feed.update_subscription(self.up_token, self.down_token)
                    except Exception as e:
                        self.log_exec(f"⚠️ Token Error: {e}")
                        continue

                # 3. Temporal State
                window_end = self.window_start_epoch + 300
                self.t_minus = window_end - current_epoch
                self.last_up_ask = event.up_ask
                self.last_down_ask = event.down_ask
                total_cost = self.last_up_ask + self.last_down_ask

                # 4. Diagnostic Heartbeat (Every 5 seconds in Sniping Zone)
                if config.GOLDEN_WINDOW_END_SEC <= self.t_minus <= config.GOLDEN_WINDOW_START_SEC:
                    if current_epoch - self.last_status_time >= 5:
                        self.last_status_time = current_epoch
                        status_msg = f"🔍 SCAN: UP={self.last_up_ask:.2f} | DN={self.last_down_ask:.2f} | SUM={total_cost:.2f} | T-{self.t_minus}s"
                        self.log_exec(status_msg)

                # 5. THE WARRIOR SNIPER LOGIC (Scenario B: Directional Sniper)
                if config.GOLDEN_WINDOW_END_SEC <= self.t_minus <= config.GOLDEN_WINDOW_START_SEC:
                    
                    tasks = []
                    
                    # Check UP Sniper - Independent Evaluation
                    if not self.has_up and self.last_up_ask <= config.TARGET_MAX_ODDS and self.last_up_ask > 0:
                        size = config.BASE_SHARE
                        if (self.up_invested_usd + (size * self.last_up_ask)) <= config.MAX_POSITION_USD:
                            self.has_up = True # Optimistic lock
                            tasks.append(self.fire_order(self.up_token, "UP", self.last_up_ask, size))

                    # Check DOWN Sniper - Independent Evaluation
                    if not self.has_down and self.last_down_ask <= config.TARGET_MAX_ODDS and self.last_down_ask > 0:
                        size = config.BASE_SHARE
                        if (self.down_invested_usd + (size * self.last_down_ask)) <= config.MAX_POSITION_USD:
                            self.has_down = True # Optimistic lock
                            tasks.append(self.fire_order(self.down_token, "DOWN", self.last_down_ask, size))

                    # FIRE CONCURRENTLY
                    if tasks:
                        asyncio.gather(*tasks)

            except Exception as e:
                logger.error(f"Engine Loop Error: {e}")
                await asyncio.sleep(1)

    async def fire_order(self, token, side, price, size):
        self.log_exec(f"⚡ SNIPER FIRE: BUY {side} @ {price}")
        try:
            res = await self.executor.execute(token, side, price, size, config)
            if res.get("status") == "FILLED":
                filled = res.get("filled_price", price)
                if side == "UP":
                    self.up_invested_usd += (size * filled)
                else:
                    self.down_invested_usd += (size * filled)
                self.log_exec(f"✅ {side} FILLED @ {filled} | Tx: {res.get('tx_hash')[:8]}", send_tele=True)
            else:
                # Reset lock if failed
                if side == "UP": self.has_up = False
                else: self.has_down = False
                self.log_exec(f"❌ {side} FAILED: {res.get('error')[:20]}")
        except Exception as e:
            if side == "UP": self.has_up = False
            else: self.has_down = False
            self.log_exec(f"❌ {side} ERROR: {str(e)[:30]}")

