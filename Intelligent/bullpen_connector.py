import subprocess
import json
import logging
import os

logger = logging.getLogger("intelligent.bullpen")

class BullpenConnector:
    def __init__(self, cli_path="bullpen"):
        self.cli_path = cli_path

    def get_smart_money_signals(self):
        vps_path = "/root/.bullpen/bin/bullpen"
        cmd_base = vps_path if os.path.exists(vps_path) else "bullpen"
        
        results = {"stats": None}
        
        try:
            # Command: General Smart-Money flow (Collective Sentiment)
            cmd = f"{cmd_base} polymarket data smart-money --output json"
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            
            if res.returncode != 0:
                print(f"DEBUG: Bullpen CLI Error: {res.stderr[:100]}")
                return {"score": 0.0, "direction_score": 0.0, "raw": None}
            
            raw_output = res.stdout.strip()
            # EMERGENCY DUMP: Save to file for manual inspection
            with open("debug_bullpen_raw.txt", "w") as f:
                f.write(raw_output)
                
            if not raw_output:
                return {"score": 0.0, "direction_score": 0.0, "raw": None}
                
            data = json.loads(raw_output)
            print(f"DEBUG: Bullpen Snapshot Received ({len(raw_output)} bytes)")
            return self._parse_v5_snapshot(data)
            
        except Exception as e:
            logger.error(f"Failed to fetch Bullpen v5: {e}")
            return {"score": 0.0, "direction_score": 0.0, "raw": None}

    def _parse_v5_snapshot(self, data):
        """
        Parser v5.0: Focuses on signals and trader outcomes from the snapshot.
        """
        try:
            up_votes = 0
            down_votes = 0
            
            # The 'signals' list is the gold mine for directional flow
            signals = data.get("signals", []) if isinstance(data, dict) else []
            
            if not signals:
                # If no signals, look at the general summary if available
                summary = str(data.get("summary", "")).upper()
                if any(k in summary for k in ["BULLISH", "BUYING", "LONG"]): up_votes += 1
                if any(k in summary for k in ["BEARISH", "SELLING", "SHORT"]): down_votes += 1
            
            if signals:
                first_sig = signals[0]
                print(f"DEBUG: First Bullpen Signal: {first_sig.get('title', 'No Title')} | {first_sig.get('summary', 'No Summary')[:50]}...")

            for s in signals:
                title = str(s.get("title", "")).upper()
                summary = str(s.get("summary", "")).upper()
                side = str(s.get("side", "") or "").upper()
                outcome = str(s.get("outcome", "") or "").upper()
                text = title + " " + summary
                
                # Logic v6.0: Extremely inclusive
                is_up = any(k in text for k in ["UP", "BULLISH", "LONG", "YES", "BUY"]) or (side == "BUY" and outcome == "YES")
                is_down = any(k in text for k in ["DOWN", "BEARISH", "SHORT", "NO", "SELL"]) or (side == "BUY" and outcome == "NO")
                
                if is_up: up_votes += 1
                if is_down: down_votes += 1
                
                # Extra weight for clear directional keywords
                if "BULLISH" in text or "LONG" in text: up_votes += 1
                if "BEARISH" in text or "SHORT" in text: down_votes += 1

            total = up_votes + down_votes
            direction_score = 0.0
            if total > 0:
                direction_score = (up_votes - down_votes) / total
                
            return {
                "score": round(direction_score, 2),
                "direction_score": round(direction_score, 2),
                "total_votes": total,
                "raw": data
            }
        except Exception as e:
            logger.error(f"Error in Bullpen v5 Parser: {e}")
            return {"score": 0.0, "direction_score": 0.0, "raw": data}
