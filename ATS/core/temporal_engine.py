import asyncio
import time
import random
import logging
import requests
import json
import csv
import os
import datetime
from .config import config
from .poly_feed import PolyWebsocketFeed, OrderBookEvent
from .executor import OrderExecutor

# Path for Intelligent Department access
import sys
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

try:
    from Intelligent.gate import IntelligentGate
except ImportError:
    IntelligentGate = None

TRADE_CSV = "logs/trades.csv"
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
                        return tokens[0], tokens[1], markets[0].get("id")
    except Exception as e:
        logger.error(f"Failed to fetch tokens for slug {slug}: {e}")
    return None, None, None

class TemporalEngine:
    def __init__(self, queue: asyncio.Queue, feed: PolyWebsocketFeed, executor: OrderExecutor):
        self.queue = queue
        self.feed = feed
        self.executor = executor
        self.gate = IntelligentGate() if IntelligentGate else None
        
        # Paper Account State
        self.paper_balance = config.INITIAL_PAPER_BALANCE
        print(f"💰 PAPER WALLET INITIALIZED: ${self.paper_balance:.2f}")
        
        print(f"DEBUG: Intelligent Gate Initialized: {self.gate is not None}")
        if self.gate is None:
            print("DEBUG: IntelligentGate is None. Check imports or gate.py syntax.")
        
        self.current_window_slug = ""
        self.window_start_epoch = 0
        self.current_window_expiry = 0
        
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
        
        # ATS v2.0 State
        self.window_active = True
        self.dead_zone_active = False
        self.leg1_price = 0.0
        self.dynamic_target = config.TARGET_MAX_ENTRY
        self.panic_mode = False
        
        self.pillar1_open = False
        self.pillar1_expired = False
        self.gate_consulted_epoch = 0 # Track which epoch we consulted for
        self.pillar1_got_one = False
        self.overlap_zone_active = False
        self.panic_bid_tracked = 0.0
        
        self.executions = []
        self.last_status_time = 0
        
        # Ensure log directory exists
        os.makedirs("logs", exist_ok=True)

    def is_dead_zone(self) -> bool:
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
                if start_h <= utc_hour < end_h:
                    return True
            else:
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
            with open("logs/ats_execution.log", "a", encoding="utf-8") as f:
                f.write(f"[{ts_file}] {msg}\n")
        except Exception:
            pass
            
        if send_tele and config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
            try:
                asyncio.create_task(self.send_telegram(f"ATS Sniper: {msg}"))
            except RuntimeError:
                pass # Event loop closed during shutdown

    def write_trade_csv(self, row: dict):
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
        self.log_exec(f"🔍 [T-{config.PREFETCH_SEC}] Starting Pre-emptive Discovery: {slug}")
        while time.time() < target_epoch:
            try:
                up, down, m_id = await asyncio.to_thread(fetch_token_ids_for_slug, slug)
                self.next_up_token = up
                self.next_down_token = down
                self.next_market_id = m_id
                self.next_window_slug = slug
                self.log_exec(f"✅ Discovery Success: {up[:6]}... / {down[:6]}...")
                return
            except Exception:
                await asyncio.sleep(1)
        self.log_exec(f"⚠️ Discovery Timeout for {slug}")

    async def run(self):
        self.log_exec("🚀 ATS v2.0 Ultra-Safe Active")
        while True:
            try:
                now = time.time()
                current_epoch = int(now)
                
                # Standard window calculations
                # expiry_0: Window yang baru saja berakhir (atau sedang berakhir)
                expiry_0 = current_epoch - (current_epoch % 300)
                # expiry_1: Window yang sedang aktif (akan berakhir dalam 0-300 detik)
                expiry_1 = expiry_0 + 300
                # expiry_2: Window berikutnya (untuk Sniper P1)
                expiry_2 = expiry_0 + 600
                
                # 1. PRE-FETCH DISCOVERY
                # Gunakan target_epoch yang unik agar tidak trigger berulang kali untuk epoch yang sama
                if current_epoch >= expiry_1 - config.PREFETCH_SEC and self.next_window_slug != f"btc-updown-5m-{expiry_2}" and not self.fetching_next:
                    self.fetching_next = True
                    asyncio.create_task(self.preemptive_discovery(expiry_2))

                # 2. WINDOW TRANSITION (Shifted to T-10)
                # Jika sudah masuk 10 detik terakhir window curr (expiry_1), 
                # maka kita harus sudah fokus ke window next (expiry_2)
                active_target_epoch = expiry_2 if current_epoch >= expiry_1 - config.P1_SNIPER_OPEN_SEC else expiry_1
                
                # 2.1 INTELLIGENT GATE CHECK (T-25 before window shift)
                # If we are approaching a new window and haven't asked the gate yet
                if self.gate and self.gate_consulted_epoch != active_target_epoch and 20 <= (active_target_epoch - current_epoch) <= 30:
                    self.gate_consulted_epoch = active_target_epoch
                    
                    # Capture Binance Features from the Gate's own FeatureBuilder
                    features = self.gate.feature_builder.get_snapshot()
                    
                    # Async task to not block the loop
                    asyncio.create_task(self._consult_gate(f"btc-updown-5m-{active_target_epoch}", features))

                if active_target_epoch != self.window_start_epoch:
                    if self.up_token and self.down_token:
                        self.last_window_tokens = [self.up_token, self.down_token]
                        self.last_window_expiry = now + 15 # Keep old tokens alive a bit longer for P3 panic
                    
                    self.window_start_epoch = active_target_epoch
                    
                    if self.next_up_token and self.next_window_slug == f"btc-updown-5m-{active_target_epoch}":
                        self.up_token = self.next_up_token
                        self.down_token = self.next_down_token
                        self.current_window_slug = self.next_window_slug
                        self.next_up_token = None
                    else:
                        self.current_window_slug = f"btc-updown-5m-{active_target_epoch}"
                        try:
                            up, down, m_id = await asyncio.to_thread(fetch_token_ids_for_slug, self.current_window_slug)
                            if up and down:
                                self.up_token = up
                                self.down_token = down
                                self.market_id = m_id
                                self.log_exec(f"💎 Tokens Found: {up[:8]}... / {down[:8]}...")
                            else:
                                self.log_exec(f"⚠️ Discovery Gap: {self.current_window_slug} not ready. Skipping.")
                                self.window_active = False
                                continue
                        except Exception as e:
                            self.log_exec(f"⚠️ Critical Transition Error: {e}")
                            await asyncio.sleep(1)
                            continue

                    self.window_start_epoch = active_target_epoch # This is actually Expiry Epoch
                    self.current_window_expiry = active_target_epoch

                    # Reset ATS v2.0 State
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
                    self.pillar1_open = False # Start closed until T-10
                    self.pillar1_expired = False
                    self.pillar1_got_one = False
                    self.overlap_zone_active = False
                    # JANGAN reset fetching_next di sini, biarkan dia tetap True sampai window benar-akan berakhir
                    self.executions.clear()
                    
                    self.log_exec(f"🔄 Switch -> {self.current_window_slug} [Pillar 1 Sniper Armed]", send_tele=True)
                    
                    if self.is_dead_zone():
                        self.window_active = False
                        self.dead_zone_active = True
                        utc_h = datetime.datetime.utcnow().strftime("%H:%M UTC")
                        self.log_exec(f"💤 DEAD ZONE ({utc_h}) — Skipping window")
                        self.write_trade_csv({
                            "action": "DEAD_ZONE_SKIP", "side": "-", "asset": "-",
                            "ref_price": 0, "fill_price": 0, "shares": 0,
                            "up_entry": 0, "down_entry": 0,
                            "combined": 0, "pnl": 0, "status": "DEAD_ZONE", "tx_hash": "-"
                        })
                    else:
                        self.dead_zone_active = False
                    
                    sub_list = [self.up_token, self.down_token]
                    await self.feed.update_subscription(sub_list)

                # 3. CLEANUP OLD WINDOW
                if self.last_window_expiry > 0 and now >= self.last_window_expiry:
                    self.log_exec(f"🧹 Releasing old window context")
                    self.last_window_expiry = 0
                    self.last_window_tokens = None
                    await self.feed.update_subscription([self.up_token, self.down_token])

                # 4. UPDATE TIMERS (Precision Refactor)
                self.t_minus = self.current_window_expiry - current_epoch
                # window_duration_passed = 300 - t_minus (since t_minus is time to end)
                # For Pillar 1 Sniper (T-10 prev to T+10 curr), we check if t_minus is between 310 and 290
                # But to keep it simple, we use seconds_into_window:
                seconds_into_window = 300 - self.t_minus 
                # If t_minus > 300, it means we are in the pre-start (Sniper) phase of the new window
                if self.t_minus > 300:
                    seconds_into_window = -(self.t_minus - 300)

                # ATS v2.0 State Transitions
                if self.window_active:
                    # PILLAR 1: SNIPER (OPEN)
                    if not self.pillar1_open and not self.pillar1_expired and seconds_into_window >= -config.P1_SNIPER_OPEN_SEC:
                        if config.PAPER_TRADING_MODE and self.paper_balance < config.BASE_TRADE_USD:
                            self.log_exec(f"⚠️ INSUFFICIENT PAPER BALANCE: ${self.paper_balance:.2f} < ${config.BASE_TRADE_USD}. Skipping.")
                            self.window_active = False
                            continue
                            
                        self.pillar1_open = True
                        self.log_exec(f"🎯 PILLAR 1 SNIPER ACTIVE: Targeting {config.BASE_TRADE_USD} shares each")

                    # Pillar 1 Expiration (T+10)
                    if self.pillar1_open and seconds_into_window > config.P1_SNIPER_CLOSE_SEC:
                        self.pillar1_open = False
                        self.pillar1_expired = True
                        if self.has_up and self.has_down:
                            self.log_exec("🏁 P1 Result: HEDGED. Skipping P2.")
                        elif self.has_up ^ self.has_down:
                            self.pillar1_got_one = True
                            # Initialize Base Target with full buffers (Slippage + Relaxation)
                            # This ensures that even after full relaxation, we don't cross MAX_HEDGE_COST
                            total_relax_buffer = config.P2_RELAX_LATE + config.P2_RELAX_CRITICAL
                            self.dynamic_target = config.MAX_HEDGE_COST - self.leg1_price - config.P2_SLIPPAGE - total_relax_buffer
                            self.log_exec(f"🏁 P1 Result: 1 Leg Filled. Pillar 2 Hard Target: {self.dynamic_target:.3f} (Buffers: Slip={config.P2_SLIPPAGE}, Relax={total_relax_buffer})")
                        else:
                            self.window_active = False
                            self.log_exec(f"⏭️ SKIP WINDOW: 0 Legs filled in P1. Disarming.")
                            self.write_trade_csv({
                                "action": "SKIP", "side": "-", "asset": "-",
                                "ref_price": 0, "fill_price": 0, "shares": 0,
                                "up_entry": self.last_up_ask, "down_entry": self.last_down_ask,
                                "combined": 0, "pnl": 0, "status": "SKIPPED", "tx_hash": "-"
                            })
                            continue
                            
                    # Overlap Zone Activation (T-25)
                    if self.t_minus <= config.OVERLAP_ZONE_SEC and not self.overlap_zone_active and self.pillar1_got_one and not (self.has_up and self.has_down):
                        self.overlap_zone_active = True
                        self.log_exec(f"⚠️ OVERLAP ZONE ACTIVE (T-{config.OVERLAP_ZONE_SEC}): Pre-arming Panic Logic")

                # 5. PROCESS DATA EVENTS
                poll_timeout = 0.1
                # Tight loop for Pillar 2 if close to target
                if self.window_active and self.pillar1_got_one and not (self.has_up and self.has_down) and not self.overlap_zone_active:
                    missing_ask = self.last_down_ask if self.has_up else self.last_up_ask
                    if 0 < missing_ask <= self.dynamic_target + config.P2_PROXIMITY_ALERT:
                        poll_timeout = config.P2_POLL_INTERVAL

                try:
                    event = await asyncio.wait_for(self.queue.get(), timeout=poll_timeout)
                    # Sample logging for verification
                    if random.random() < 0.05:
                        self.log_exec(f"🔔 Price Update: {event.asset_id[:6]}... Ask: {event.ask:.4f}")
                
                    # Update current view
                    if event.asset_id == self.up_token:
                        self.last_up_ask = event.ask
                        self.last_up_bid = event.bid
                    elif event.asset_id == self.down_token:
                        self.last_down_ask = event.ask
                        self.last_down_bid = event.bid
                except asyncio.TimeoutError:
                    pass

                # 6. ATS v2.0 PILLARS EXECUTION LOGIC
                if not self.window_active:
                    continue
                    
                # Evaluate Panic Bid Tracking in Overlap Zone
                if self.overlap_zone_active:
                    filled_bid = self.last_up_bid if self.has_up else self.last_down_bid
                    self.panic_bid_tracked = filled_bid
                    
                # PILLAR 3: Emergency Exit (T-20 Guard)
                if self.t_minus <= config.GOLDEN_WINDOW_END_SEC and (self.has_up ^ self.has_down) and not self.panic_mode:
                    self.panic_mode = True
                    self.log_exec(f"🚨 PILLAR 3 EMERGENCY TRIGGERED (T-{self.t_minus})")
                    
                    missing_side = "DOWN" if self.has_up else "UP"
                    missing_ask = self.last_down_ask if missing_side == "DOWN" else self.last_up_ask
                    missing_token = self.down_token if missing_side == "DOWN" else self.up_token
                    
                    filled_side = "UP" if self.has_up else "DOWN"
                    filled_bid = self.last_up_bid if filled_side == "UP" else self.last_down_bid
                    filled_token = self.up_token if filled_side == "UP" else self.down_token
                    
                    # Final check: can we fill Leg 2 and stay under MAX_HEDGE_COST?
                    # Limit is MAX_HEDGE_COST - leg1 - expected_slippage
                    hard_limit_search = config.MAX_HEDGE_COST - self.leg1_price - config.P2_SLIPPAGE
                    if 0 < missing_ask <= hard_limit_search + 0.005: # Tiny 0.5 cent margin for emergency
                        self.log_exec(f"⚡ P3 LATE HEDGE BUY: {missing_side} @ {missing_ask}")
                        asyncio.create_task(self.fire_order(missing_token, "BUY", missing_ask, config.BASE_TRADE_USD, missing_side, slippage=config.P2_SLIPPAGE))
                    else:
                        if self.panic_bid_tracked < config.BID_FLOOR_THRESHOLD:
                            self.log_exec(f"🛑 LIQUIDITY_VACUUM_DETECTED: Panic bid {self.panic_bid_tracked} < {config.BID_FLOOR_THRESHOLD}. Letting expire.")
                        else:
                            self.log_exec(f"💥 PANIC SELL: Liquidation {filled_side} @ {self.panic_bid_tracked}")
                            asyncio.create_task(self.fire_order(filled_token, "SELL", self.panic_bid_tracked, config.BASE_TRADE_USD, filled_side))
                    continue

                # PILLAR 1 & 2: Hunting (T > 20)
                if self.t_minus > config.GOLDEN_WINDOW_END_SEC and not self.panic_mode:
                    tasks = []
                    
                    if self.pillar1_open:
                        # PILLAR 1 Logic: strict target, no relaxation
                        if not self.has_up and 0 < self.last_up_ask <= config.TARGET_MAX_ENTRY:
                            self.has_up = True
                            tasks.append(self.fire_order(self.up_token, "BUY", self.last_up_ask, config.BASE_TRADE_USD, "UP", slippage=config.ABSOLUTE_SLIPPAGE))
                        if not self.has_down and 0 < self.last_down_ask <= config.TARGET_MAX_ENTRY:
                            self.has_down = True
                            tasks.append(self.fire_order(self.down_token, "BUY", self.last_down_ask, config.BASE_TRADE_USD, "DOWN", slippage=config.ABSOLUTE_SLIPPAGE))
                    elif self.pillar1_got_one:
                        # PILLAR 2 Logic: Dynamic relaxation
                        current_dynamic_target = self.dynamic_target
                        # Phase 1: Relax by P2_RELAX_LATE
                        if self.t_minus <= config.P2_RELAX_LATE_SEC and self.t_minus > config.P2_RELAX_CRITICAL_SEC:
                            current_dynamic_target += config.P2_RELAX_LATE
                        # Phase 2: Relax by P2_RELAX_LATE + P2_RELAX_CRITICAL (fully relaxed)
                        elif self.t_minus <= config.P2_RELAX_CRITICAL_SEC:
                            current_dynamic_target += (config.P2_RELAX_LATE + config.P2_RELAX_CRITICAL)
                            
                        # Only hunt for the missing leg
                        if not self.has_up and 0 < self.last_up_ask <= current_dynamic_target:
                            self.has_up = True
                            tasks.append(self.fire_order(self.up_token, "BUY", self.last_up_ask, config.BASE_TRADE_USD, "UP", slippage=config.P2_SLIPPAGE))
                        if not self.has_down and 0 < self.last_down_ask <= current_dynamic_target:
                            self.has_down = True
                            tasks.append(self.fire_order(self.down_token, "BUY", self.last_down_ask, config.BASE_TRADE_USD, "DOWN", slippage=config.P2_SLIPPAGE))
                            
                    if tasks:
                        await asyncio.gather(*tasks)

            except Exception as e:
                logger.error(f"Engine Loop Error: {e}")
                await asyncio.sleep(1)

    async def fire_order(self, token, side, price, size, asset_name, slippage=None):
        self.log_exec(f"⚡ SEND: {side} {asset_name} Ref @ {price:.2f}")
        try:
            res = await self.executor.execute(token, side, price, size, config, slippage=slippage)
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
                    
                    if self.leg1_price == 0.0:
                        self.leg1_price = filled
                        # Initial calculation for the first time it hits (redundant but safe)
                        total_relax_buffer = config.P2_RELAX_LATE + config.P2_RELAX_CRITICAL
                        self.dynamic_target = config.MAX_HEDGE_COST - self.leg1_price - config.P2_SLIPPAGE - total_relax_buffer
                        self.log_exec(f"🎯 HARD CEILING ARMED: Base Search Target <= {self.dynamic_target:.3f}")
                        
                    self.log_exec(f"✅ {asset_name} FILLED @ {filled:.2f} | Tx: {tx_hash[:8]}")
                    
                    self.write_trade_csv({
                        "action": "BUY", "side": side, "asset": asset_name,
                        "ref_price": price, "fill_price": filled, "shares": size,
                        "up_entry": self.up_fill_price, "down_entry": self.down_fill_price,
                        "combined": 0, "pnl": 0, "status": "FILLED", "tx_hash": tx_hash
                    })
                    
                    if self.has_up and self.has_down:
                        await self.send_cycle_done_report()
                else:
                    panic_pnl = (filled - self.leg1_price) * size
                    self.log_exec(f"💸 {asset_name} SOLD (PANIC) @ {filled:.2f} | Tx: {tx_hash[:8]}")
                    
                    self.write_trade_csv({
                        "action": "PANIC_SELL", "side": side, "asset": asset_name,
                        "ref_price": price, "fill_price": filled, "shares": size,
                        "up_entry": self.up_fill_price, "down_entry": self.down_fill_price,
                        "combined": 0, "pnl": round(panic_pnl, 4), "status": "PANIC_EXIT",
                        "tx_hash": tx_hash
                    })
                    
            else:
                if side == "BUY":
                    if asset_name == "UP": self.has_up = False
                    if asset_name == "DOWN": self.has_down = False
                err = res.get('error', 'unknown')
                self.log_exec(f"❌ {asset_name} FAILED: {str(err)[:50]}")
                
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
        total_pnl = (pnl_per_share * config.BASE_TRADE_USD) - (config.BASE_TRADE_USD * 2 * 0.01) # Minus roughly 1% execution tax mock
        
        # Update Paper Balance
        if config.PAPER_TRADING_MODE:
            self.paper_balance += total_pnl
            self.log_exec(f"💰 PAPER BALANCE UPDATED: ${self.paper_balance:.2f} (PnL: {total_pnl:+.3f})")

        dt = datetime.datetime.fromtimestamp(self.window_start_epoch)
        window_time_str = dt.strftime("%H:%M %b %d")
        
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
            
    async def _consult_gate(self, window_id: str, features: dict):
        if not self.gate: return
        
        decision, adj = await self.gate.evaluate_window(window_id, features)
        self.log_exec(f"\U0001f9e0 Intelligent Gate Decision: {decision} (Adj: {adj})")
        
        if decision == "SKIP":
            self.window_active = False
            self.log_exec(f"🛑 GATE REJECTED Window {window_id}. Disarming.")
        elif decision == "WAIT":
            # In WAIT mode, we might push the Sniper start time or be more selective
            self.dynamic_target -= 0.05 # Be very stingy in WAIT mode
            self.log_exec(f"⏳ GATE suggests WAIT. Tightening target by 0.05.")
        
        if adj != 0:
            self.dynamic_target += adj
            
    def report_outcome_to_memory(self, window_id: str, outcome_data: dict):
        """Bridge to send results back to Intelligent department."""
        if self.gate:
            self.gate.memory.update_outcome(window_id, outcome_data)
