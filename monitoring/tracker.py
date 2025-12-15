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
    
    MIN_VOLATILITY_THRESHOLD = 5.0  # 5% pump
    VOLATILITY_WINDOW_MINUTES = 5   # In 5 minutes

    def __init__(self, exchange_client: ExchangeClient, bot: Bot, db: DatabaseClient):
        self.exchange_client = exchange_client
        self.bot = bot
        self.db = db
        self.messages = BotMessages()
        
        # Cache previous prices for comparison
        # Format: { "symbol:exchange": [(price, timestamp), ...] }
        self.price_history: Dict[str, List[tuple]] = {}
        
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
                # Periodic cleanup
                self.cleanup_old_history()
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
            
            cache_key = f"{symbol}:{exchange}"
            
            # 1. Update Price History
            now = datetime.utcnow()
            if cache_key not in self.price_history:
                self.price_history[cache_key] = []
            self.price_history[cache_key].append((price, now))
            
            # 2. Check for Short-Term Volatility (Pump)
            volatility_spike = self._check_volatility(cache_key, price, now)
            
            # 3. Check for 24h High Spike
            daily_spike = config.MIN_SPIKE_THRESHOLD <= change_24h <= config.MAX_SPIKE_THRESHOLD
            
            if daily_spike or volatility_spike:
                # Use a specific type for alert frequency check? 
                # For now, share the simplified throttling (1h cool off)
                
                # If it's a volatility spike, we might want to alert even if change_24h is low
                # The message format currently assumes "Gain" is change_24h. 
                # We should pass the effective change if possible, but let's stick to 24h for consistency 
                # or indicate it's a "Pump Alert".
                # For simplicity, we use the same alert flow.
                
                if await self._should_alert(cache_key, symbol, exchange, change_24h):
                    await self._send_spike_alert(
                        symbol, exchange, price, change_24h, volume
                    )
                    
                    # Record this alert
                    self.alerted_spikes[cache_key] = datetime.utcnow()
                    
                    # Save to database
                    await self.db.save_alert(symbol, exchange, change_24h)

    def _check_volatility(self, cache_key: str, current_price: float, current_time: datetime) -> bool:
        """Check if price moved X% in last Y minutes"""
        history = self.price_history.get(cache_key, [])
        if not history:
            return False
            
        # Find price from window ago (e.g. 5 mins)
        target_time = current_time - timedelta(minutes=self.VOLATILITY_WINDOW_MINUTES)
        
        # Find closest entry that is at least window old (or close to it)
        # Scan history
        old_price = None
        for p, t in history:
            # We want an entry that is roughly window ago. 
            # If t <= target_time, it means it's older than 5 mins.
            # We take the most recent entry that satisfies "older than window - buffer"?
            # Actually, we want the price AT target_time.
            # If we find a record older than target_time, we can use it.
            if t <= target_time:
                 old_price = p
                 # Continue to find the closest one to target_time? 
                 # Since list is appended, early entries are oldest. 
                 # We want the *latest* entry that is <= target_time, 
                 # OR the earliest entry if we don't have enough history?
                 # Let's simple pick: Any entry older than 5 mins is a reference point.
                 # To capture "5% in 5 mins", we check the price 5 mins ago.
            else:
                # This entry is newer than target window.
                # If we found an old_price already, break.
                if old_price: 
                    break
        
        if old_price and old_price > 0:
            percent_change = ((current_price - old_price) / old_price) * 100
            if percent_change >= self.MIN_VOLATILITY_THRESHOLD:
                # print(f"🚀 VOLATILITY DETECTED: {cache_key} +{percent_change:.2f}% in 5m")
                return True
                
        return False

    def cleanup_old_history(self):
        """Remove history older than window + buffer"""
        cutoff = datetime.utcnow() - timedelta(minutes=self.VOLATILITY_WINDOW_MINUTES + 5)
        for key in list(self.price_history.keys()):
            self.price_history[key] = [
                (p, t) for (p, t) in self.price_history[key]
                if t > cutoff
            ]
            if not self.price_history[key]:
                del self.price_history[key]
    
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
        # Get all users with alerts enabled (includes preferences from lookup)
        users = await self.db.get_users_with_alerts_enabled()
        
        if not users:
            return
            
        # Generate URL once
        url = self.exchange_client._generate_trade_link(exchange, symbol)
        
        # Format alert message
        message = self.messages.format_spike_alert(
            symbol, exchange, price, change, volume, url
        )
        
        print(f"🚨 Sending spike alert: {symbol} on {exchange} (+{change}%)")
        
        # Send to valid users
        for user in users:
            try:
                # Check user preferences
                prefs = user.get('prefs', {})
                if prefs:
                    allowed_exchanges = prefs.get('alert_exchanges')
                    # If allowed_exchanges is None/Empty, default to ALL (or configured defaults)
                    # But if the key exists and is a list, check it.
                    if allowed_exchanges is not None: 
                        if exchange not in allowed_exchanges:
                            continue
                
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