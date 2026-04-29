import sys
import os
import asyncio

# Setup path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

async def test_gate_init():
    print("--- TESTING GATE INITIALIZATION ---")
    try:
        from Intelligent.gate import IntelligentGate
        gate = IntelligentGate()
        print(f"SUCCESS: Gate initialized. Model: {gate.ai.model}")
        print(f"SUCCESS: FeatureBuilder ready: {gate.feature_builder is not None}")
        
        # Test a mock evaluation call
        mock_features = {"cvd": 100.0, "ob_imbalance": 0.5}
        print("Testing mock evaluation call (expecting AI Error or Timeout since no API key)...")
        # We don't actually await it fully to avoid hanging, just check if it's a coroutine
        coro = gate.evaluate_window("test_window", mock_features)
        print(f"SUCCESS: evaluate_window is an awaitable: {asyncio.iscoroutine(coro)}")
        
    except Exception as e:
        print(f"FAILED: Initialization error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_gate_init())
