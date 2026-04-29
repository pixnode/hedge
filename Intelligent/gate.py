import os
import json
import logging
import requests
import asyncio
from dotenv import load_dotenv
from .memory import PoolMemory
from .bullpen_connector import BullpenConnector
from .openrouter_agent import OpenRouterAgent

logger = logging.getLogger("intelligent.gate")

class IntelligentGate:
    def __init__(self):
        self.memory = PoolMemory()
        self.bullpen = BullpenConnector()
        
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
        
        # 2. Consolidate Context for LLM Reasoning
        context = {
            "cvd": binance_features.get("cvd", 0.0),
            "ob_imbalance": binance_features.get("ob_imbalance", 0.0),
            "bullpen_sentiment": bullpen_score,
            "news_impact": 0.0 
        }
        
        # 3. Get AI Reasoning Layer
        print(f"DEBUG: Requesting AI Analysis for {window_id}...")
        ai_analysis = self.ai.analyze_market_context(context)
        
        confidence = ai_analysis.get("confidence", 0.5)
        decision = ai_analysis.get("decision", "WAIT")
        reasoning = ai_analysis.get("reasoning", "")
        
        # 4. Final Logic Override (Veto)
        # Revert to simple veto to prevent 0.00 blindness
        if confidence < self.conf_threshold and abs(bullpen_score) < 0.2:
            decision = "SKIP"
            reasoning = f"[Veto] Low conviction from both AI ({confidence}) and Bullpen ({bullpen_score})."

        # 5. Calculate Dynamic Target Adjustment
        dynamic_adj = 0.0
        if decision == "ENTER":
            # Adjust target based on confidence
            if confidence > 0.8: dynamic_adj = 0.05
            elif confidence < 0.6: dynamic_adj = -0.05

        # 6. Record to Memory
        record_data = {
            "window_id": window_id,
            "confidence": confidence,
            "bullpen_sentiment": bullpen_score,
            "cvd": context["cvd"],
            "gate_decision": decision,
            "llm_reasoning": reasoning,
            "features_snapshot": binance_features
        }
        self.memory.record_window(record_data)
        
        # 7. Notify Telegram
        await self.notify_telegram_record(record_data, "Bullpen Signal Active")
        
        return decision, dynamic_adj

    async def notify_telegram_record(self, record, signal_label):
        message = (
            f"━━━━━━━━━━━━━━━\n"
            f" [V3 GATE] Decision: {record['gate_decision']}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"ID Window: {record['window_id']}\n"
            f"Confidence: {record['confidence']:.2f}\n"
            f"Bullpen: {record['bullpen_sentiment']:.2f}\n"
            f"Signal: {signal_label}\n"
            f"AI: {record['llm_reasoning']}\n"
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
