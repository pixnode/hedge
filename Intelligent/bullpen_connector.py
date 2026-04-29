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
        
        results = {"stats": None, "trades": None}
        
        try:
            # Command 1: Smart Money Stats (for Convergence)
            cmd_stats = f"{cmd_base} polymarket data smart-money --output json"
            res_stats = subprocess.run(cmd_stats, shell=True, capture_output=True, text=True, timeout=10)
            if res_stats.returncode == 0:
                results["stats"] = json.loads(res_stats.stdout)
                
            # Command 2: Whale Feed (for Directional Action)
            cmd_trades = f"{cmd_base} polymarket feed trades --limit 15 --output json"
            res_trades = subprocess.run(cmd_trades, shell=True, capture_output=True, text=True, timeout=10)
            if res_trades.returncode == 0:
                results["trades"] = json.loads(res_trades.stdout)
                
            return self._parse_advanced_v4(results)
            
        except Exception as e:
            logger.error(f"Failed to fetch Bullpen v4: {e}")
            return {"score": 0.0, "direction_score": 0.0, "raw": None}

    def _parse_advanced_v4(self, results):
        try:
            up_votes = 0
            down_votes = 0
            
            # 1. Parse Trades (Looking for YES/NO and BUY/SELL)
            trades_data = results.get("trades") or []
            # Bullpen sometimes wraps list in a dict
            trades = trades_data.get("trades", []) if isinstance(trades_data, dict) else trades_data
                
            for t in trades:
                side = str(t.get("side", "") or t.get("action", "")).upper()
                outcome = str(t.get("outcome", "")).upper()
                market = str(t.get("market_name", "") or t.get("title", "")).upper()
                
                # Logic:
                # Buying YES on UP-market = Bullish
                # Buying NO on UP-market = Bearish
                # Buying YES on DOWN-market = Bearish
                # Buying NO on DOWN-market = Bullish
                
                is_bullish = False
                is_bearish = False
                
                if "UP" in market:
                    if (side == "BUY" and outcome == "YES") or (side == "SELL" and outcome == "NO"): is_bullish = True
                    if (side == "BUY" and outcome == "NO") or (side == "SELL" and outcome == "YES"): is_bearish = True
                elif "DOWN" in market:
                    if (side == "BUY" and outcome == "YES") or (side == "SELL" and outcome == "NO"): is_bearish = True
                    if (side == "BUY" and outcome == "NO") or (side == "SELL" and outcome == "YES"): is_bullish = True
                
                if is_bullish: up_votes += 1
                if is_bearish: down_votes += 1

            # 2. Parse Signals (Convergence)
            stats = results.get("stats") or {}
            signals = stats.get("signals", []) if isinstance(stats, dict) else []
            for s in signals:
                text = (str(s.get("title", "")) + " " + str(s.get("summary", ""))).upper()
                if "CONVERGENCE" in text or "SHARP TRADERS" in text:
                    if any(k in text for k in ["UP", "BULLISH", "YES"]): up_votes += 2 # Stronger weight
                    if any(k in text for k in ["DOWN", "BEARISH", "NO"]): down_votes += 2

            # 3. Calculate Directional Score
            total = up_votes + down_votes
            direction_score = 0.0
            if total > 0:
                direction_score = (up_votes - down_votes) / total
                
            return {
                "score": round(direction_score, 2),
                "direction_score": round(direction_score, 2),
                "total_votes": total,
                "raw": results
            }
        except Exception as e:
            logger.error(f"Error in Bullpen v4 Parser: {e}")
            return {"score": 0.0, "direction_score": 0.0, "raw": results}
