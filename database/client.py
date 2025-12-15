from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from typing import Optional, List, Dict
from config import config

class DatabaseClient:
    """MongoDB client for user and alert data management"""
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        
        # Collections
        self.users = None
        self.user_preferences = None
        self.price_snapshots = None
        self.alert_history = None
    
    async def connect(self):
        """Connect to MongoDB"""
        try:
            self.client = AsyncIOMotorClient(config.MONGODB_URL)
            self.db = self.client[config.MONGODB_DB_NAME]
            
            # Get collection references
            self.users = self.db.users
            self.user_preferences = self.db.user_preferences
            self.price_snapshots = self.db.price_snapshots
            self.alert_history = self.db.alert_history
            
            # Create indexes
            await self._create_indexes()
            
            # Test connection
            await self.client.admin.command('ping')
            print("✓ Connected to MongoDB")
            
        except Exception as e:
            print(f"✗ MongoDB connection failed: {e}")
            raise
    
    async def _create_indexes(self):
        """Create database indexes for better performance"""
        # User indexes
        await self.users.create_index("id", unique=True)
        
        # User preferences indexes
        await self.user_preferences.create_index("user_id", unique=True)
        
        # Price snapshots indexes
        await self.price_snapshots.create_index([("symbol", 1), ("exchange", 1), ("timestamp", -1)])
        
        # Alert history indexes
        await self.alert_history.create_index([("symbol", 1), ("exchange", 1), ("alerted_at", -1)])
    
    async def disconnect(self):
        """Disconnect from MongoDB"""
        if self.client:
            self.client.close()
            print("✓ Disconnected from MongoDB")
    
    # User operations
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        return await self.users.find_one({"id": user_id})
    
    async def create_or_update_user(self, user_id: int, username: Optional[str], first_name: str):
        """Create or update user"""
        now = datetime.utcnow()
        
        await self.users.update_one(
            {"id": user_id},
            {
                "$set": {
                    "username": username,
                    "first_name": first_name,
                    "last_active": now
                },
                "$setOnInsert": {
                    "id": user_id,
                    "alerts_enabled": True,
                    "created_at": now
                }
            },
            upsert=True
        )
    
    async def update_user_alerts(self, user_id: int, enabled: bool):
        """Enable or disable alerts for a user"""
        await self.users.update_one(
            {"id": user_id},
            {"$set": {"alerts_enabled": enabled}}
        )
    
    async def get_users_with_alerts_enabled(self) -> List[Dict]:
        """Get all users with alerts enabled"""
        # Use aggregation to join with preferences
        pipeline = [
            {"$match": {"alerts_enabled": True}},
            {"$lookup": {
                "from": "user_preferences",
                "localField": "id",
                "foreignField": "user_id",
                "as": "prefs"
            }},
            {"$unwind": {"path": "$prefs", "preserveNullAndEmptyArrays": True}}
        ]
        
        cursor = self.users.aggregate(pipeline)
        return await cursor.to_list(length=None)
    
    # User preferences operations
    async def get_user_preferences(self, user_id: int) -> Optional[Dict]:
        """Get user preferences"""
        return await self.user_preferences.find_one({"user_id": user_id})
    
    async def create_default_preferences(self, user_id: int):
        """Create default preferences for user"""
        default_prefs = {
            "user_id": user_id,
            "preferred_exchanges": ["binance", "bybit", "mexc", "bitget", "gateio"],
            "alert_exchanges": ["binance", "bybit", "mexc", "bitget", "gateio"],  # Enabled exchanges for alerts
            "default_top_count": 10,
            "min_alert_threshold": 30,
            "max_alert_threshold": 70
        }
        
        await self.user_preferences.update_one(
            {"user_id": user_id},
            {"$setOnInsert": default_prefs},
            upsert=True
        )

    async def update_user_alert_exchanges(self, user_id: int, exchanges: List[str]):
        """Update the list of exchanges a user wants alerts from"""
        await self.user_preferences.update_one(
            {"user_id": user_id},
            {"$set": {"alert_exchanges": exchanges}},
            upsert=True
        )
    
    # Alert history operations
    async def save_alert(self, symbol: str, exchange: str, percent_gain: float):
        """Save alert to history"""
        alert = {
            "symbol": symbol,
            "exchange": exchange,
            "percent_gain": percent_gain,
            "alerted_at": datetime.utcnow()
        }
        
        await self.alert_history.insert_one(alert)
    
    async def get_recent_alerts(self, symbol: str, exchange: str, hours: int = 1) -> List[Dict]:
        """Get recent alerts for a symbol/exchange pair"""
        from datetime import timedelta
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        cursor = self.alert_history.find({
            "symbol": symbol,
            "exchange": exchange,
            "alerted_at": {"$gte": cutoff}
        })
        
        return await cursor.to_list(length=None)
    
    # Price snapshot operations
    async def save_price_snapshot(self, symbol: str, exchange: str, price: float, 
                                   volume_24h: float, percent_change_24h: float):
        """Save price snapshot for historical tracking"""
        snapshot = {
            "symbol": symbol,
            "exchange": exchange,
            "price": price,
            "volume_24h": volume_24h,
            "percent_change_24h": percent_change_24h,
            "timestamp": datetime.utcnow()
        }
        
        await self.price_snapshots.insert_one(snapshot)
    
    async def get_price_history(self, symbol: str, exchange: str, limit: int = 100) -> List[Dict]:
        """Get price history for a symbol"""
        cursor = self.price_snapshots.find(
            {"symbol": symbol, "exchange": exchange}
        ).sort("timestamp", -1).limit(limit)
        
        return await cursor.to_list(length=None)