import lightgbm as lgb
import pandas as pd
import numpy as np
import joblib
import os
import logging

# Path to save the trained model
MODEL_PATH = os.path.join(os.path.dirname(__file__), "gate_model.pkl")

logger = logging.getLogger("intelligent.model")

class IntelligentModel:
    def __init__(self):
        self.model = None
        self._load_model()

    def _load_model(self):
        """Loads the pre-trained LightGBM model if it exists."""
        if os.path.exists(MODEL_PATH):
            try:
                self.model = joblib.load(MODEL_PATH)
                logger.info("LightGBM model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load model: {e}")

    def train(self, X, y):
        """
        Trains the LightGBM model on historical Pool Memory data.
        X: DataFrame of 12 features
        y: Target (model_correct or actual WIN/LOSS)
        """
        logger.info(f"Starting LightGBM training on {len(X)} records...")
        
        # Hyperparameters (Optimized for financial time-series)
        params = {
            'objective': 'binary',
            'metric': 'binary_logloss',
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'learning_rate': 0.05,
            'feature_fraction': 0.9
        }
        
        train_data = lgb.Dataset(X, label=y)
        self.model = lgb.train(params, train_data, num_boost_round=100)
        
        # Save for future use
        joblib.dump(self.model, MODEL_PATH)
        logger.info(f"Model saved to {MODEL_PATH}")

    def predict(self, features: dict):
        """
        Predicts the probability of a successful hedge.
        Returns a float between 0 and 1.
        """
        if self.model is None:
            # Fallback to neutral if no model is trained yet
            return 0.5
            
        try:
            # Convert dict to DataFrame row
            X = pd.DataFrame([features])
            prob = self.model.predict(X)
            return float(prob[0])
        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return 0.5

if __name__ == "__main__":
    # Test script for LightGBM
    model = IntelligentModel()
    print("Model instance created.")
    # X_dummy = pd.DataFrame(np.random.rand(10, 5), columns=['cvd', 'ob', 'vol', 'spread', 'bullpen'])
    # y_dummy = np.random.randint(0, 2, 10)
    # model.train(X_dummy, y_dummy)
