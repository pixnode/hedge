import subprocess
import json
import logging
import os
import time

logger = logging.getLogger("intelligent.bullpen")

class BullpenConnector:
    def __init__(self, cli_path="bullpen"):
        self.cli_path = cli_path

    def get_smart_money_signals(self):
        vps_path = "/root/.bullpen/bin/bullpen"
        cmd_base = vps_path if os.path.exists(vps_path) else "bullpen"
        
        try:
            # Command v7.0: Requesting raw trades snapshot with PnL filter
            # This ensures we get real action, not just ranking stats.
            cmd = f"{cmd_base} polymarket data trades --min-pnl 1000 --limit 50 --output json"
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            
            if res.returncode != 0:
                return {"score": 0.0, "direction_score": 0.0, "raw": None}
            
            raw_output = res.stdout.strip()
            # EMERGENCY DUMP
            with open("debug_bullpen_raw.txt", "w") as f:
                f.write(raw_output)
                
            if not raw_output:
                return {"score": 0.0, "direction_score": 0.0, "raw": None}
                
            data = json.loads(raw_output)
            return self._parse_v7_realtime(data)
            
        except Exception as e:
            logger.error(f"Failed to fetch Bullpen v7: {e}")
            return {"score": 0.0, "direction_score": 0.0, "raw": None}

    def _parse_v7_realtime(self, data):
        """
        Parser v7.0: Filters trades from the last 5 minutes and calculates direction.
        """
        try:
            up_votes = 0
            down_votes = 0
            now = time.time()
            
            # Data can be a list or a dict containing a list
            trades = data.get("trades", []) if isinstance(data, dict) else data
            if not isinstance(trades, list):
                return {"score": 0.0, "direction_score": 0.0}

            for t in trades:
                # 1. Time Filter: Only last 5 minutes (300s)
                trade_ts = t.get("timestamp", 0)
                if trade_ts > 0 and (now - trade_ts) > 300:
                    continue
                
                market = str(t.get("market_name", "")).upper()
                side = str(t.get("side", "")).upper()
                outcome = str(t.get("outcome", "")).upper()
                
                # We only care about BTC markets for this bot
                if "BTC" not in market:
                    continue

                is_up = False
                is_down = False
                
                # Standard Directional Logic
                if "UP" in market:
                    if (side == "BUY" and outcome == "YES") or (side == "SELL" and outcome == "NO"): is_up = True
                    if (side == "BUY" and outcome == "NO") or (side == "SELL" and outcome == "YES"): is_down = True
                elif "DOWN" in market:
                    if (side == "BUY" and outcome == "YES") or (side == "SELL" and outcome == "NO"): is_down = True
                    if (side == "BUY" and outcome == "NO") or (side == "SELL" and outcome == "YES"): is_up = True
                
                if is_up: up_votes += 1
                if is_down: down_votes += 1

            total = up_votes + down_votes
            direction_score = 0.0
            if total > 0:
                direction_score = (up_votes - down_votes) / total
                
            return {
                "score": round(direction_score, 2),
                "direction_score": round(direction_score, 2),
                "total_recent_trades": total,
                "raw": data
            }
        except Exception as e:
            logger.error(f"Error in Bullpen v7 Parser: {e}")
            return {"score": 0.0, "direction_score": 0.0, "raw": data}
