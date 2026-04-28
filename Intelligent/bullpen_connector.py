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
        # Try absolute path first for VPS, then fallback to 'bullpen'
        vps_path = "/root/.bullpen/bin/bullpen"
        cmd_base = vps_path if os.path.exists(vps_path) else "bullpen"
        
        try:
            cmd = f"{cmd_base} polymarket data smart-money --output json"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                if "Login Required" in result.stderr:
                    logger.warning("Bullpen Login Required. Please run 'bullpen login' in terminal.")
                return None
            
            data = json.loads(result.stdout)
            return self._parse_sentiment(data)
            
        except FileNotFoundError:
            logger.error("Bullpen CLI not found. Please install it from https://cli.bullpen.fi/")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch Bullpen data: {e}")
            return None

    def _parse_sentiment(self, raw_data):
        """
        Parses raw Bullpen JSON into a simplified sentiment score (-1 to 1).
        Logic: Looks at top traders' net position in current BTC markets.
        """
        try:
            # Note: The exact JSON structure depends on the Bullpen CLI version.
            # We look for overall 'sentiment' or individual trader flows.
            
            sentiment_score = 0.0
            
            # Example logic (placeholder until actual JSON structure is confirmed):
            # If the CLI returns a list of trades:
            if isinstance(raw_data, list):
                up_flow = sum(1 for t in raw_data if "UP" in t.get("market", "").upper())
                down_flow = sum(1 for t in raw_data if "DOWN" in t.get("market", "").upper())
                
                total = up_flow + down_flow
                if total > 0:
                    sentiment_score = (up_flow - down_flow) / total
            
            # If the CLI returns a summary object:
            elif isinstance(raw_data, dict):
                sentiment_score = raw_data.get("sentiment_score", 0.0)
                
            return {
                "score": round(sentiment_score, 2),
                "raw": raw_data
            }
        except Exception as e:
            logger.error(f"Error parsing Bullpen sentiment: {e}")
            return {"score": 0.0, "raw": raw_data}

if __name__ == "__main__":
    # Test Bullpen CLI
    bp = BullpenConnector()
    signals = bp.get_smart_money_signals()
    if signals:
        print(f"Smart Money Sentiment: {signals['score']}")
        # print(f"Raw Data: {json.dumps(signals['raw'], indent=2)}")
    else:
        print("Bullpen CLI not found or returned error.")
