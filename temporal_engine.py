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
        self.has_up = False
        self.has_down = False
        
        self.t_minus = 0
        self.last_up_ask = 0.0
        self.last_down_ask = 0.0
        
        self.executions = []
        self.last_status_time = 0
        
    def log_exec(self, msg: str, detail: str = ""):
        # 1. UI Logging (Simplified for terminal display)
        ts_ui = time.strftime("%H:%M:%S")
        self.executions.append(f"[{ts_ui}] {msg}")
        if len(self.executions) > 10:
            self.executions.pop(0)
            
        # 2. Persistent File Logging (Rich context for auditing)
        try:
            ts_file = time.strftime("%Y-%m-%d %H:%M:%S")
            win_short = self.current_window_slug[-10:] if self.current_window_slug else "INIT"
            
            # Formulating the market state string
            sum_ask = round(self.last_up_ask + self.last_down_ask, 3)
            state = f"| {win_short} | T-{self.t_minus:03}s | U:{self.last_up_ask:.2f} D:{self.last_down_ask:.2f} Σ:{sum_ask:.2f}"
            
            full_msg = f"[{ts_file}] {state} | {msg}"
            if detail:
                full_msg += f" | {detail}"
                
            with open("ats_execution.log", "a", encoding="utf-8") as f:
                f.write(full_msg + "\n")
        except Exception:
            pass

    async def run(self):
        while True:
            current_epoch = int(time.time())
            new_window_start = current_epoch - (current_epoch % 300)
            
            if new_window_start != self.window_start_epoch:
                self.window_start_epoch = new_window_start
                self.current_window_slug = f"btc-updown-5m-{self.window_start_epoch}"
                
                # Reset inventory state
                self.has_up = False
                self.has_down = False
                self.executions.clear()
                self.log_exec(f"🔄 New Window: {self.current_window_slug}")
                
                # Fetch tokens for the new window
                try:
                    self.up_token, self.down_token = await asyncio.to_thread(fetch_token_ids_for_slug, self.current_window_slug)
                    self.log_exec(f"📡 Tokens Acquired -> UP: {self.up_token[:6]}..., DOWN: {self.down_token[:6]}...")
                    # Update WS Subscription
                    if hasattr(self.feed, 'update_subscription'):
                        await self.feed.update_subscription(self.up_token, self.down_token)
                except ValueError as ve:
                    self.log_exec(str(ve))
                    await asyncio.sleep(5)
                    continue
            
            # Calculate T-Remaining
            window_end = self.window_start_epoch + 300
            self.t_minus = window_end - current_epoch
            
            # Periodic Market Status Log (Every 30 seconds)
            if current_epoch - self.last_status_time >= 30:
                status_msg = f"HEARTBEAT: Monitoring window {self.current_window_slug}"
                self.log_exec(status_msg)
                self.last_status_time = current_epoch

            # Check the queue
            try:
                # Process all available events without blocking
                while True:
                    event: OrderBookEvent = self.queue.get_nowait()
                    self.last_up_ask = event.up_ask
                    self.last_down_ask = event.down_ask
                    
                    # The Hunter Logic
                    if config.GOLDEN_WINDOW_END_SEC <= self.t_minus <= config.GOLDEN_WINDOW_START_SEC:
                        
                        # Hedging Logic Evaluation - MUST be <= MAX_TOTAL_HEDGE_COST (Probabilities)
                        if (self.last_up_ask + self.last_down_ask) <= config.MAX_TOTAL_HEDGE_COST:
                        
                            # Check UP Sniper
                            if not self.has_up and self.last_up_ask <= config.TARGET_MAX_ODDS:
                                size = config.BASE_SHARES
                                self.log_exec(f"⚡ ORDER SENT: BUY {size} UP @ {self.last_up_ask}")
                                self.has_up = True # Optimistic lock
                                try:
                                    res = await self.executor.execute(self.up_token, "UP", self.last_up_ask, size, config)
                                    if res.get("status") == "FILLED":
                                        self.log_exec(f"✅ FILLED: UP @ {res.get('filled_price')} | Tx: {res.get('tx_hash')[:10]}...")
                                    else:
                                        self.has_up = False # Release lock if failed
                                        self.log_exec(f"❌ FAILED: UP Order Failed")
                                except Exception as e:
                                    self.log_exec(f"❌ ERROR: UP execute failed - {str(e)}")
                                    self.has_up = False

                            # Check DOWN Sniper
                            if not self.has_down and self.last_down_ask <= config.TARGET_MAX_ODDS:
                                size = config.BASE_SHARES
                                self.log_exec(f"⚡ ORDER SENT: BUY {size} DOWN @ {self.last_down_ask}")
                                self.has_down = True # Optimistic lock
                                try:
                                    res = await self.executor.execute(self.down_token, "DOWN", self.last_down_ask, size, config)
                                    if res.get("status") == "FILLED":
                                        self.log_exec(f"✅ FILLED: DOWN @ {res.get('filled_price')} | Tx: {res.get('tx_hash')[:10]}...")
                                    else:
                                        self.has_down = False
                                        self.log_exec(f"❌ FAILED: DOWN Order Failed")
                                except Exception as e:
                                    self.log_exec(f"❌ ERROR: DOWN execute failed - {str(e)}")
                                    self.has_down = False

            except asyncio.QueueEmpty:
                pass

            await asyncio.sleep(0.05) # Yield to event loop, 50ms tick
