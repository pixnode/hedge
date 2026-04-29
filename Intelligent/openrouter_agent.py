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
        if not self.api_key:
            return {"confidence": 0.5, "reasoning": "API Key Missing", "decision": "WAIT"}

        prompt = f"""
        Analyze this BTC Polymarket context:
        - Binance CVD: {context_data.get('cvd')}
        - Order Book Imbalance: {context_data.get('ob_imbalance')}
        - Bullpen Sentiment: {context_data.get('bullpen_sentiment')}
        
        Provide:
        1. Confidence Score (0.0 to 1.0)
        2. Decision: ENTER, SKIP, or WAIT
        3. Brief reasoning (max 15 words)
        
        JSON ONLY:
        {{
            "confidence": float,
            "decision": "string",
            "reasoning": "string"
        }}
        """

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a professional trader."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"}
            }

            print(f"DEBUG: AI is thinking (Model: {self.model})...")
            response = requests.post(self.url, headers=headers, json=payload, timeout=60)
            result = response.json()
            
            if 'choices' not in result:
                print(f"DEBUG: AI Raw Error: {result}")
                return {"confidence": 0.5, "decision": "WAIT", "reasoning": "AI API Error"}

            content = result['choices'][0]['message']['content']
            print(f"DEBUG: AI Raw Content: {content[:200]}...")
            
            # Sanitizer: AI often wraps JSON in code blocks or thinking text
            temp_content = content
            if "```json" in temp_content:
                temp_content = temp_content.split("```json")[1].split("```")[0].strip()
            elif "```" in temp_content:
                temp_content = temp_content.split("```")[1].split("```")[0].strip()
            
            try:
                return json.loads(temp_content)
            except:
                # Last resort: try to find anything that looks like JSON
                import re
                match = re.search(r'\{.*\}', temp_content, re.DOTALL)
                if match:
                    return json.loads(match.group())
                raise
            
        except Exception as e:
            logger.error(f"AI Error: {e}")
            return {"confidence": 0.5, "decision": "WAIT", "reasoning": f"Error: {str(e)[:20]}"}
