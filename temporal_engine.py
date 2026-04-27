import asyncio
import time
import logging
import requests
import json
import csv
import os
import datetime
from config import config
from poly_feed import PolyWebsocketFeed, OrderBookEvent
from executor import OrderExecutor

TRADE_CSV = "trades.csv"
TRADE_HEADERS = [
    "timestamp", "window_slug", "action", "side", "asset",
    "ref_price", "fill_price", "shares", "up_entry", "down_entry",
    "combined", "pnl", "status", "tx_hash", "mode"
]

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
        
        # Pre-emptive State
        self.next_up_token = None
        self.next_down_token = None
        self.next_window_slug = ""
        self.fetching_next = False
        
        self.last_window_tokens = None
        self.last_window_expiry = 0
        
        # Inventory State
        self.up_invested_usd = 0.0
        self.down_invested_usd = 0.0
        self.up_fill_price = 0.0
        self.down_fill_price = 0.0
        self.has_up = False
        self.has_down = False
        
        self.t_minus = 0
        self.last_up_ask = 0.0
        self.last_down_ask = 0.0
        self.last_up_bid = 0.0
        self.last_down_bid = 0.0
        
        # New 3-Pillar State
        self.window_active = True
        self.dead_zone_active = False
        self.leg1_price = 0.0
        self.dynamic_target = config.TARGET_MAX_ENTRY
        self.panic_mode = False
        
        self.executions = []
        self.last_status_time = 0

    def is_dead_zone(self) -> bool:
        """Check if current UTC hour falls within any configured dead zone."""
        dz = config.DEAD_ZONE_UTC.strip()
        if not dz:
            return False
        utc_hour = datetime.datetime.utcnow().hour
        for zone in dz.split(","):
            zone = zone.strip()
            if "-" not in zone:
                continue
            parts = zone.split("-")
            start_h = int(parts[0])
            end_h = int(parts[1])
            if start_h <= end_h:
                # Normal range e.g. 05-07
                if start_h <= utc_hour < end_h:
                    return True
            else:
                # Wraps midnight e.g. 20-00 means 20,21,22,23
                if utc_hour >= start_h or utc_hour < end_h:
                    return True
        return False

    def log_exec(self, msg: str, send_tele: bool = False):
        ts_ui = time.strftime("%H:%M:%S")
        self.executions.append(f"[{ts_ui}] {msg}")
        if len(self.executions) > 10:
            self.executions.pop(0)
            
        try:
            ts_file = time.strftime("%Y-%m-%d %H:%M:%S")
            with open("ats_execution.log", "a", encoding="utf-8") as f:
                f.write(f"[{ts_file}] {msg}\n")
        except Exception:
            pass
            
        if send_tele and config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
            asyncio.create_task(self.send_telegram(f"ATS Sniper: {msg}"))

    def write_trade_csv(self, row: dict):
        """Append a trade record to trades.csv. Auto-creates headers on first write."""
        file_exists = os.path.isfile(TRADE_CSV)
        try:
            with open(TRADE_CSV, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=TRADE_HEADERS)
                if not file_exists or os.path.getsize(TRADE_CSV) == 0:
                    writer.writeheader()
                mode = "PAPER" if config.PAPER_TRADING_MODE else "LIVE"
                row["mode"] = mode
                row["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                row["window_slug"] = self.current_window_slug
                writer.writerow(row)
        except Exception as e:
            logger.error(f"CSV write error: {e}")

    async def send_telegram(self, message: str):
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": config.TELEGRAM_CHAT_ID, "text": message}
        try:
            await asyncio.to_thread(requests.post, url, json=payload, timeout=5)
        except Exception as e:
            logger.error(f"Telegram Failed: {e}")

    async def preemptive_discovery(self, target_epoch: int):
        slug = f"btc-updown-5m-{target_epoch}"
        self.log_exec(f"🔍 [T-10] Starting Pre-emptive Discovery: {slug}")
        while time.time() < target_epoch:
            try:
                up, down = await asyncio.to_thread(fetch_token_ids_for_slug, slug)
                self.next_up_token = up
                self.next_down_token = down
                self.next_window_slug = slug
                self.log_exec(f"✅ Discovery Success: {up[:6]}... / {down[:6]}...")
                return
            except Exception:
                await asyncio.sleep(1)
        self.log_exec(f"⚠️ Discovery Timeout for {slug}")

    async def run(self):
        self.log_exec("🚀 ATS v1.0 Ultra-Safe Active")
        while True:
            try:
                now = time.time()
                current_epoch = int(now)
                
                window_start = current_epoch - (current_epoch % 300)
                next_window_start = window_start + 300
                
                # 1. T-10 PRE-EMPTIVE DISCOVERY
                if current_epoch >= next_window_start - 10 and not self.fetching_next:
                    self.fetching_next = True
                    asyncio.create_task(self.preemptive_discovery(next_window_start))

                # 2. T-0 WINDOW TRANSITION
                if window_start != self.window_start_epoch:
                    if self.up_token and self.down_token:
                        self.last_window_tokens = [self.up_token, self.down_token]
                        self.last_window_expiry = now + 5
                    
                    self.window_start_epoch = window_start
                    
                    if self.next_up_token and self.next_window_slug == f"btc-updown-5m-{window_start}":
                        self.up_token = self.next_up_token
                        self.down_token = self.next_down_token
                        self.current_window_slug = self.next_window_slug
                        self.next_up_token = None
                    else:
                        self.current_window_slug = f"btc-updown-5m-{self.window_start_epoch}"
                        try:
                            self.up_token, self.down_token = await asyncio.to_thread(fetch_token_ids_for_slug, self.current_window_slug)
                        except Exception as e:
                            self.log_exec(f"⚠️ Critical Transition Error: {e}")
                            await asyncio.sleep(1)
                            continue

                    # Reset State for New Window
                    self.up_invested_usd = 0.0
                    self.down_invested_usd = 0.0
                    self.up_fill_price = 0.0
                    self.down_fill_price = 0.0
                    self.has_up = False
                    self.has_down = False
                    self.window_active = True
                    self.leg1_price = 0.0
                    self.dynamic_target = config.TARGET_MAX_ENTRY
                    self.panic_mode = False
                    self.fetching_next = False
                    self.executions.clear()
                    self.log_exec(f"🔄 [T-0] Switch -> {self.current_window_slug}", send_tele=True)
                    
                    # Dead Zone Check
                    if self.is_dead_zone():
                        self.window_active = False
                        self.dead_zone_active = True
                        utc_h = datetime.datetime.utcnow().strftime("%H:%M UTC")
                        self.log_exec(f"💤 DEAD ZONE ({utc_h}) — Skipping window (low vol / thin liquidity)")
                        self.write_trade_csv({
                            "action": "DEAD_ZONE_SKIP", "side": "-", "asset": "-",
                            "ref_price": 0, "fill_price": 0, "shares": 0,
                            "up_entry": 0, "down_entry": 0,
                            "combined": 0, "pnl": 0, "status": "DEAD_ZONE", "tx_hash": "-"
                        })
                    else:
                        self.dead_zone_active = False
                    
                    sub_list = [self.up_token, self.down_token]
                    if self.last_window_tokens:
                        sub_list.extend(self.last_window_tokens)
                    await self.feed.update_subscription(sub_list)

                # 3. T+5 CLEANUP
                if self.last_window_expiry > 0 and now >= self.last_window_expiry:
                    self.log_exec(f"🧹 [T+5] Releasing old window context")
                    self.last_window_expiry = 0
                    self.last_window_tokens = None
                    await self.feed.update_subscription([self.up_token, self.down_token])

                # 4. Update T-Minus
                window_end = self.window_start_epoch + 300
                self.t_minus = window_end - current_epoch

                # 5. Process Data Events
                try:
                    event: OrderBookEvent = await asyncio.wait_for(self.queue.get(), timeout=0.1)
                    if event.asset_id == self.up_token:
                        self.last_up_ask = event.ask
                        self.last_up_bid = event.bid
                    elif event.asset_id == self.down_token:
                        self.last_down_ask = event.ask
                        self.last_down_bid = event.bid
                except asyncio.TimeoutError:
                    pass
                
                # 6. Ultra-Safe Logic (3 Pillars)
                if not self.window_active:
                    continue
                    
                # PILLAR 1: Skip Rule (T-N Check)
                if self.t_minus <= config.GOLDEN_WINDOW_END_SEC and not self.has_up and not self.has_down:
                    self.window_active = False
                    self.log_exec(f"⏭️ SKIP WINDOW: No entry hit <= {config.TARGET_MAX_ENTRY}")
                    self.write_trade_csv({
                        "action": "SKIP", "side": "-", "asset": "-",
                        "ref_price": 0, "fill_price": 0, "shares": 0,
                        "up_entry": self.last_up_ask, "down_entry": self.last_down_ask,
                        "combined": 0, "pnl": 0, "status": "SKIPPED", "tx_hash": "-"
                    })
                    continue

                # PILLAR 3: Emergency Exit (T-N Guard)
                if self.t_minus <= config.GOLDEN_WINDOW_END_SEC and (self.has_up ^ self.has_down) and not self.panic_mode:
                    self.panic_mode = True
                    self.log_exec("🚨 EMERGENCY EXIT TRIGGERED (T-20)")
                    
                    # Missing side logic
                    missing_side = "DOWN" if self.has_up else "UP"
                    missing_ask = self.last_down_ask if missing_side == "DOWN" else self.last_up_ask
                    missing_token = self.down_token if missing_side == "DOWN" else self.up_token
                    
                    # Filled side logic
                    filled_side = "UP" if self.has_up else "DOWN"
                    filled_bid = self.last_up_bid if filled_side == "UP" else self.last_down_bid
                    filled_token = self.up_token if filled_side == "UP" else self.down_token
                    
                    if 0 < missing_ask <= self.dynamic_target:
                        # Condition A: Force Buy (Hedge Completable)
                        self.log_exec(f"⚡ FORCE BUY: {missing_side} @ {missing_ask}")
                        asyncio.create_task(self.fire_order(missing_token, "BUY", missing_ask, config.BASE_TRADE_USD, missing_side))
                    else:
                        # Condition B: Panic Sell (Liquidate Leg 1)
                        self.log_exec(f"💥 PANIC SELL: Liquidation {filled_side} @ {filled_bid}")
                        asyncio.create_task(self.fire_order(filled_token, "SELL", filled_bid, config.BASE_TRADE_USD, filled_side))
                    continue

                # PILLAR 1 & 2: Normal Hunting (T > 20)
                if self.t_minus > 20 and not self.panic_mode:
                    tasks = []
                    
                    # If hunting for first leg OR second leg target met
                    up_target = config.TARGET_MAX_ENTRY if not self.has_down else self.dynamic_target
                    down_target = config.TARGET_MAX_ENTRY if not self.has_up else self.dynamic_target
                    
                    if not self.has_up and 0 < self.last_up_ask <= up_target:
                        self.has_up = True # Optimistic lock
                        tasks.append(self.fire_order(self.up_token, "BUY", self.last_up_ask, config.BASE_TRADE_USD, "UP"))
                        
                    if not self.has_down and 0 < self.last_down_ask <= down_target:
                        self.has_down = True # Optimistic lock
                        tasks.append(self.fire_order(self.down_token, "BUY", self.last_down_ask, config.BASE_TRADE_USD, "DOWN"))
                        
                    if tasks:
                        await asyncio.gather(*tasks)

            except Exception as e:
                logger.error(f"Engine Loop Error: {e}")
                await asyncio.sleep(1)

    async def fire_order(self, token, side, price, size, asset_name):
        self.log_exec(f"⚡ SEND: {side} {asset_name} Ref @ {price:.2f}")
        try:
            res = await self.executor.execute(token, side, price, size, config)
            if res.get("status") == "FILLED":
                filled = res.get("filled_price", price)
                tx_hash = res.get("tx_hash", "unknown")
                
                if side == "BUY":
                    if asset_name == "UP": 
                        self.up_invested_usd += (size * filled)
                        self.up_fill_price = filled
                    if asset_name == "DOWN": 
                        self.down_invested_usd += (size * filled)
                        self.down_fill_price = filled
                    
                    # Update dynamic target based on first leg
                    if self.leg1_price == 0.0:
                        self.leg1_price = filled
                        self.dynamic_target = config.MAX_HEDGE_COST - self.leg1_price
                        self.log_exec(f"🎯 DYNAMIC TARGET SET: Leg 2 must be <= {self.dynamic_target:.2f}")
                        
                    self.log_exec(f"✅ {asset_name} FILLED @ {filled:.2f} | Tx: {tx_hash[:8]}")
                    
                    # Log BUY to CSV
                    self.write_trade_csv({
                        "action": "BUY", "side": side, "asset": asset_name,
                        "ref_price": price, "fill_price": filled, "shares": size,
                        "up_entry": self.up_fill_price, "down_entry": self.down_fill_price,
                        "combined": 0, "pnl": 0, "status": "FILLED", "tx_hash": tx_hash
                    })
                    
                    # Trigger Cycle Done Report if Fully Hedged
                    if self.has_up and self.has_down:
                        await self.send_cycle_done_report()
                else:
                    # Panic Sell filled
                    panic_pnl = (filled - self.leg1_price) * size
                    self.log_exec(f"💸 {asset_name} SOLD (PANIC) @ {filled:.2f} | Tx: {tx_hash[:8]}")
                    
                    # Log PANIC SELL to CSV
                    self.write_trade_csv({
                        "action": "PANIC_SELL", "side": side, "asset": asset_name,
                        "ref_price": price, "fill_price": filled, "shares": size,
                        "up_entry": self.up_fill_price, "down_entry": self.down_fill_price,
                        "combined": 0, "pnl": round(panic_pnl, 4), "status": "PANIC_EXIT",
                        "tx_hash": tx_hash
                    })
                    
            else:
                # Reset lock if failed
                if side == "BUY":
                    if asset_name == "UP": self.has_up = False
                    if asset_name == "DOWN": self.has_down = False
                err = res.get('error', 'unknown')
                self.log_exec(f"❌ {asset_name} FAILED: {str(err)[:20]}")
                
                # Log FAILED to CSV
                self.write_trade_csv({
                    "action": f"{side}_FAILED", "side": side, "asset": asset_name,
                    "ref_price": price, "fill_price": 0, "shares": size,
                    "up_entry": 0, "down_entry": 0,
                    "combined": 0, "pnl": 0, "status": "FAILED",
                    "tx_hash": str(err)[:30]
                })
        except Exception as e:
            if side == "BUY":
                if asset_name == "UP": self.has_up = False
                if asset_name == "DOWN": self.has_down = False
            self.log_exec(f"❌ {asset_name} ERROR: {str(e)[:30]}")

    async def send_cycle_done_report(self):
        combined = self.up_fill_price + self.down_fill_price
        pnl_per_share = 1.0 - combined
        total_pnl = pnl_per_share * config.BASE_TRADE_USD
        
        dt = datetime.datetime.fromtimestamp(self.window_start_epoch)
        window_time_str = dt.strftime("%H:%M %b %d")
        
        # Log HEDGED completion to CSV
        self.write_trade_csv({
            "action": "CYCLE_DONE", "side": "-", "asset": "BOTH",
            "ref_price": 0, "fill_price": 0, "shares": config.BASE_TRADE_USD,
            "up_entry": self.up_fill_price, "down_entry": self.down_fill_price,
            "combined": round(combined, 4), "pnl": round(total_pnl, 4),
            "status": "HEDGED", "tx_hash": "-"
        })
        
        report = (
            f"\U0001f6e1\ufe0f ATS BTC5M : \U0001f4b0 Cycle Done\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\U0001f194 Window: {self.current_window_slug.split('-')[-1]} {window_time_str}\n"
            f"\U0001f4ca Entry UP : ${self.up_fill_price:.3f}\n"
            f"\U0001f4ca Entry DWN: ${self.down_fill_price:.3f}\n"
            f"\U0001f4b5 Combined : ${combined:.3f}\n"
            f"\U0001f4c8 Net P&L  : +${total_pnl:.2f}\n"
            f"\U0001f4e6 Shares   : {config.BASE_TRADE_USD}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        )
        self.log_exec(f"📋 Generating Final Report...")
        if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
            await self.send_telegram(report)
