from openrouter_agent import OpenRouterAgent
import json
import asyncio

async def test():
    agent = OpenRouterAgent()
    print(f"Using Model: {agent.model}")
    
    context = {
        "cvd": 500.0,
        "ob_imbalance": 0.1,
        "bullpen_score": 0.5,
        "news_impact": 0.0
    }
    
    print("Sending request to OpenRouter...")
    result = agent.analyze_market_context(context)
    print("\nAI DECISION:")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(test())
