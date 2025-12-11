import asyncio
from datetime import datetime, timedelta
from typing import Dict, List
from database.client import DatabaseClient
from telegram import Bot
from telegram.constants import ParseMode

from exchanges.client import ExchangeClient
from bot.messages import BotMessages
from config import config

class SpikeTracker:
    """Monitor exchanges for sudden price spikes and alert users"""
    
    def __init__(self, exchange_client: ExchangeClient, bot: Bot, db: DatabaseClient):
        self.exchange_client = exchange_client
        self.bot = bot
        self.db = db
        self.messages = BotMessages()
        
        # Cache previous prices for comparison
        self.price_cache: Dict[str, Dict] = {}
        
        # Track which spikes we've already alerted on (prevent spam)
        self.alerted_spikes: Dict[str, datetime] = {}
        
        self.is_running = False
    
    async def start(self):
        """Start the monitoring loop"""
        self.is_running = True
        print("🔍 Spike tracker started")
        
        while self.is_running:
            try:
                await self._check_all_exchanges()
                await asyncio.sleep(config.SPIKE_CHECK_INTERVAL)
            except Exception as e:
                print(f"Error in spike tracker: {e}")
                await asyncio.sleep(10)  # Wait before retrying
    
    async def stop(self):
        """Stop the monitoring loop"""
        self.is_running = False
        print("🛑 Spike tracker stopped")
    
    async def _check_all_exchanges(self):
        """Check all exchanges for spikes"""
        for exchange_name in config.EXCHANGES:
            try:
                await self._check_exchange_spikes(exchange_name)
            except Exception as e:
                print(f"Error checking {exchange_name}: {e}")
    
    async def _check_exchange_spikes(self, exchange_name: str):
        """Check a single exchange for price spikes"""
        # Get top gainers from this exchange
        gainers = await self.exchange_client.get_top_gainers(
            exchange_name, 
            limit=50  # Check more coins for potential spikes
        )
        
        for gainer in gainers:
            symbol = gainer['symbol']
            exchange = gainer['exchange']
            price = gainer['price']
            change_24h = gainer['change_24h']
            volume = gainer['volume_24h']
            
            # Check if this is a spike (within threshold range)
            if config.MIN_SPIKE_THRESHOLD <= change_24h <= config.MAX_SPIKE_THRESHOLD:
                cache_key = f"{symbol}:{exchange}"
                
                # Check if we've already alerted on this spike recently
                if await self._should_alert(cache_key, symbol, exchange, change_24h):
                    await self._send_spike_alert(
                        symbol, exchange, price, change_24h, volume
                    )
                    
                    # Record this alert
                    self.alerted_spikes[cache_key] = datetime.utcnow()
                    
                    # Save to database
                    await self.db.save_alert(symbol, exchange, change_24h)
    
    async def _should_alert(self, cache_key: str, symbol: str, exchange: str, current_change: float) -> bool:
        """Determine if we should send an alert for this spike"""
        # Check in-memory cache first (faster)
        if cache_key in self.alerted_spikes:
            last_alert = self.alerted_spikes[cache_key]
            if datetime.utcnow() - last_alert < timedelta(hours=1):
                return False  # Don't spam alerts
        
        # Check database for recent alerts
        recent_alerts = await self.db.get_recent_alerts(symbol, exchange, hours=1)
        if recent_alerts:
            return False
        
        return True
    
    async def _send_spike_alert(
        self, 
        symbol: str, 
        exchange: str, 
        price: float, 
        change: float, 
        volume: float
    ):
        """Send spike alert to all users with alerts enabled"""
        # Get all users with alerts enabled
        users = await self.db.get_users_with_alerts_enabled()
        
        if not users:
            return
        
        # Format alert message
        message = self.messages.format_spike_alert(
            symbol, exchange, price, change, volume
        )
        
        print(f"🚨 Sending spike alert: {symbol} on {exchange} (+{change}%)")
        
        # Send to all users
        for user in users:
            try:
                await self.bot.send_message(
                    chat_id=user['id'],
                    text=message,
                    parse_mode=ParseMode.MARKDOWN
                )
                await asyncio.sleep(0.05)  # Rate limiting
            except Exception as e:
                print(f"Failed to send alert to user {user['id']}: {e}")
    
    def cleanup_old_alerts(self):
        """Clean up old entries from alerted_spikes cache"""
        cutoff = datetime.utcnow() - timedelta(hours=2)
        self.alerted_spikes = {
            k: v for k, v in self.alerted_spikes.items() 
            if v > cutoff
        }