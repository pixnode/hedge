import requests
import json
import logging
import os
import re

logger = logging.getLogger("intelligent.openrouter")

class OpenRouterAgent:
    def __init__(self, api_key=None, model=None):
        env_path = os.path.join(os.path.dirname(__file__), "config.env")
        self.config = self._load_env(env_path)
        
        self.api_key = api_key or self.config.get("OPENROUTER_API_KEY")
        # Prioritize: 1. Passed model argument, 2. config.env, 3. global fallback
        self.model = model or self.config.get("OPENROUTER_MODEL_GATE") or self.config.get("OPENROUTER_MODEL", "moonshotai/kimi-k2.5:nitro")
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

    def ask_ai(self, prompt: str):
        """General purpose AI query."""
        if not self.api_key:
            return {"error": "API Key Missing"}

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/pixnode/hedge",
                "X-Title": "ATS v3.0 Intelligent Department"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a quant trading expert. Output JSON only."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": float(self.config.get("AI_TEMPERATURE", 0.1)),
                "top_p": float(self.config.get("AI_TOP_P", 0.9)),
                "max_tokens": int(self.config.get("AI_MAX_TOKENS", 1000))
            }

            print(f"DEBUG: AI is thinking (Model: {self.model})...")
            response = requests.post(self.url, headers=headers, json=payload, timeout=90)
            result = response.json()
            
            if 'choices' not in result:
                print(f"DEBUG: AI API Error: {result}")
                return {"error": "API Error"}

            raw_content = result['choices'][0]['message']['content']
            if not raw_content:
                return {"error": "Empty AI Response"}
            
            # Brutal JSON Extraction
            clean_json = raw_content
            match = re.search(r'(\{.*\})', raw_content, re.DOTALL)
            if match:
                clean_json = match.group(1)
            
            clean_json = clean_json.replace("```json", "").replace("```", "").strip()
            
            try:
                return json.loads(clean_json)
            except json.JSONDecodeError as je:
                # Attempt last-resort repair for common "unterminated string" or truncated JSON
                if "Unterminated string" in str(je) or "Expecting value" in str(je):
                    # Try to force-close any open strings or brackets
                    repaired = clean_json.strip()
                    if not repaired.endswith("}"): repaired += '"}' if '"' in repaired else "}"
                    try:
                        return json.loads(repaired)
                    except:
                        pass
                
                logger.error(f"AI JSON Parse Failed: {je} | Raw Snippet: {clean_json[:100]}")
                # Return a safe fallback based on keywords if JSON fails
                return {
                    "confidence": 0.5,
                    "decision": "SKIP" if "SKIP" in clean_json.upper() else "WAIT",
                    "reasoning": "AI format error, using keyword fallback."
                }

        except Exception as e:
            logger.error(f"AI Query Failed: {e}")
            return {"error": str(e)}

    def analyze_market_context(self, context_data: dict):
        prompt = f"""
        Analyze this BTC Polymarket context:
        - Binance CVD: {context_data.get('cvd')}
        - Order Book Imbalance: {context_data.get('ob_imbalance')}
        - ML Prediction Score (LightGBM): {context_data.get('ml_prediction_score')}
        - Bullpen Sentiment: {context_data.get('bullpen_sentiment')}
        
        Provide JSON ONLY. The 'reasoning' field MUST NOT be empty.
        {{
            "confidence": float (0.0 to 1.0),
            "decision": "ENTER/SKIP/WAIT",
            "reasoning": "A concise 1-sentence explanation of the primary driver."
        }}
        """
        return self.ask_ai(prompt)
