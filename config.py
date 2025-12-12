import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    
    # MongoDB
    MONGODB_URL = os.getenv("MONGODB_URL")
    MONGODB_DB_NAME = "topgainers"  # Database name
    
    # Monitoring
    SPIKE_CHECK_INTERVAL = int(os.getenv("SPIKE_CHECK_INTERVAL", 60))
    MIN_SPIKE_THRESHOLD = float(os.getenv("MIN_SPIKE_THRESHOLD", 30))
    MAX_SPIKE_THRESHOLD = float(os.getenv("MAX_SPIKE_THRESHOLD", 70))
    
    # Exchanges
    EXCHANGES = os.getenv("EXCHANGES", "binance,bybit,mexc,bitget,gateio").split(",")
    
    # Bybit regional endpoint
    # Options: "bybit.com" (global), "bybit.us" (US), "bybit.eu" (EU)
    BYBIT_HOSTNAME = os.getenv("BYBIT_HOSTNAME", "bybit.com")
    
    # Environment
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    IS_PRODUCTION = ENVIRONMENT == "production"
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        if not cls.MONGODB_URL:
            raise ValueError("MONGODB_URL is required")
        return True

config = Config()