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
        self.watchlists = None
        self.banned_users = None  # Admin: banned users
    
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
            self.watchlists = self.db.watchlists
            self.banned_users = self.db.banned_users  # Admin: banned users
            
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
        
        # Watchlist indexes
        await self.watchlists.create_index("user_id", unique=True)
        
        # Banned users indexes
        await self.banned_users.create_index("user_id", unique=True)
    
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
                    "alerts_enabled": False,  # Default OFF - users opt-in via /alerts
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
    
    # Watchlist operations
    async def get_user_watchlist(self, user_id: int) -> List[str]:
        """Get user's watchlist symbols"""
        doc = await self.watchlists.find_one({"user_id": user_id})
        if doc:
            return doc.get("symbols", [])
        return []
    
    async def add_to_watchlist(self, user_id: int, symbol: str) -> bool:
        """Add a symbol to user's watchlist. Returns True if added, False if already exists."""
        # Normalize symbol (uppercase, remove common suffixes)
        symbol = symbol.upper().replace("/USDT", "").replace("-USDT", "")
        if not symbol.endswith("USDT"):
            symbol = f"{symbol}USDT"
        
        # Check if already in watchlist
        current = await self.get_user_watchlist(user_id)
        if symbol in current:
            return False
        
        # Add to watchlist
        await self.watchlists.update_one(
            {"user_id": user_id},
            {"$addToSet": {"symbols": symbol}},
            upsert=True
        )
        return True
    
    async def remove_from_watchlist(self, user_id: int, symbol: str) -> bool:
        """Remove a symbol from user's watchlist. Returns True if removed, False if not found."""
        # Normalize symbol
        symbol = symbol.upper().replace("/USDT", "").replace("-USDT", "")
        if not symbol.endswith("USDT"):
            symbol = f"{symbol}USDT"
        
        # Check if in watchlist
        current = await self.get_user_watchlist(user_id)
        if symbol not in current:
            return False
        
        # Remove from watchlist
        await self.watchlists.update_one(
            {"user_id": user_id},
            {"$pull": {"symbols": symbol}}
        )
        return True
    
    async def clear_watchlist(self, user_id: int) -> int:
        """Clear user's entire watchlist. Returns number of symbols removed."""
        current = await self.get_user_watchlist(user_id)
        count = len(current)
        
        if count > 0:
            await self.watchlists.update_one(
                {"user_id": user_id},
                {"$set": {"symbols": []}}
            )
        return count
    
    async def is_in_watchlist(self, user_id: int, symbol: str) -> bool:
        """Check if a symbol is in user's watchlist"""
        # Normalize symbol
        symbol = symbol.upper().replace("/USDT", "").replace("-USDT", "")
        if not symbol.endswith("USDT"):
            symbol = f"{symbol}USDT"
        
        current = await self.get_user_watchlist(user_id)
        return symbol in current
    
    async def get_watchlist_users_for_symbol(self, symbol: str) -> List[int]:
        """Get all user IDs who have this symbol in their watchlist"""
        # Normalize symbol
        symbol = symbol.upper().replace("/USDT", "").replace("-USDT", "")
        if not symbol.endswith("USDT"):
            symbol = f"{symbol}USDT"
        
        cursor = self.watchlists.find({"symbols": symbol})
        docs = await cursor.to_list(length=None)
        return [doc["user_id"] for doc in docs]
    
    # Admin operations
    async def ban_user(self, user_id: int, banned_by: int, reason: str = "") -> bool:
        """Ban a user. Returns True if newly banned, False if already banned."""
        existing = await self.banned_users.find_one({"user_id": user_id})
        if existing:
            return False
        
        await self.banned_users.insert_one({
            "user_id": user_id,
            "banned_by": banned_by,
            "reason": reason,
            "banned_at": datetime.utcnow()
        })
        return True
    
    async def unban_user(self, user_id: int) -> bool:
        """Unban a user. Returns True if unbanned, False if wasn't banned."""
        result = await self.banned_users.delete_one({"user_id": user_id})
        return result.deleted_count > 0
    
    async def is_banned(self, user_id: int) -> bool:
        """Check if a user is banned"""
        doc = await self.banned_users.find_one({"user_id": user_id})
        return doc is not None
    
    async def get_banned_users(self) -> List[Dict]:
        """Get all banned users"""
        cursor = self.banned_users.find({})
        return await cursor.to_list(length=None)
    
    async def get_all_users(self) -> List[Dict]:
        """Get all registered users"""
        cursor = self.users.find({})
        return await cursor.to_list(length=None)
    
    async def get_user_count(self) -> int:
        """Get total user count"""
        return await self.users.count_documents({})
    
    async def get_active_users_count(self, hours: int = 24) -> int:
        """Get count of users active in last N hours"""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return await self.users.count_documents({"last_active": {"$gte": cutoff}})
    
    async def get_bot_stats(self) -> Dict:
        """Get overall bot statistics for admin dashboard"""
        total_users = await self.get_user_count()
        active_24h = await self.get_active_users_count(24)
        alerts_enabled = await self.users.count_documents({"alerts_enabled": True})
        alerts_sent = await self.alert_history.count_documents({})
        banned_count = await self.banned_users.count_documents({})
        
        # Get watchlist stats
        watchlist_cursor = self.watchlists.find({})
        watchlists = await watchlist_cursor.to_list(length=None)
        total_watchlist_items = sum(len(w.get("symbols", [])) for w in watchlists)
        users_with_watchlist = len([w for w in watchlists if w.get("symbols")])
        
        return {
            "total_users": total_users,
            "active_24h": active_24h,
            "alerts_enabled": alerts_enabled,
            "alerts_sent_total": alerts_sent,
            "banned_users": banned_count,
            "users_with_watchlist": users_with_watchlist,
            "total_watchlist_items": total_watchlist_items
        }