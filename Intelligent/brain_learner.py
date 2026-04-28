import logging
import json
from .memory import PoolMemory
from .openrouter_agent import OpenRouterAgent

logger = logging.getLogger("intelligent.learner")

class BrainLearner:
    def __init__(self):
        self.memory = PoolMemory()
        self.ai = OpenRouterAgent()

    def perform_daily_retrain_analysis(self):
        """
        Queries the last 288 windows (1 day) and asks AI to find patterns in losses/wins.
        """
        # 1. Fetch data from memory
        records = self.memory.get_training_data(limit=288)
        if not records:
            logger.warning("Not enough data in Pool Memory for analysis.")
            return None

        # 2. Summarize for AI
        total_trades = len(records)
        win_count = sum(1 for r in records if r[1]) # model_correct is index 1
        win_rate = (win_count / total_trades) * 100
        
        # Extract snapshots of failed trades to understand why
        fails = [json.loads(r[0]) for r in records if not r[1]][:10] # Top 10 fails

        prompt = f"""
        PERFORMANCE REVIEW (Last 24 Hours):
        - Total Windows Evaluated: {total_trades}
        - AI Signal Accuracy: {win_rate:.2f}%
        
        FAILED TRADES SAMPLE (Features Snapshot):
        {json.dumps(fails, indent=2)}
        
        TASK:
        1. Identify if there's a common pattern in the failed trades (e.g., high volatility, specific CVD range).
        2. Suggest adjustment for 'dynamic_target_adj' or 'confidence_threshold'.
        3. Provide a 'Daily Lesson' for the bot.
        
        OUTPUT FORMAT (JSON ONLY):
        {{
            "suggested_threshold": float,
            "dynamic_adj_recommendation": float,
            "daily_lesson": "string",
            "priority": "LOW/MEDIUM/HIGH"
        }}
        """

        try:
            # We use a more powerful model for training analysis if available
            self.ai.model = "google/gemini-2.0-pro-exp-02-05:free" # Use Pro for reasoning
            analysis = self.ai.analyze_market_context({"custom_prompt": prompt}) # Generic method reuse
            
            logger.info(f"Daily Learning Complete: {analysis.get('daily_lesson')}")
            return analysis
            
        except Exception as e:
            logger.error(f"Brain Learning Failed: {e}")
            return None

if __name__ == "__main__":
    learner = BrainLearner()
    # analysis = learner.perform_daily_retrain_analysis()
    # print(analysis)
    print("Brain Learner Ready.")
