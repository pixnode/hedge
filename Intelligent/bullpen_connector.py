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
        Executes Bullpen CLI with Dual-Fetch strategy:
        1. General Smart Money Stats
        2. Real-time Whale Feed
        """
        vps_path = "/root/.bullpen/bin/bullpen"
        cmd_base = vps_path if os.path.exists(vps_path) else "bullpen"
        
        results = {"stats": None, "trades": None}
        
        try:
            # Command 1: Smart Money Stats
            cmd_stats = f"{cmd_base} polymarket data smart-money --output json"
            res_stats = subprocess.run(cmd_stats, shell=True, capture_output=True, text=True, timeout=10)
            if res_stats.returncode == 0:
                results["stats"] = json.loads(res_stats.stdout)
                
            # Command 2: Whale Feed (Directional Action)
            # Fetching the last few large trades to see current flow
            cmd_trades = f"{cmd_base} polymarket feed trades --min-pnl 5000 --min-trade-size 500 --output json --limit 10"
            res_trades = subprocess.run(cmd_trades, shell=True, capture_output=True, text=True, timeout=10)
            if res_trades.returncode == 0:
                results["trades"] = json.loads(res_trades.stdout)
                
            return self._parse_advanced_sentiment(results)
            
        except Exception as e:
            logger.error(f"Failed to fetch Bullpen Dual-Fetch: {e}")
            return {"score": 0.0, "direction_score": 0.0, "raw": None}

    def _parse_advanced_sentiment(self, results):
        """
        Advanced Parser v3.0:
        Calculates direction_score from real-time trades and stats.
        """
        try:
            up_weight = 0.0
            down_weight = 0.0
            
            # 1. Parse Real-time Trades (High Priority)
            trades = results.get("trades") or []
            if isinstance(trades, dict) and "trades" in trades:
                trades = trades["trades"]
                
            for t in trades:
                side = str(t.get("side", "")).upper() # BUY/SELL
                outcome = str(t.get("outcome", "")).upper() # YES/NO
                amount = float(t.get("usd_size", 0) or 0)
                
                # Logic: If someone buys YES on a BTC-UP market, it's Bullish.
                # If they buy YES on a BTC-DOWN market, it's Bearish.
                market_name = str(t.get("market_name", "")).upper()
                
                is_bullish_action = False
                is_bearish_action = False
                
                if "UP" in market_name:
                    if side == "BUY": is_bullish_action = True
                    if side == "SELL": is_bearish_action = True
                elif "DOWN" in market_name:
                    if side == "BUY": is_bearish_action = True
                    if side == "SELL": is_bullish_action = True
                
                weight = 1.0 + (amount / 5000.0) # Larger trades carry more weight
                if is_bullish_action: up_weight += weight
                if is_bearish_action: down_weight += weight

            # 2. Parse General Stats (Secondary Priority)
            stats = results.get("stats", {})
            signals = stats.get("signals", []) if isinstance(stats, dict) else []
            for s in signals:
                text = (str(s.get("title", "")) + " " + str(s.get("summary", ""))).upper()
                if any(k in text for k in ["UP", "BULLISH", "LONG"]): up_weight += 0.5
                if any(k in text for k in ["DOWN", "BEARISH", "SHORT"]): down_weight += 0.5

            # 3. Calculate Directional Score (-1.0 to +1.0)
            total = up_weight + down_weight
            direction_score = 0.0
            if total > 0:
                direction_score = (up_weight - down_weight) / total
                
            return {
                "score": round(direction_score, 2), # This is our new direction_score
                "direction_score": round(direction_score, 2),
                "total_signals": total,
                "raw": results
            }
        except Exception as e:
            logger.error(f"Error in Advanced Bullpen Parser: {e}")
            return {"score": 0.0, "direction_score": 0.0, "raw": results}

if __name__ == "__main__":
    bp = BullpenConnector()
    data = bp.get_smart_money_signals()
    print(f"Bullpen Directional Score: {data['direction_score']}")
