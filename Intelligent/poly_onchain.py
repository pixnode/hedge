import requests
import json
import logging
import time

logger = logging.getLogger("intelligent.onchain")

class PolyOnChain:
    def __init__(self):
        self.endpoint = "https://gamma-api.polymarket.com/query"

    def get_whale_direction_score(self, condition_id, min_size=500):
        """
        Queries Polymarket Gamma API for recent whale trades on a specific condition.
        Calculates a Directional Score based on (Buy_YES - Buy_NO) / Total.
        """
        query = """
        query MarketTrades($conditionId: String!, $minSize: Float!) {
            trades(
                where: { 
                    conditionId: $conditionId, 
                    usdSize_gt: $minSize 
                }
                orderBy: timestamp
                orderDirection: desc
                first: 20
            ) {
                side
                outcome
                usdSize
                timestamp
            }
        }
        """
        variables = {
            "conditionId": condition_id,
            "minSize": min_size
        }

        try:
            response = requests.post(self.endpoint, json={'query': query, 'variables': variables}, timeout=10)
            if response.status_code != 200:
                return 0.0

            data = response.json().get("data", {}).get("trades", [])
            if not data:
                return 0.0

            up_vol = 0.0
            down_vol = 0.0

            for t in data:
                side = t.get("side") # BUY/SELL
                outcome = t.get("outcome") # "0" for YES, "1" for NO (usually)
                size = float(t.get("usdSize", 0))

                # Logic: We assume outcome "0" is UP/YES and "1" is DOWN/NO
                # In BTC-UP market: Buying YES (0) is Bullish.
                # In BTC-DOWN market: Buying YES (0) is Bearish.
                # This needs to be calibrated per market.
                
                if outcome == "0": # YES
                    if side == "BUY": up_vol += size
                    else: down_vol += size
                else: # NO
                    if side == "BUY": down_vol += size
                    else: up_vol += size

            total = up_vol + down_vol
            if total > 0:
                score = (up_vol - down_vol) / total
                return round(score, 2)
            
            return 0.0

        except Exception as e:
            logger.error(f"Failed to fetch On-Chain data: {e}")
            return 0.0

if __name__ == "__main__":
    # Test with a known condition_id
    poc = PolyOnChain()
    # Example condition_id
    score = poc.get_whale_direction_score("0x...") 
    print(f"On-Chain Whale Score: {score}")
