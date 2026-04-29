import requests
import json
import logging
import time

logger = logging.getLogger("intelligent.onchain")

class PolyOnChain:
    def __init__(self):
        self.endpoint = "https://gamma-api.polymarket.com/query"

    def get_active_btc_condition(self):
        """
        Finds the current active BTC 5m market condition_id.
        """
        query = """
        query Markets($search: String) {
            markets(
                where: { 
                    active: true, 
                    closed: False,
                    groupItemTitle_contains: "Bitcoin",
                    question_contains: "5m"
                }
                orderBy: endDate
                orderDirection: asc
                first: 1
            ) {
                conditionId
                question
                slug
            }
        }
        """
        try:
            response = requests.post(self.endpoint, json={'query': query}, timeout=10)
            if response.status_code != 200:
                print(f"DEBUG: Gamma API HTTP Error {response.status_code}")
                return None, None
                
            res_json = response.json()
            data = res_json.get("data", {}).get("markets", [])
            if data:
                return data[0]["conditionId"], data[0]["question"]
            return None, None
        except Exception as e:
            print(f"DEBUG: Gamma API Request Failed: {e}")
            return None, None

    def get_onchain_direction_score(self, min_size=500):
        """
        Calculates (Volume_YES - Volume_NO) / Total from real-time on-chain trades.
        """
        condition_id, question = self.get_active_btc_condition()
        if not condition_id:
            return 0.0, "No Active Market Found"

        query = """
        query MarketTrades($conditionId: String!, $minSize: Float!) {
            trades(
                where: { 
                    conditionId: $conditionId, 
                    usdSize_gt: $minSize 
                }
                orderBy: timestamp
                orderDirection: desc
                first: 30
            ) {
                side
                outcome
                usdSize
            }
        }
        """
        variables = {"conditionId": condition_id, "minSize": min_size}

        try:
            response = requests.post(self.endpoint, json={'query': query, 'variables': variables}, timeout=10)
            trades = response.json().get("data", {}).get("trades", [])
            
            if not trades:
                return 0.0, f"No Whale Trades (> ${min_size}) on {question}"

            yes_vol = 0.0
            no_vol = 0.0

            for t in trades:
                side = t.get("side") # BUY/SELL
                outcome = t.get("outcome") # "0" is YES, "1" is NO
                size = float(t.get("usdSize", 0))

                if side == "BUY":
                    if outcome == "0": yes_vol += size # Buy YES
                    else: no_vol += size # Buy NO
                else:
                    if outcome == "0": no_vol += size # Sell YES (Bearish)
                    else: yes_vol += size # Sell NO (Bullish)

            total = yes_vol + no_vol
            if total > 0:
                score = (yes_vol - no_vol) / total
                return round(score, 2), f"Analyzed ${total:,.0f} Whale Volume on {question}"
            
            return 0.0, "Zero Whale Volume"

        except Exception as e:
            logger.error(f"On-Chain Error: {e}")
            return 0.0, "API Error"

if __name__ == "__main__":
    poc = PolyOnChain()
    score, msg = poc.get_onchain_direction_score()
    print(f"Score: {score} | {msg}")
