import requests
import json
import logging
import os

logger = logging.getLogger("intelligent.openrouter")

class OpenRouterAgent:
    def __init__(self, api_key=None, model=None):
        # Load from Intelligent/config.env
        env_path = os.path.join(os.path.dirname(__file__), "config.env")
        self.config = self._load_env(env_path)
        
        self.api_key = api_key or self.config.get("OPENROUTER_API_KEY")
        self.model = model or self.config.get("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
        self.url = "https://openrouter.ai/api/v1/chat/completions"

    def _load_env(self, path):
        config = {}
        if os.path.exists(path):
            with open(path, "r") as f:
                for line in f:
                    if "=" in line and not line.startswith("#"):
                        k, v = line.strip().split("=", 1)
                        config[k] = v
        return config

    def analyze_market_context(self, context_data: dict):
        """
        Sends market context to LLM for reasoning and confidence scoring.
        Context includes: Binance Metrics, Bullpen Sentiment, News Impact.
        """
        if not self.api_key:
            logger.error("OpenRouter API Key missing.")
            return {"confidence": 0.5, "reasoning": "API Key Missing", "decision": "WAIT"}

        prompt = f"""
        Analyze the following BTC5M Polymarket context and provide a trade decision.
        
        DATA CONTEXT:
        - Binance CVD: {context_data.get('cvd')}
        - Order Book Imbalance: {context_data.get('ob_imbalance')}
        - Bullpen Smart Money Score: {context_data.get('bullpen_score')} (-1 to 1)
        - News Sentiment: {context_data.get('news_impact')} (-1 to 1)
        
        TASK:
        1. Evaluate if the conditions are stable for a HEDGE entry (Arbitrage).
        2. Provide a Confidence Score (0.0 to 1.0).
        3. Provide a Decision: ENTER, SKIP, or WAIT.
        4. Brief reasoning (max 20 words).
        
        OUTPUT FORMAT (JSON ONLY):
        {{
            "confidence": float,
            "decision": "ENTER/SKIP/WAIT",
            "direction": "UP/DOWN/NONE",
            "reasoning": "string"
        }}
        """

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/pixnode/hedge",
                "X-Title": "ATS v3.0 Intelligent Gate"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a Senior Quant Trader AI."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"}
            }

            print(f"DEBUG: AI is thinking (Model: {self.model})...")
            response = requests.post(self.url, headers=headers, json=payload, timeout=120)
            result = response.json()
            
            if 'error' in result:
                logger.error(f"OpenRouter API Error: {result['error']}")
                return {"confidence": 0.5, "reasoning": f"AI Error: {result['error'].get('message', 'Unknown')}", "decision": "WAIT"}

            content = result['choices'][0]['message']['content']
            return json.loads(content)
            
        except Exception as e:
            logger.error(f"OpenRouter Request Failed: {e}")
            return {"confidence": 0.5, "reasoning": f"LLM Error: {str(e)[:30]}", "decision": "WAIT"}

if __name__ == "__main__":
    # Test with dummy data
    agent = OpenRouterAgent(api_key="sk-or-...") # Replace with real key for manual test
    dummy_context = {
        "cvd": 1500.5,
        "ob_imbalance": 0.25,
        "bullpen_score": 0.8,
        "news_impact": 0.1
    }
    # result = agent.analyze_market_context(dummy_context)
    # print(json.dumps(result, indent=2))
    print("OpenRouter Agent Ready.")
