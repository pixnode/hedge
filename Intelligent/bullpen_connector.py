import subprocess
import json
import logging
import os

logger = logging.getLogger("intelligent.bullpen")

class BullpenConnector:
    def __init__(self, cli_path="bullpen"):
        self.cli_path = cli_path

    def get_smart_money_signals(self):
        """
        Executes Bullpen CLI to fetch smart money flow for Polymarket.
        """
        vps_path = "/root/.bullpen/bin/bullpen"
        cmd_base = vps_path if os.path.exists(vps_path) else "bullpen"
        
        try:
            # Added timeout to prevent hanging
            cmd = f"{cmd_base} polymarket data smart-money --output json"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            
            if result.returncode != 0:
                return None
            
            data = json.loads(result.stdout)
            # Log raw data summary
            print(f"DEBUG: Bullpen Raw Data received ({len(str(data))} bytes)")
            return self._parse_sentiment(data)
            
        except Exception as e:
            logger.error(f"Failed to fetch Bullpen data: {e}")
            return None

    def _parse_sentiment(self, raw_data):
        """
        Parses raw Bullpen JSON into a simplified sentiment score (-1 to 1).
        Verified for Bullpen CLI v1.2+ JSON structure.
        """
        try:
            sentiment_score = 0.0
            signals = []
            
            if isinstance(raw_data, dict) and "signals" in raw_data:
                signals = raw_data["signals"]
            elif isinstance(raw_data, list):
                signals = raw_data
            
            if not signals:
                return {"score": 0.0, "raw": raw_data}
            
            up_weight = 0
            down_weight = 0
            
            for s in signals:
                title = s.get("title", "")
                text = (str(title) + " " + str(s.get("summary", ""))).upper()
                side = str(s.get("side", "") or "").upper()
                
                print(f"DEBUG: Bullpen Signal Found: {title}")
                
                # Logic: Find bullish/bearish indicators with expanded keyword list
                is_up = any(k in text for k in ["UP", "BULLISH", "LONG", "BUY", "BTC-UP", "BITCOIN-UP"]) or side == "BUY"
                is_down = any(k in text for k in ["DOWN", "BEARISH", "SHORT", "SELL", "BTC-DOWN", "BITCOIN-DOWN"]) or side == "SELL"
                
                # Weighting: You can increase weight based on volume in text if available
                if is_up: up_weight += 1
                if is_down: down_weight += 1
            
            total = up_weight + down_weight
            if total > 0:
                sentiment_score = (up_weight - down_weight) / total
                
            return {
                "score": round(sentiment_score, 2),
                "count": total,
                "raw": raw_data
            }
        except Exception as e:
            logger.error(f"Error parsing Bullpen sentiment: {e}")
            return {"score": 0.0, "raw": raw_data}

if __name__ == "__main__":
    bp = BullpenConnector()
    signals = bp.get_smart_money_signals()
    if signals:
        print(f"Smart Money Score: {signals['score']} (Based on {signals.get('count', 0)} signals)")
    else:
        print("Bullpen CLI not found or empty.")
