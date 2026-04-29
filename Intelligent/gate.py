import time
import json
import logging
import os
import datetime
import asyncio
import requests
from dotenv import load_dotenv
from .memory import PoolMemory
from .bullpen_connector import BullpenConnector
from .openrouter_agent import OpenRouterAgent

logger = logging.getLogger("intelligent.gate")

# Load environment
env_path = os.path.join(os.path.dirname(__file__), "config.env")
load_dotenv(env_path)

class IntelligentGate:
    def __init__(self):
        self.memory = PoolMemory()
        self.bullpen = BullpenConnector()
        
        # Load specific model for Gate
        gate_model = os.getenv("OPENROUTER_MODEL_GATE", "deepseek/deepseek-r1")
        self.ai = OpenRouterAgent(model=gate_model)
        
        # Thresholds (could be loaded from config.env)
        self.conf_threshold = 0.55

    async def evaluate_window(self, window_id: str, binance_features: dict):
        """
        Main orchestration for the Intelligent Gate (T-25).
        Returns the final gate decision and dynamic adjustment.
        """
        logger.info(f"Evaluating Gate for {window_id}...")
        
        # 1. Fetch External Signals
        bullpen_data = self.bullpen.get_smart_money_signals()
        bullpen_score = bullpen_data.get("score", 0.0) if bullpen_data else 0.0
        
        # 2. Consolidate Context for LLM Reasoning
        context = {
            "cvd": binance_features.get("cvd", 0.0),
            "ob_imbalance": binance_features.get("ob_imbalance", 0.0),
            "bullpen_score": bullpen_score,
            "news_impact": 0.0 # Placeholder for now
        }
        
        # 3. Get AI Reasoning Layer
        print(f"DEBUG: Requesting AI Analysis for {window_id}...")
        ai_analysis = self.ai.analyze_market_context(context)
        
        confidence = ai_analysis.get("confidence", 0.5)
        decision = ai_analysis.get("decision", "WAIT")
        ai_direction = ai_analysis.get("direction", "NONE")
        reasoning = ai_analysis.get("reasoning", "")
        
        # 4. Final Logic Override (V3 Advanced Veto Rules)
        skip_reason = "NONE"
        
        # Rule A: Skip if low confidence AND Bullpen is indecisive
        if confidence < self.conf_threshold and abs(bullpen_score) < 0.2:
            decision = "SKIP"
            skip_reason = "low_confidence_veto"
            reasoning = "[Veto] Indecisive Market: Low AI Confidence & Low Whale Movement."

        # Rule B: Veto if AI Bullish but Whales are Strongly Bearish
        if decision == "ENTER" and ai_direction == "UP" and bullpen_score < -0.8:
            decision = "SKIP"
            skip_reason = "bullpen_bearish_veto"
            reasoning = "[Veto] Bullpen Counter-Signal: Whales are heavily Bearish."
            
        # Rule C: Veto if AI Bearish but Whales are Strongly Bullish
        if decision == "ENTER" and ai_direction == "DOWN" and bullpen_score > 0.8:
            decision = "SKIP"
            skip_reason = "bullpen_bullish_veto"
            reasoning = "[Veto] Bullpen Counter-Signal: Whales are heavily Bullish."

        gate_reasoning = reasoning # Final executor reasoning

        # 5. Calculate Dynamic Target Adjustment
        dynamic_adj = 0.0
        if decision == "ENTER" and confidence > 0.75:
            dynamic_adj = -0.02 # Selective entry (look for better price or confirm strength)
        
        # 6. Record to Pool Memory
        record_data = {
            "window_id": window_id,
            "timestamp_created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "signal": "BULL" if bullpen_score > 0 else "BEAR",
            "confidence": confidence,
            "convergence_score": bullpen_score,
            "bullpen_sentiment": bullpen_score,
            "news_impact": 0.0,
            "dynamic_target_adj": dynamic_adj,
            "gate_decision": decision,
            "skip_reason": skip_reason,
            "gate_reasoning": gate_reasoning,
            "llm_reasoning": ai_analysis.get("reasoning", ""),
            "features_snapshot": binance_features
        }
        self.memory.record_window(record_data)
        
        # 7. Notify Telegram (V3 Record)
        # Include skip_reason in notification if it's a SKIP
        signal_label = f"Bullpen Signal Active"
        if skip_reason != "NONE":
            signal_label = f"VETO: {skip_reason}"
            
        await self.notify_telegram_record(record_data, signal_label)
        
        return decision, dynamic_adj

    async def notify_telegram_record(self, record, news_summary):
        msg = (
            f"\U0001f9e0 [V3 GATE] Decision: {record['gate_decision']}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"🆔 Window: {record['window_id']}\n"
            f"\U0001f4ca Confidence: {record['confidence']:.2f}\n"
            f"\U0001f4c8 Bullpen: {record['bullpen_sentiment']:.2f}\n"
            f"\U0001f4f0 Signal: {news_summary}\n"
            f"\U0001f4ac AI Thought: {record['llm_reasoning']}\n"
            f"\u2699\ufe0f Executor: {record['gate_reasoning']}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
        )
        print(msg)
        
        # Send to Telegram
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if bot_token and chat_id:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {"chat_id": chat_id, "text": msg}
            try:
                await asyncio.to_thread(requests.post, url, json=payload, timeout=5)
            except Exception as e:
                logger.error(f"Gate Telegram Notify Failed: {e}")
