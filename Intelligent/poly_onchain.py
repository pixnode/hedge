import requests
import logging
import time

logger = logging.getLogger("intelligent.onchain")

class PolyOnChain:
    def __init__(self):
        self.api_url = "https://clob.polymarket.com/trades"

    def get_directional_score(self, up_token_id, down_token_id):
        """
        Fetches last trades for both tokens and calculates a directional flow score.
        Score: -1.0 (Heavy Down Flow) to +1.0 (Heavy Up Flow)
        """
        try:
            up_vol = self._get_buy_volume(up_token_id)
            down_vol = self._get_buy_volume(down_token_id)
            
            total_vol = up_vol + down_vol
            if total_vol == 0:
                return 0.0
                
            # Score = (Buy pressure on UP - Buy pressure on DOWN) / Total
            score = (up_vol - down_vol) / total_vol
            return round(score, 2)
            
        except Exception as e:
            logger.error(f"On-Chain analysis failed: {e}")
            return 0.0

    def _get_buy_volume(self, asset_id):
        """
        Calculates the USD volume of BUY orders in the last few trades.
        """
        try:
            params = {"asset_id": asset_id}
            response = requests.get(self.api_url, params=params, timeout=10)
            if response.status_code != 200:
                return 0.0
            
            trades = response.json()
            if not isinstance(trades, list):
                return 0.0
            
            # Sum up the USD volume of 'buy' orders
            # buy side = pressure on that price
            buy_volume = 0.0
            for t in trades[:30]: # Look at last 30 trades
                if t.get("side") == "buy":
                    price = float(t.get("price", 0))
                    size = float(t.get("size", 0))
                    buy_volume += (price * size)
                    
            return buy_volume
        except:
            return 0.0

if __name__ == "__main__":
    # Test with specific IDs if available
    poc = PolyOnChain()
    # score = poc.get_directional_score("UP_ID", "DOWN_ID")
    # print(f"On-Chain Score: {score}")
    print("PolyOnChain Module Ready.")
