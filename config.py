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
    TARGET_MAX_ENTRY: float = float(os.getenv("TARGET_MAX_ENTRY", "0.20"))
    MAX_HEDGE_COST: float = float(os.getenv("MAX_HEDGE_COST", "0.80"))
    ABSOLUTE_SLIPPAGE: float = float(os.getenv("ABSOLUTE_SLIPPAGE", "0.10"))
    
    # Temporal Constraints (in seconds, Cast to int)
    GOLDEN_WINDOW_START_SEC: int = int(os.getenv("GOLDEN_WINDOW_START_SEC", "300"))
    GOLDEN_WINDOW_END_SEC: int = int(os.getenv("GOLDEN_WINDOW_END_SEC", "20"))
    
    # Dead Zone: UTC hour ranges where bot skips all windows (low volatility / thin liquidity)
    # Format: "HH-HH,HH-HH" e.g. "20-00,05-07" = skip 20:00-00:00 UTC AND 05:00-07:00 UTC
    # Set to "" to disable dead zone skipping
    DEAD_ZONE_UTC: str = os.getenv("DEAD_ZONE_UTC", "20-00,05-07")
    
    # Position Sizing
    BASE_TRADE_USD: float = float(os.getenv("BASE_TRADE_USD", "2.0"))
    MAX_POSITION_USD: float = float(os.getenv("MAX_POSITION_USD", "5.0"))
    
    # Proxy & Security
    POLY_PROXY_ADDRESS: str = os.getenv("POLY_PROXY_ADDRESS", "")
    SIGNATURE_TYPE: int = int(os.getenv("SIGNATURE_TYPE", "1")) # 1 for EOA, 2 for Proxy/Safe
    
    # Telegram Notification
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

config = Config()
