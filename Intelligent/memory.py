import sqlite3
import json
import os
import datetime
import asyncio
import logging

# Path to the database in the Intelligent department
DB_PATH = os.path.join(os.path.dirname(__file__), "pool_memory.db")

logger = logging.getLogger("intelligent.memory")

class PoolMemory:
    def __init__(self):
        self.conn = None
        self._init_db()

    def _init_db(self):
        """Initializes the SQLite database with the v3.0 schema."""
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")  # For concurrent HFT access
        
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS window_records (
                window_id TEXT PRIMARY KEY,
                timestamp_created DATETIME,
                
                -- Signals
                signal TEXT,
                confidence REAL,
                p_up REAL,
                p_down REAL,
                convergence_score REAL,
                bullpen_sentiment REAL,
                news_impact REAL,
                
                -- Decisions
                dynamic_target_adj REAL,
                gate_decision TEXT,
                llm_reasoning TEXT,
                
                -- ATS Outcomes (Updated later)
                ats_status TEXT,
                ats_pnl REAL,
                ats_up_entry REAL,
                ats_down_entry REAL,
                outcome TEXT,
                model_correct BOOLEAN,
                outcome_timestamp DATETIME,
                
                -- Snapshots
                features_snapshot TEXT, -- JSON string of 12 features
                raw_data_dump TEXT      -- JSON string of raw API responses
            )
        """)
        self.conn.commit()
        logger.info(f"Pool Memory initialized at {DB_PATH}")

    def record_window(self, data: dict):
        """
        Records the initial state of a window before execution.
        Expected keys: window_id, signal, confidence, convergence_score, bullpen_sentiment, etc.
        """
        try:
            cursor = self.conn.cursor()
            cols = [
                "window_id", "timestamp_created", "signal", "confidence", 
                "p_up", "p_down", "convergence_score", "bullpen_sentiment", 
                "news_impact", "dynamic_target_adj", "gate_decision", 
                "llm_reasoning", "features_snapshot"
            ]
            
            # Ensure features_snapshot is JSON
            if isinstance(data.get("features_snapshot"), dict):
                data["features_snapshot"] = json.dumps(data["features_snapshot"])
            
            placeholders = ", ".join(["?"] * len(cols))
            sql = f"INSERT OR REPLACE INTO window_records ({', '.join(cols)}) VALUES ({placeholders})"
            
            values = [
                data.get("window_id"),
                data.get("timestamp_created", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                data.get("signal", "NEUTRAL"),
                data.get("confidence", 0.0),
                data.get("p_up", 0.5),
                data.get("p_down", 0.5),
                data.get("convergence_score", 0.0),
                data.get("bullpen_sentiment", 0.0),
                data.get("news_impact", 0.0),
                data.get("dynamic_target_adj", 0.0),
                data.get("gate_decision", "WAIT"),
                data.get("llm_reasoning", ""),
                data.get("features_snapshot", "{}")
            ]
            
            cursor.execute(sql, values)
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to record window: {e}")
            return False

    def update_outcome(self, window_id: str, outcome_data: dict):
        """
        Updates a record with actual ATS execution results.
        Expected keys: ats_status, ats_pnl, ats_up_entry, ats_down_entry, outcome
        """
        try:
            cursor = self.conn.cursor()
            
            # Determine if model was correct
            # Logic: If BULL and UP won, or BEAR and DOWN won
            # This requires knowing the winner side from Polymarket later, 
            # or we just rely on PnL > 0 for now.
            pnl = outcome_data.get("ats_pnl", 0.0)
            model_correct = pnl > 0
            
            sql = """
                UPDATE window_records 
                SET ats_status = ?, ats_pnl = ?, ats_up_entry = ?, 
                    ats_down_entry = ?, outcome = ?, model_correct = ?, outcome_timestamp = ?
                WHERE window_id = ?
            """
            cursor.execute(sql, (
                outcome_data.get("ats_status"),
                pnl,
                outcome_data.get("ats_up_entry"),
                outcome_data.get("ats_down_entry"),
                outcome_data.get("outcome"),
                model_correct,
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                window_id
            ))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update outcome: {e}")
            return False

    def get_training_data(self, limit=288):
        """Fetches the last N completed windows for Daily Retrain."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT features_snapshot, model_correct 
                FROM window_records 
                WHERE outcome IS NOT NULL 
                ORDER BY timestamp_created DESC 
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()
        except Exception:
            return []

if __name__ == "__main__":
    # Test initialization
    mem = PoolMemory()
    test_data = {
        "window_id": "TEST_WINDOW_001",
        "signal": "BULL",
        "confidence": 0.85,
        "features_snapshot": {"rsi": 65, "cvd": 1200}
    }
    mem.record_window(test_data)
    print("Test Record Created.")
    
    mem.update_outcome("TEST_WINDOW_001", {
        "ats_status": "HEDGED",
        "ats_pnl": 0.55,
        "outcome": "WIN"
    })
    print("Test Outcome Updated.")
