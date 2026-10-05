import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from database.client import DatabaseClient
from telegram import Bot

from exchanges.client import ExchangeClient
from exchanges.websocket_client import WebSocketClient
from bot.messages import BotMessages
from config import config
from .broadcaster import AlertBroadcaster


class SpikeTracker:
    """Monitor exchanges for sudden price spikes/dumps and alert users"""

    # Original thresholds (still used for quick detection)
    MIN_VOLATILITY_THRESHOLD = 5.0  # 5% pump
    MIN_DUMP_THRESHOLD = -5.0       # -5% dump (negative value)
    VOLATILITY_WINDOW_MINUTES = 5   # In 5 minutes

    # Multi-Factor Scoring Thresholds
    VOLUME_SPIKE_MULTIPLIER = 3.0   # Recent trading pace must be 3x the 24h average to score
    MIN_VOLUME_WINDOW_SECONDS = 50  # Need at least this much time between samples
    MOMENTUM_CANDLES_REQUIRED = 3   # 3 consecutive gains = momentum
    MIN_PUMP_SCORE = 50             # Minimum score to trigger early pump alert
    HIGH_PUMP_SCORE = 70            # High confidence pump alert

    # Scoring weights
    SCORE_VOLUME_SPIKE = 30         # Points for volume spike
    SCORE_MOMENTUM = 25             # Points for momentum (consecutive gains)
    SCORE_VOLATILITY = 25           # Points for 5m volatility
    SCORE_DAILY_TREND = 20          # Points for positive 24h trend
    SCORE_ORDER_BOOK = 20           # Points for high buy pressure (>65%)
    SCORE_ORDER_BOOK_STRONG = 35    # Points for very high buy pressure (>80%)

    # Cooldowns per alert type. Daily alerts would otherwise repeat every
    # hour for as long as a coin stays in the 30-70% band.
    ALERT_COOLDOWNS = {
        "confirmed_pumps": timedelta(hours=1),
        "dumps": timedelta(hours=1),
        "daily_spikes": timedelta(hours=12),
        "daily_dumps": timedelta(hours=12),
    }
    EARLY_PUMP_COOLDOWN = timedelta(minutes=30)

    # Fast alerts (5-minute pumps/dumps) are time-critical: they are never
    # held back by other alerts for the coin, and they repeat within their
    # cooldown if the move keeps going this much further (in %)
    FAST_ALERT_TYPES = ("confirmed_pumps", "dumps")
    ESCALATION_THRESHOLD = 5.0

    # Daily alerts are informational: skip one if the coin was alerted for
    # any reason recently, so it doesn't repeat news the user already got
    DAILY_ALERT_GAP = timedelta(minutes=30)

    def __init__(self, exchange_client: ExchangeClient, bot: Bot, db: DatabaseClient):
        self.exchange_client = exchange_client
        self.ws_client = WebSocketClient()  # Initialize Sniper WebSocket
        self.bot = bot
        self.db = db
        self.messages = BotMessages()
        self.broadcaster = AlertBroadcaster(bot, db)

        # Cache previous prices for comparison
        # Format: { "symbol:exchange": [(price, timestamp), ...] }
        self.price_history: Dict[str, List[tuple]] = {}

        # 24h rolling volume samples, used to estimate the recent trading pace
        # Format: { "symbol:exchange": [(volume_24h, timestamp), ...] }
        self.volume_history: Dict[str, List[tuple]] = {}

        # Track consecutive price movements for momentum
        # Format: { "symbol:exchange": [change1, change2, change3, ...] }
        self.momentum_history: Dict[str, List[float]] = {}

        # Last alert time per (coin, alert type)
        self.alerted_spikes: Dict[Tuple[str, str], datetime] = {}

        # Price at the last alert per (coin, alert type), to detect escalation
        self.alert_prices: Dict[Tuple[str, str], float] = {}

        # Last alert time per coin, any type
        self.last_alert_for_coin: Dict[str, datetime] = {}

        # Track early pump alerts separately (different cooldown)
        self.alerted_early_pumps: Dict[str, datetime] = {}

        # Track WebSocket subscriptions (for Sniper Mode cleanup)
        # Format: { "symbol:exchange": timestamp_added }
        self.active_subscriptions: Dict[str, datetime] = {}

        self.is_running = False

    async def start(self):
        """Start the monitoring loop"""
        self.is_running = True
        print("🔍 Spike tracker started")

        # Start WebSocket Client
        await self.ws_client.start()

        while self.is_running:
            try:
                await self._check_all_exchanges()
                self.cleanup_old_history()
            except Exception as e:
                print(f"Error in spike tracker: {e}")
            await asyncio.sleep(config.SPIKE_CHECK_INTERVAL)

    async def stop(self):
        """Stop the monitoring loop"""
        self.is_running = False
        await self.ws_client.stop()
        print("🛑 Spike tracker stopped")

    async def _check_all_exchanges(self):
        """Check all exchanges for spikes"""
        # Load recipients once per cycle rather than once per alert
        await self.broadcaster.refresh()

        # Fetch all exchanges concurrently; process sequentially
        results = await asyncio.gather(
            *(self._fetch_movers(name) for name in config.EXCHANGES),
            return_exceptions=True
        )

        for exchange_name, coins in zip(config.EXCHANGES, results):
            if isinstance(coins, Exception):
                print(f"Error checking {exchange_name}: {coins}")
                continue
            for coin in coins:
                try:
                    await self._process_coin(coin)
                except Exception as e:
                    print(f"Error processing {coin.get('symbol')} on {exchange_name}: {e}")

    async def _fetch_movers(self, exchange_name: str) -> List[Dict]:
        """Top gainers and losers for an exchange, de-duplicated"""
        # Both calls share one cached ticker fetch
        gainers = await self.exchange_client.get_top_gainers(exchange_name, limit=50)
        losers = await self.exchange_client.get_top_losers(exchange_name, limit=30)

        seen = set()
        unique_coins = []
        for coin in gainers + losers:
            if coin['symbol'] not in seen:
                seen.add(coin['symbol'])
                unique_coins.append(coin)
        return unique_coins

    async def _process_coin(self, coin: Dict):
        """Update history for one coin and send any alerts it triggers"""
        symbol = coin['symbol']
        exchange = coin['exchange']
        price = coin['price']
        change_24h = coin['change_24h']
        volume = coin['volume_24h']

        cache_key = f"{symbol}:{exchange}"
        now = datetime.utcnow()

        self._record_history(cache_key, price, volume, now)

        volatility_change = self._get_volatility_change(cache_key, price, now)

        # ===== EARLY PUMP DETECTION =====
        pump_score = await self._calculate_pump_score(
            cache_key, volume, change_24h, volatility_change
        )
        # Only rising coins can be early pumps - volume and order book
        # signals alone also light up during sell-offs
        if pump_score >= self.MIN_PUMP_SCORE and volatility_change > 0:
            if self._should_alert_early_pump(cache_key, now):
                await self._send_early_pump_alert(
                    symbol, exchange, price, change_24h, volume, pump_score
                )
                self.alerted_early_pumps[cache_key] = now

        # ===== THRESHOLD ALERTS =====
        alert_type = self._classify_move(volatility_change, change_24h)
        if alert_type and await self._should_alert(cache_key, symbol, exchange, alert_type, price, now):
            if alert_type == "confirmed_pumps":
                message = self.messages.format_pump_alert(
                    symbol, exchange, price, volatility_change, volume, coin.get('url', '')
                )
                print(f"🚀 PUMP: {symbol} on {exchange} (+{volatility_change:.2f}% in 5m)")
            elif alert_type == "dumps":
                message = self.messages.format_dump_alert(
                    symbol, exchange, price, volatility_change, volume, coin.get('url', '')
                )
                print(f"💥 DUMP: {symbol} on {exchange} ({volatility_change:.2f}% in 5m)")
            elif alert_type == "daily_spikes":
                message = self.messages.format_spike_alert(
                    symbol, exchange, price, change_24h, volume, coin.get('url', '')
                )
                print(f"🔥 DAILY SPIKE: {symbol} on {exchange} (+{change_24h:.2f}%)")
            else:
                message = self.messages.format_daily_dump_alert(
                    symbol, exchange, price, change_24h, volume, coin.get('url', '')
                )
                print(f"📉 DAILY DUMP: {symbol} on {exchange} ({change_24h:.2f}%)")

            await self.broadcaster.broadcast(message, alert_type, exchange=exchange, symbol=symbol)

            self.alerted_spikes[(cache_key, alert_type)] = now
            self.alert_prices[(cache_key, alert_type)] = price
            self.last_alert_for_coin[cache_key] = now
            change = volatility_change if alert_type in ("confirmed_pumps", "dumps") else change_24h
            await self.db.save_alert(symbol, exchange, change, alert_type=alert_type)

    def _classify_move(self, volatility_change: float, change_24h: float) -> Optional[str]:
        """Return the highest-priority alert type this move qualifies for"""
        if volatility_change >= self.MIN_VOLATILITY_THRESHOLD:
            return "confirmed_pumps"
        if volatility_change <= self.MIN_DUMP_THRESHOLD:
            return "dumps"
        if config.MIN_SPIKE_THRESHOLD <= change_24h <= config.MAX_SPIKE_THRESHOLD:
            return "daily_spikes"
        if -config.MAX_SPIKE_THRESHOLD <= change_24h <= -config.MIN_SPIKE_THRESHOLD:
            return "daily_dumps"
        return None

    def _record_history(self, cache_key: str, price: float, volume: float, now: datetime):
        """Append the latest price/volume sample and update momentum"""
        prices = self.price_history.setdefault(cache_key, [])
        prices.append((price, now))
        self.volume_history.setdefault(cache_key, []).append((volume, now))

        # Momentum: price change between consecutive checks
        if len(prices) >= 2:
            prev_price = prices[-2][0]
            if prev_price > 0:
                momentum = self.momentum_history.setdefault(cache_key, [])
                momentum.append(((price - prev_price) / prev_price) * 100)
                if len(momentum) > 10:
                    del momentum[:-10]

    def _sample_from_window_ago(self, history: List[tuple], current_time: datetime) -> Optional[tuple]:
        """
        Latest sample at least VOLATILITY_WINDOW_MINUTES old, or None if we
        don't have that much history yet.
        """
        target_time = current_time - timedelta(minutes=self.VOLATILITY_WINDOW_MINUTES)
        found = None
        for sample in history:
            if sample[1] <= target_time:
                found = sample
            else:
                break
        return found

    def _get_volatility_change(self, cache_key: str, current_price: float, current_time: datetime) -> float:
        """% price change over the volatility window (0 if not enough history)"""
        sample = self._sample_from_window_ago(self.price_history.get(cache_key, []), current_time)
        if sample and sample[0] > 0:
            return ((current_price - sample[0]) / sample[0]) * 100
        return 0.0

    async def _calculate_pump_score(self, cache_key: str, volume: float, change_24h: float,
                                    volatility_change: float) -> int:
        """Calculate pump probability score based on multiple factors"""
        score = 0
        symbol, exchange = cache_key.split(":", 1)

        # Factor 1: Volume Spike (30 points)
        score += self._get_volume_spike_score(cache_key)

        # Factor 2: Momentum - consecutive gains (25 points)
        score += self._get_momentum_score(cache_key)

        # Factor 3: Short-term volatility (25 points)
        if volatility_change >= 3.0:  # 3%+ gain in 5 mins
            score += self.SCORE_VOLATILITY
        elif volatility_change >= 1.5:  # 1.5%+ gain
            score += int(self.SCORE_VOLATILITY * 0.5)

        # Factor 4: Daily trend already positive (20 points)
        if change_24h >= 10:  # Already up 10%+ today
            score += self.SCORE_DAILY_TREND
        elif change_24h >= 5:  # Up 5%+
            score += int(self.SCORE_DAILY_TREND * 0.5)

        # Factor 5: Order Book Imbalance (Sniper Mode)
        buy_pressure = await self.ws_client.get_order_book_imbalance(exchange, symbol)
        if buy_pressure >= 80:
            score += self.SCORE_ORDER_BOOK_STRONG
        elif buy_pressure >= 65:
            score += self.SCORE_ORDER_BOOK

        # --- SNIPER MODE TRIGGER ---
        # If score is promising but not yet an alert (e.g. 20-49),
        # subscribe to WebSocket to get that Order Book boost for next check!
        if 20 <= score < self.MIN_PUMP_SCORE and self.ws_client.supports(exchange):
            if cache_key not in self.active_subscriptions:
                asyncio.create_task(self.ws_client.subscribe_order_book(exchange, symbol))
            # Add or refresh, keeping the subscription alive
            self.active_subscriptions[cache_key] = datetime.utcnow()

        return score

    def _get_volume_spike_ratio(self, cache_key: str) -> float:
        """
        How fast the coin is trading now compared with its 24h average pace.

        Exchanges only report a rolling 24h volume. Between two samples that
        figure gains whatever traded in the interval and loses what traded
        24h earlier (approximated by the average pace), so:
            recent volume ≈ (vol_now - vol_then) + average_pace * dt
        """
        history = self.volume_history.get(cache_key, [])
        if len(history) < 2:
            return 0.0

        current_volume, current_time = history[-1]
        reference = self._sample_from_window_ago(history, current_time) or history[0]
        previous_volume, previous_time = reference

        dt = (current_time - previous_time).total_seconds()
        if dt < self.MIN_VOLUME_WINDOW_SECONDS or current_volume <= 0:
            return 0.0

        expected = current_volume / 86400 * dt
        recent = (current_volume - previous_volume) + expected
        return max(recent, 0.0) / expected

    def _get_volume_spike_score(self, cache_key: str) -> int:
        """Score based on recent trading pace vs the 24h average"""
        volume_ratio = self._get_volume_spike_ratio(cache_key)

        if volume_ratio >= self.VOLUME_SPIKE_MULTIPLIER * 2:  # 6x average pace
            return self.SCORE_VOLUME_SPIKE
        elif volume_ratio >= self.VOLUME_SPIKE_MULTIPLIER:  # 3x average pace
            return int(self.SCORE_VOLUME_SPIKE * 0.7)
        elif volume_ratio >= 2.0:  # 2x average pace
            return int(self.SCORE_VOLUME_SPIKE * 0.3)

        return 0

    def _get_momentum_score(self, cache_key: str) -> int:
        """Check for consecutive positive price movements"""
        history = self.momentum_history.get(cache_key, [])

        if len(history) < self.MOMENTUM_CANDLES_REQUIRED:
            return 0

        # Check last N entries for consecutive gains
        recent = history[-self.MOMENTUM_CANDLES_REQUIRED:]
        if all(change > 0 for change in recent):
            # Bonus if gains are increasing
            if recent[-1] > recent[-2]:
                return self.SCORE_MOMENTUM
            return int(self.SCORE_MOMENTUM * 0.7)

        # Check for at least 2 consecutive gains
        if history[-1] > 0 and history[-2] > 0:
            return int(self.SCORE_MOMENTUM * 0.4)

        return 0

    def _should_alert_early_pump(self, cache_key: str, now: datetime) -> bool:
        """Check if we should send early pump alert (30 min cooldown)"""
        last_alert = self.alerted_early_pumps.get(cache_key)
        return last_alert is None or now - last_alert >= self.EARLY_PUMP_COOLDOWN

    async def _should_alert(self, cache_key: str, symbol: str, exchange: str,
                            alert_type: str, price: float, now: datetime) -> bool:
        """Determine if we should send an alert of this type for this coin"""
        key = (cache_key, alert_type)

        if alert_type not in self.FAST_ALERT_TYPES:
            last_any = self.last_alert_for_coin.get(cache_key)
            if last_any and now - last_any < self.DAILY_ALERT_GAP:
                return False

        cooldown = self.ALERT_COOLDOWNS[alert_type]
        last = self.alerted_spikes.get(key)
        if last and now - last < cooldown:
            # Within cooldown, only a move that keeps going is worth another alert
            return self._has_escalated(key, alert_type, price)

        # Database check covers alerts sent before a restart
        if not last and await self.db.has_recent_alert(
            symbol, exchange, hours=cooldown.total_seconds() / 3600, alert_type=alert_type
        ):
            # Remember it so we don't query again every cycle
            self.alerted_spikes[key] = now
            self.alert_prices[key] = price
            return False

        return True

    def _has_escalated(self, key: Tuple[str, str], alert_type: str, price: float) -> bool:
        """Has a fast move kept going well past the price of its last alert?"""
        if alert_type not in self.FAST_ALERT_TYPES:
            return False
        last_price = self.alert_prices.get(key)
        if not last_price or last_price <= 0:
            return False
        move = ((price - last_price) / last_price) * 100
        if alert_type == "confirmed_pumps":
            return move >= self.ESCALATION_THRESHOLD
        return move <= -self.ESCALATION_THRESHOLD

    def cleanup_old_history(self):
        """Drop history and cooldown entries that can no longer matter"""
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=self.VOLATILITY_WINDOW_MINUTES + 10)

        for store in (self.price_history, self.volume_history):
            for key in list(store.keys()):
                store[key] = [entry for entry in store[key] if entry[1] > cutoff]
                if not store[key]:
                    del store[key]

        # Momentum for coins that dropped out of the movers list
        for key in list(self.momentum_history.keys()):
            if key not in self.price_history:
                del self.momentum_history[key]

        early_cutoff = now - self.EARLY_PUMP_COOLDOWN
        self.alerted_early_pumps = {
            k: v for k, v in self.alerted_early_pumps.items() if v > early_cutoff
        }

        self.alerted_spikes = {
            k: v for k, v in self.alerted_spikes.items()
            if now - v < self.ALERT_COOLDOWNS[k[1]]
        }
        self.alert_prices = {
            k: v for k, v in self.alert_prices.items() if k in self.alerted_spikes
        }

        gap_cutoff = now - self.DAILY_ALERT_GAP
        self.last_alert_for_coin = {
            k: v for k, v in self.last_alert_for_coin.items() if v > gap_cutoff
        }

        # "Sniper Mode" cleanup: stop watching order books that went quiet
        ws_cutoff = now - timedelta(minutes=15)
        for key in list(self.active_subscriptions.keys()):
            if self.active_subscriptions[key] < ws_cutoff:
                symbol, exchange = key.split(":", 1)
                asyncio.create_task(self.ws_client.unsubscribe_order_book(exchange, symbol))
                del self.active_subscriptions[key]

    async def _send_early_pump_alert(
        self,
        symbol: str,
        exchange: str,
        price: float,
        change_24h: float,
        volume: float,
        pump_score: int
    ):
        """Send early pump detection alert to subscribed users"""
        if not self.broadcaster.has_recipients():
            return

        url = self.exchange_client._generate_trade_link(exchange, symbol)
        confidence = "HIGH" if pump_score >= self.HIGH_PUMP_SCORE else "MEDIUM"

        message = self.messages.format_early_pump_alert(
            symbol, exchange, price, change_24h, volume, pump_score, confidence, url
        )
        print(f"🔮 EARLY PUMP ({confidence}, {pump_score}): {symbol} on {exchange}")

        await self.broadcaster.broadcast(message, "early_pumps", exchange=exchange, symbol=symbol)
