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
        
        Provide JSON ONLY:
        {{
            "confidence": float,
            "decision": "ENTER/SKIP/WAIT",
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
                    {"role": "system", "content": "You are a quant trader. Output JSON only."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"}
            }

            print(f"DEBUG: AI is thinking (Model: {self.model})...")
            response = requests.post(self.url, headers=headers, json=payload, timeout=90)
            result = response.json()
            
            if 'choices' not in result:
                print(f"DEBUG: AI API Error: {result}")
                return {"confidence": 0.5, "decision": "WAIT", "reasoning": "API Error"}

            raw_content = result['choices'][0]['message']['content']
            
            # --- EKSTRAKSI JSON BRUTAL (AKAR MASALAH 0.00) ---
            # Cari blok JSON di antara { dan }
            clean_json = raw_content
            match = re.search(r'(\{.*\})', raw_content, re.DOTALL)
            if match:
                clean_json = match.group(1)
            
            # Bersihkan karakter kontrol atau sisa-sisa markdown
            clean_json = clean_json.replace("```json", "").replace("```", "").strip()
            
            parsed = json.loads(clean_json)
            
            # Pastikan nilai confidence adalah float dan tidak 0 jika tidak seharusnya
            confidence = parsed.get("confidence", 0.5)
            if isinstance(confidence, str):
                confidence = float(confidence)
            
            return parsed
            
        except Exception as e:
            logger.error(f"AI Parse Error: {e} | Raw: {raw_content[:100] if 'raw_content' in locals() else 'None'}")
            return {"confidence": 0.5, "decision": "WAIT", "reasoning": "Parse Error"}
