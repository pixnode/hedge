import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

@dataclass
class Config:
    # API Credentials
    POLYMARKET_PRIVATE_KEY: str = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    POLY_API_KEY: str = os.getenv("POLY_API_KEY", "")
    POLY_API_SECRET: str = os.getenv("POLY_API_SECRET", "")
    POLY_API_PASSPHRASE: str = os.getenv("POLY_API_PASSPHRASE", "")
    
    # Endpoints
    POLY_WS_URL: str = os.getenv("POLY_WS_URL", "wss://ws-subscriptions-clob.polymarket.com/ws/market")
    CLOB_HOST: str = os.getenv("CLOB_HOST", "https://clob.polymarket.com")
    
    # Execution Constraints (Cast to float)
    PAPER_TRADING_MODE: bool = os.getenv("PAPER_TRADING_MODE", "False").lower() in ("true", "1", "yes")
    TARGET_MAX_ODDS: float = float(os.getenv("TARGET_MAX_ODDS", "0.40"))
    MAX_TOTAL_HEDGE_COST: float = float(os.getenv("MAX_TOTAL_HEDGE_COST", "0.85"))
    
    # Temporal Constraints (in seconds, Cast to int)
    GOLDEN_WINDOW_START_SEC: int = int(os.getenv("GOLDEN_WINDOW_START_SEC", "300"))
    GOLDEN_WINDOW_END_SEC: int = int(os.getenv("GOLDEN_WINDOW_END_SEC", "20"))
    
    # Position Sizing (Cast to float)
    BASE_SHARES: float = float(os.getenv("BASE_SHARES", "1.0"))

config = Config()
