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
    """Monitor exchanges for sudden price spikes/dumps and alert users"""
    
    # Original thresholds (still used for quick detection)
    MIN_VOLATILITY_THRESHOLD = 5.0  # 5% pump
    MIN_DUMP_THRESHOLD = -5.0       # -5% dump (negative value)
    VOLATILITY_WINDOW_MINUTES = 5   # In 5 minutes
    
    # Multi-Factor Scoring Thresholds
    VOLUME_SPIKE_MULTIPLIER = 3.0   # Volume must be 3x average to score
    MOMENTUM_CANDLES_REQUIRED = 3   # 3 consecutive gains = momentum
    MIN_PUMP_SCORE = 50             # Minimum score to trigger early pump alert
    HIGH_PUMP_SCORE = 70            # High confidence pump alert
    
    # Scoring weights
    SCORE_VOLUME_SPIKE = 30         # Points for volume spike
    SCORE_MOMENTUM = 25             # Points for momentum (consecutive gains)
    SCORE_VOLATILITY = 25           # Points for 5m volatility
    SCORE_DAILY_TREND = 20          # Points for positive 24h trend

    def __init__(self, exchange_client: ExchangeClient, bot: Bot, db: DatabaseClient):
        self.exchange_client = exchange_client
        self.bot = bot
        self.db = db
        self.messages = BotMessages()
        
        # Cache previous prices for comparison
        # Format: { "symbol:exchange": [(price, timestamp), ...] }
        self.price_history: Dict[str, List[tuple]] = {}
        
        # Volume history for spike detection
        # Format: { "symbol:exchange": [(volume, timestamp), ...] }
        self.volume_history: Dict[str, List[tuple]] = {}
        
        # Track consecutive price movements for momentum
        # Format: { "symbol:exchange": [change1, change2, change3, ...] }
        self.momentum_history: Dict[str, List[float]] = {}
        
        # Track which spikes we've already alerted on (prevent spam)
        self.alerted_spikes: Dict[str, datetime] = {}
        
        # Track early pump alerts separately (different cooldown)
        self.alerted_early_pumps: Dict[str, datetime] = {}
        
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
        """Check a single exchange for price spikes using multi-factor scoring"""
        # Get top gainers AND losers for better coverage
        gainers = await self.exchange_client.get_top_gainers(
            exchange_name, 
            limit=50
        )
        
        losers = await self.exchange_client.get_top_losers(
            exchange_name,
            limit=30
        )
        
        # Combine and process all coins
        all_coins = gainers + losers
        # Remove duplicates based on symbol
        seen = set()
        unique_coins = []
        for coin in all_coins:
            if coin['symbol'] not in seen:
                seen.add(coin['symbol'])
                unique_coins.append(coin)
        
        for coin in unique_coins:
            symbol = coin['symbol']
            exchange = coin['exchange']
            price = coin['price']
            change_24h = coin['change_24h']
            volume = coin['volume_24h']
            
            cache_key = f"{symbol}:{exchange}"
            now = datetime.utcnow()
            
            # ===== UPDATE HISTORY =====
            # 1. Price History
            if cache_key not in self.price_history:
                self.price_history[cache_key] = []
            self.price_history[cache_key].append((price, now))
            
            # 2. Volume History
            if cache_key not in self.volume_history:
                self.volume_history[cache_key] = []
            self.volume_history[cache_key].append((volume, now))
            
            # 3. Momentum History (track price changes between checks)
            if cache_key not in self.momentum_history:
                self.momentum_history[cache_key] = []
            if len(self.price_history[cache_key]) >= 2:
                prev_price = self.price_history[cache_key][-2][0]
                if prev_price > 0:
                    change = ((price - prev_price) / prev_price) * 100
                    self.momentum_history[cache_key].append(change)
                    # Keep only last 10 changes
                    if len(self.momentum_history[cache_key]) > 10:
                        self.momentum_history[cache_key] = self.momentum_history[cache_key][-10:]
            
            # ===== CALCULATE SCORES =====
            pump_score = self._calculate_pump_score(cache_key, price, volume, change_24h, now)
            
            # ===== ORIGINAL DETECTION (still active) =====
            volatility_change = self._get_volatility_change(cache_key, price, now)
            is_pump = volatility_change >= self.MIN_VOLATILITY_THRESHOLD
            is_dump = volatility_change <= self.MIN_DUMP_THRESHOLD
            daily_spike = config.MIN_SPIKE_THRESHOLD <= change_24h <= config.MAX_SPIKE_THRESHOLD
            daily_dump = -config.MAX_SPIKE_THRESHOLD <= change_24h <= -config.MIN_SPIKE_THRESHOLD
            
            # ===== EARLY PUMP DETECTION (new!) =====
            if pump_score >= self.MIN_PUMP_SCORE:
                if await self._should_alert_early_pump(cache_key):
                    await self._send_early_pump_alert(
                        symbol, exchange, price, change_24h, volume, pump_score
                    )
                    self.alerted_early_pumps[cache_key] = now
            
            # ===== ORIGINAL ALERTS =====
            should_process = daily_spike or daily_dump or is_pump or is_dump
            
            if should_process:
                if await self._should_alert(cache_key, symbol, exchange, change_24h):
                    if is_pump:
                        await self._send_spike_alert(
                            symbol, exchange, price, change_24h, volume,
                            is_pump=True,
                            pump_change=volatility_change
                        )
                    elif is_dump:
                        await self._send_dump_alert(
                            symbol, exchange, price, change_24h, volume,
                            dump_change=volatility_change
                        )
                    elif daily_spike:
                        await self._send_spike_alert(
                            symbol, exchange, price, change_24h, volume,
                            is_pump=False,
                            pump_change=0.0
                        )
                    elif daily_dump:
                        await self._send_dump_alert(
                            symbol, exchange, price, change_24h, volume,
                            dump_change=change_24h,
                            is_daily=True
                        )
                    
                    self.alerted_spikes[cache_key] = now
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

    def _get_volatility_change(self, cache_key: str, current_price: float, current_time: datetime) -> float:
        """Helper to get the actual % change for the message"""
        history = self.price_history.get(cache_key, [])
        if not history: return 0.0
        
        target_time = current_time - timedelta(minutes=self.VOLATILITY_WINDOW_MINUTES)
        old_price = None
        for p, t in history:
            if t <= target_time:
                 old_price = p
            else:
                if old_price: break
        
        if old_price and old_price > 0:
            return ((current_price - old_price) / old_price) * 100
        return 0.0
    
    def _calculate_pump_score(self, cache_key: str, price: float, volume: float, change_24h: float, now: datetime) -> int:
        """Calculate pump probability score based on multiple factors"""
        score = 0
        
        # Factor 1: Volume Spike (30 points)
        volume_score = self._get_volume_spike_score(cache_key, volume)
        score += volume_score
        
        # Factor 2: Momentum - consecutive gains (25 points)
        momentum_score = self._get_momentum_score(cache_key)
        score += momentum_score
        
        # Factor 3: Short-term volatility (25 points)
        volatility_change = self._get_volatility_change(cache_key, price, now)
        if volatility_change >= 3.0:  # 3%+ gain in 5 mins
            score += self.SCORE_VOLATILITY
        elif volatility_change >= 1.5:  # 1.5%+ gain
            score += int(self.SCORE_VOLATILITY * 0.5)
        
        # Factor 4: Daily trend already positive (20 points)
        if change_24h >= 10:  # Already up 10%+ today
            score += self.SCORE_DAILY_TREND
        elif change_24h >= 5:  # Up 5%+
            score += int(self.SCORE_DAILY_TREND * 0.5)
        
        return score
    
    def _get_volume_spike_score(self, cache_key: str, current_volume: float) -> int:
        """Check if current volume is significantly higher than average"""
        history = self.volume_history.get(cache_key, [])
        
        if len(history) < 3:  # Need enough history
            return 0
        
        # Calculate average volume (excluding current)
        volumes = [v for v, t in history[:-1]]
        if not volumes:
            return 0
        
        avg_volume = sum(volumes) / len(volumes)
        
        if avg_volume <= 0:
            return 0
        
        volume_ratio = current_volume / avg_volume
        
        if volume_ratio >= self.VOLUME_SPIKE_MULTIPLIER * 2:  # 6x average
            return self.SCORE_VOLUME_SPIKE
        elif volume_ratio >= self.VOLUME_SPIKE_MULTIPLIER:  # 3x average
            return int(self.SCORE_VOLUME_SPIKE * 0.7)
        elif volume_ratio >= 2.0:  # 2x average
            return int(self.SCORE_VOLUME_SPIKE * 0.3)
        
        return 0
    
    def _get_momentum_score(self, cache_key: str) -> int:
        """Check for consecutive positive price movements"""
        history = self.momentum_history.get(cache_key, [])
        
        if len(history) < self.MOMENTUM_CANDLES_REQUIRED:
            return 0
        
        # Check last N entries for consecutive gains
        recent = history[-self.MOMENTUM_CANDLES_REQUIRED:]
        consecutive_gains = all(change > 0 for change in recent)
        
        if consecutive_gains:
            # Bonus if gains are increasing
            if len(recent) >= 2 and recent[-1] > recent[-2]:
                return self.SCORE_MOMENTUM
            return int(self.SCORE_MOMENTUM * 0.7)
        
        # Check for at least 2 consecutive gains
        if len(history) >= 2 and history[-1] > 0 and history[-2] > 0:
            return int(self.SCORE_MOMENTUM * 0.4)
        
        return 0
    
    async def _should_alert_early_pump(self, cache_key: str) -> bool:
        """Check if we should send early pump alert (30 min cooldown)"""
        if cache_key in self.alerted_early_pumps:
            last_alert = self.alerted_early_pumps[cache_key]
            if datetime.utcnow() - last_alert < timedelta(minutes=30):
                return False
        return True

    def cleanup_old_history(self):
        """Remove history older than window + buffer"""
        cutoff = datetime.utcnow() - timedelta(minutes=self.VOLATILITY_WINDOW_MINUTES + 10)
        
        # Clean price history
        for key in list(self.price_history.keys()):
            self.price_history[key] = [
                (p, t) for (p, t) in self.price_history[key]
                if t > cutoff
            ]
            if not self.price_history[key]:
                del self.price_history[key]
        
        # Clean volume history
        for key in list(self.volume_history.keys()):
            self.volume_history[key] = [
                (v, t) for (v, t) in self.volume_history[key]
                if t > cutoff
            ]
            if not self.volume_history[key]:
                del self.volume_history[key]
        
        # Clean old early pump alerts (older than 1 hour)
        alert_cutoff = datetime.utcnow() - timedelta(hours=1)
        for key in list(self.alerted_early_pumps.keys()):
            if self.alerted_early_pumps[key] < alert_cutoff:
                del self.alerted_early_pumps[key]
    
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
    
    async def _send_early_pump_alert(
        self,
        symbol: str,
        exchange: str,
        price: float,
        change_24h: float,
        volume: float,
        pump_score: int
    ):
        """Send early pump detection alert to all users with alerts enabled"""
        users = await self.db.get_users_with_alerts_enabled()
        
        if not users:
            return
        
        # Generate URL
        url = self.exchange_client._generate_trade_link(exchange, symbol)
        
        # Determine confidence level
        if pump_score >= self.HIGH_PUMP_SCORE:
            confidence = "HIGH"
            emoji = "🚨"
        else:
            confidence = "MEDIUM"
            emoji = "🔮"
        
        # Format message
        message = self.messages.format_early_pump_alert(
            symbol, exchange, price, change_24h, volume, pump_score, confidence, url
        )
        
        # Send to all users
        for user in users:
            try:
                user_id = user['id']
                
                # Check user's alert type preferences
                alert_types = await self.db.get_user_alert_types(user_id)
                if not alert_types.get('early_pumps', True):
                    continue  # User disabled early pump alerts
                
                # Check user's exchange preferences
                prefs = await self.db.get_user_preferences(user_id)
                if prefs:
                    allowed_exchanges = prefs.get('alert_exchanges', [])
                    if allowed_exchanges and exchange.lower() not in [e.lower() for e in allowed_exchanges]:
                        continue
                
                # Check if user is banned
                if await self.db.is_banned(user_id):
                    continue
                
                await self.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )
            except Exception as e:
                print(f"Failed to send early pump alert to {user.get('id')}: {e}")
    
    async def _send_spike_alert(
        self, 
        symbol: str, 
        exchange: str, 
        price: float, 
        change: float, 
        volume: float,
        is_pump: bool = False,
        pump_change: float = 0.0
    ):
        """Send spike alert to all users with alerts enabled"""
        # Get all users with alerts enabled (includes preferences from lookup)
        users = await self.db.get_users_with_alerts_enabled()
        
        if not users:
            return
            
        # Generate URL once
        url = self.exchange_client._generate_trade_link(exchange, symbol)
        
        # Format alert message
        if is_pump:
            message = self.messages.format_pump_alert(
                symbol, exchange, price, pump_change, volume, url
            )
            print(f"🚀 Sending PUMP alert: {symbol} on {exchange} (+{pump_change:.2f}% in 5m)")
        else:
            message = self.messages.format_spike_alert(
                symbol, exchange, price, change, volume, url
            )
            print(f"🚨 Sending spike alert: {symbol} on {exchange} (+{change}%)")
        
        # Send to valid users
        for user in users:
            try:
                user_id = user['id']
                
                # Check user's alert type preferences
                alert_types = await self.db.get_user_alert_types(user_id)
                if is_pump:
                    if not alert_types.get('confirmed_pumps', True):
                        continue  # User disabled confirmed pump alerts
                else:
                    if not alert_types.get('daily_spikes', True):
                        continue  # User disabled daily spike alerts
                
                # Check user preferences for exchange filter
                prefs = user.get('prefs', {})
                if prefs:
                    allowed_exchanges = prefs.get('alert_exchanges')
                    if allowed_exchanges is not None: 
                        if exchange not in allowed_exchanges:
                            continue
                
                await self.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN
                )
                await asyncio.sleep(0.05)  # Rate limiting
            except Exception as e:
                print(f"Failed to send alert to user {user['id']}: {e}")
    
    async def _send_dump_alert(
        self, 
        symbol: str, 
        exchange: str, 
        price: float, 
        change_24h: float, 
        volume: float,
        dump_change: float = 0.0,
        is_daily: bool = False
    ):
        """Send dump alert to all users with alerts enabled"""
        # Get all users with alerts enabled (includes preferences from lookup)
        users = await self.db.get_users_with_alerts_enabled()
        
        if not users:
            return
            
        # Generate URL once
        url = self.exchange_client._generate_trade_link(exchange, symbol)
        
        # Format alert message
        if is_daily:
            message = self.messages.format_daily_dump_alert(
                symbol, exchange, price, change_24h, volume, url
            )
            print(f"📉 Sending DAILY DUMP alert: {symbol} on {exchange} ({change_24h:.2f}%)")
        else:
            message = self.messages.format_dump_alert(
                symbol, exchange, price, dump_change, volume, url
            )
            print(f"💥 Sending DUMP alert: {symbol} on {exchange} ({dump_change:.2f}% in 5m)")
        
        # Send to valid users
        for user in users:
            try:
                user_id = user['id']
                
                # Check user's alert type preferences
                alert_types = await self.db.get_user_alert_types(user_id)
                if is_daily:
                    if not alert_types.get('daily_dumps', False):  # Default OFF
                        continue  # User disabled daily dump alerts
                else:
                    if not alert_types.get('dumps', True):
                        continue  # User disabled dump alerts
                
                # Check user preferences for exchange filter
                prefs = user.get('prefs', {})
                if prefs:
                    allowed_exchanges = prefs.get('alert_exchanges')
                    if allowed_exchanges is not None: 
                        if exchange not in allowed_exchanges:
                            continue
                
                await self.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN
                )
                await asyncio.sleep(0.05)  # Rate limiting
            except Exception as e:
                print(f"Failed to send dump alert to user {user_id}: {e}")
    
    def cleanup_old_alerts(self):
        """Clean up old entries from alerted_spikes cache"""
        cutoff = datetime.utcnow() - timedelta(hours=2)
        self.alerted_spikes = {
            k: v for k, v in self.alerted_spikes.items() 
            if v > cutoff
        }