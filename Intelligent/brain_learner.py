import logging
import json
import os
from dotenv import load_dotenv
from .memory import PoolMemory
from .openrouter_agent import OpenRouterAgent

logger = logging.getLogger("intelligent.learner")

class BrainLearner:
    def __init__(self):
        # Load environment variables from config.env
        env_path = os.path.join(os.path.dirname(__file__), "config.env")
        load_dotenv(env_path)
        
        self.memory = PoolMemory()
        
        # Load specific model for Learner (Default: Claude 3.5 Sonnet)
        learner_model = os.getenv("OPENROUTER_MODEL_LEARNER", "anthropic/claude-3.5-sonnet")
        self.ai = OpenRouterAgent(model=learner_model)

    def perform_daily_retrain_analysis(self):
        """
        Queries the last 288 windows (1 day) and asks AI to find patterns in losses/wins.
        """
        logger.info("Starting Daily Performance Audit...")
        
        # 1. Fetch data from memory
        records = self.memory.get_training_data(limit=288)
        if not records:
            logger.warning("Not enough data in Pool Memory for analysis.")
            return None

        # 2. Summarize for AI
        total_trades = len(records)
        # Assuming record structure from memory: (features_json, model_correct, window_id)
        win_count = sum(1 for r in records if r[1]) 
        win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0
        
        # Extract snapshots of failed trades to understand why
        fails = []
        for r in records:
            if not r[1]: # if model_correct is False
                try:
                    fails.append(json.loads(r[0]))
                except:
                    continue
        
        fails_sample = fails[:10] # Top 10 fails for context

        prompt = f"""
        QUANT PERFORMANCE AUDIT (Last 24 Hours):
        - Total Windows Evaluated: {total_trades}
        - AI Signal Accuracy: {win_rate:.2f}%
        
        FAILED TRADES SAMPLE (Features Snapshot):
        {json.dumps(fails_sample, indent=2)}
        
        TASK:
        1. Analyze patterns in failures (e.g. was CVD too high? was imbalance misleading?).
        2. Suggest a new 'Confidence Threshold' if needed.
        3. Provide a 'Daily Lesson' for the next 24 hours.
        
        OUTPUT JSON ONLY:
        {{
            "suggested_threshold": float,
            "daily_lesson": "string",
            "priority": "LOW/MEDIUM/HIGH"
        }}
        """

        try:
            # Load specific model for Learning Analysis from config.env
            analysis = self.ai.ask_ai(prompt)
            
            logger.info(f"Daily Learning Complete: {analysis.get('daily_lesson')}")
            return analysis
            
        except Exception as e:
            logger.error(f"Brain Learning Failed: {e}")
            return None

if __name__ == "__main__":
    learner = BrainLearner()
    print(f"Brain Learner Ready. Using Model: {learner.ai.model}")
