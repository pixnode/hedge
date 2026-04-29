import os
import json
import logging
import requests
import asyncio
from dotenv import load_dotenv
from .memory import PoolMemory
from .bullpen_connector import BullpenConnector
from .openrouter_agent import OpenRouterAgent
from .memory import PoolMemory
from .bullpen_connector import BullpenConnector
from .openrouter_agent import OpenRouterAgent
from .model_lgbm import IntelligentModel
from .feature_builder import FeatureBuilder

logger = logging.getLogger("intelligent.gate")

class IntelligentGate:
    def __init__(self):
        self.memory = PoolMemory()
        self.bullpen = BullpenConnector()
        self.ml_model = IntelligentModel()
        self.feature_builder = FeatureBuilder()
        
        # Start Feature Builder in background
        asyncio.create_task(self.feature_builder.start())
        
        # Load specific model for Gate
        gate_model = os.getenv("OPENROUTER_MODEL_GATE", "deepseek/deepseek-r1")
        self.ai = OpenRouterAgent(model=gate_model)
        
        # Thresholds
        self.conf_threshold = 0.55

    async def evaluate_window(self, window_id: str, binance_features: dict):
        """
        Main Gate logic: Combined Binance + Bullpen + AI Reasoning.
        """
        logger.info(f"Evaluating Gate for {window_id}...")
        
        # 1. Fetch External Signals
        bullpen_data = self.bullpen.get_smart_money_signals()
        bullpen_score = bullpen_data.get("score", 0.0) if bullpen_data else 0.0
        
        # 2. Get ML Prediction (LightGBM)
        ml_features = {
            "cvd": binance_features.get("cvd", 0.0),
            "ob_imbalance": binance_features.get("ob_imbalance", 0.0),
            "bullpen_sentiment": bullpen_score
        }
        ml_score = self.ml_model.predict(ml_features)
        
        # 3. Consolidate Context for AI
        context = {
            "cvd": binance_features.get("cvd", 0.0),
            "ob_imbalance": binance_features.get("ob_imbalance", 0.0),
            "ml_prediction_score": ml_score,
            "bullpen_sentiment": bullpen_score,
            "news_impact": 0.0 
        }
        
        # 3. Get AI Reasoning Layer
        print(f"DEBUG: Context sent to AI: {json.dumps(context)}")
        ai_analysis = self.ai.analyze_market_context(context)
        confidence = ai_analysis.get("confidence", 0.5)
        decision = ai_analysis.get("decision", "WAIT")
        ai_thought = ai_analysis.get("reasoning", "")

        # 4. Hybrid Logic (Interface Contract Alignment)
        p_up = ml_score
        p_down = 1.0 - ml_score
        convergence_score = (bullpen_score + 1.0) / 2.0 # Scale -1..1 to 0..1
        
        # 5. Final Decision Logic (Confidence Gate - Section 3.1)
        signal_label = "Hybrid Intelligence Active"
        executor_msg = "Market condition stable."
        
        # Rule: Confidence < threshold (MD 3.1)
        if confidence < self.conf_threshold:
            decision = "SKIP"
            executor_msg = f"[Veto] Low Conviction: {confidence:.2f} < {self.conf_threshold}"
            
        # Rule: Convergence Score < 0.3 (MD 3.1)
        elif convergence_score < 0.3:
            decision = "SKIP"
            executor_msg = f"[Veto] Smart Money Diverge: Convergence {convergence_score:.2f} < 0.3"

        # Rule: Extreme ML Divergence
        elif decision == "ENTER" and ml_score < 0.25:
            decision = "SKIP"
            executor_msg = f"[Veto] ML Statistical Warning: Score {ml_score:.2f} too low."

        # 6. Record to Memory (Interface Contract Fields - Section 2.1)
        record_data = {
            "window_id": window_id,
            "signal": "BULL" if p_up > 0.5 else "BEAR",
            "confidence": confidence,
            "p_up": p_up,
            "p_down": p_down,
            "convergence_score": convergence_score,
            "news_impact": 0.0, # News Agent placeholder
            "gate_decision": decision,
            "ai_thought": ai_thought,
            "executor_msg": executor_msg,
            "features_snapshot": binance_features
        }
        self.memory.record_window(record_data)
        
        # 7. Notify Telegram (Premium Format)
        await self.notify_telegram_premium(record_data)
        
        return decision, 0.0

    async def notify_telegram_premium(self, record):
        # Using raw emojis for better compatibility
        message = (
            f"🧠 [V3 GATE] Decision: {record['gate_decision']}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🆔 Window: {record['window_id']}\n"
            f"📊 Confidence: {record['confidence']:.2f}\n"
            f"📈 P_UP: {record.get('p_up', 0.5):.2f} | P_DN: {record.get('p_down', 0.5):.2f}\n"
            f"🤝 Convergence: {record.get('convergence_score', 0.5):.2f}\n"
            f"💬 AI Thought: {record['ai_thought']}\n"
            f"⚙️ Executor: {record['executor_msg']}\n"
            f"━━━━━━━━━━━━━━━"
        )
        print(message)
        
        # Send to Telegram
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if bot_token and chat_id:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {"chat_id": chat_id, "text": message}
                requests.post(url, json=payload, timeout=10)
            except Exception as e:
                logger.error(f"Telegram Notify Failed: {e}")
