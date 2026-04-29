import asyncio
import time
import random
import logging
import requests
import json
from datetime import datetime
from core.config import config

logger = logging.getLogger("temporal_engine")

class TemporalEngine:
    def __init__(self, queue: asyncio.Queue, feed, executor, gate=None, features=None):
        self.queue = queue
        self.feed = feed
        self.executor = executor
        self.gate = gate
        self.features = features
        
        self.current_window_slug = ""
        self.up_token = ""
        self.down_token = ""
        self.gate_decision = "WAIT"
        self.running = False

    def log_exec(self, msg):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    async def run(self):
        self.running = True
        self.log_exec("Temporal Engine Started.")
        
        while self.running:
            try:
                # 1. Sync with Market Windows
                now = time.time()
                window_duration = 300 # 5 minutes
                remaining = window_duration - (now % window_duration)
                
                # Update current window info
                current_ts = int(now - (now % window_duration))
                new_slug = f"btc-updown-5m-{current_ts}"
                
                if new_slug != self.current_window_slug:
                    self.current_window_slug = new_slug
                    self.log_exec(f"New Window: {new_slug}")
                    self.gate_decision = "WAIT"
                    # Discover tokens for new window
                    await self._discover_tokens(current_ts)
                
                t_minus = int(remaining)
                
                # 2. Intelligence Gate Check (T-25)
                if t_minus == 25 and self.gate and self.features:
                    features = self.features.get_snapshot(up_token=self.up_token, down_token=self.down_token)
                    decision, adj = await self.gate.evaluate_window(self.current_window_slug, features)
                    self.gate_decision = decision
                    self.log_exec(f"Gate Decision: {decision} (Adj: {adj})")

                # 3. Process Price Events
                try:
                    poll_timeout = 1.0
                    event = await asyncio.wait_for(self.queue.get(), timeout=poll_timeout)
                    
                    # Sample logging for verification
                    if random.random() < 0.05:
                        self.log_exec(f"🔔 Price Update: {event.asset_id[:6]}... Ask: {event.ask:.4f}")
                
                    # Update feature builder
                    if self.features:
                        self.features.update_from_event(event)
                        
                    # 4. Trading Logic (Executes if gate says ENTER)
                    if self.gate_decision == "ENTER" and t_minus > 10:
                        # Placeholder for pillar execution
                        pass
                        
                except asyncio.TimeoutError:
                    pass

                await asyncio.sleep(0.1)
                
            except Exception as e:
                self.log_exec(f"Engine Loop Error: {e}")
                await asyncio.sleep(1)

    async def _discover_tokens(self, timestamp):
        """
        Fetches the specific UP and DOWN token IDs for the current window from Polymarket.
        """
        try:
            # Placeholder for actual discovery logic
            # In production, this calls the Polymarket API to find tokens for the 'timestamp'
            self.log_exec(f"Discovering tokens for T={timestamp}...")
            # For now, we assume they are provided or discovered via feed
            pass
        except Exception as e:
            self.log_exec(f"Discovery Failed: {e}")

    async def send_telegram(self, msg):
        if not config.TELEGRAM_BOT_TOKEN: return
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": config.TELEGRAM_CHAT_ID, "text": msg}
        try:
            requests.post(url, json=payload, timeout=5)
        except: pass
