import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Dict, List, Optional, Tuple
from database.client import DatabaseClient
from telegram import Bot

from exchanges.client import ExchangeClient
from exchanges.websocket_client import WebSocketClient
from bot.messages import BotMessages
from config import config
from .broadcaster import AlertBroadcaster
from .limiter import AlertLimiter


@dataclass
class Observation:
    """One coin on one exchange in the current scan"""
    symbol: str
    exchange: str
    price: float
    change_24h: float
    volume: float
    move: Optional[float]  # % change over the last 5 minutes (None until we have 5 min of history)
    url: str


class SpikeTracker:
    """
    Monitor exchanges for sudden price spikes/dumps and alert users.

    Each scan works in two passes:
      1. Record every coin's price on every exchange.
      2. Measure how the whole market moved, then judge each coin ONCE across
         all exchanges, by how much it beat the market.

    This keeps alerts meaningful: thin, illiquid coins are ignored, a coin
    moving on five exchanges is one alert, and a market-wide move is one
    summary instead of hundreds of alerts.
    """

    # 5-minute pump/dump: move relative to the market
    MIN_VOLATILITY_THRESHOLD = 5.0  # 5% pump
    MIN_DUMP_THRESHOLD = -5.0       # -5% dump (negative value)
    VOLATILITY_WINDOW_MINUTES = 5   # In 5 minutes

    # Only alert on coins people can actually trade: at least this much
    # 24h volume (USD) on one exchange. Thinner coins swing 5% on a single
    # order. Watchlist coins below this still alert, but only their watchers.
    MIN_ALERT_VOLUME_USD = 3_000_000

    # Market-wide moves: when the median liquid coin moves this much in
    # 5 minutes, send one summary and judge coins relative to the market
    MARKET_MOVE_THRESHOLD = 1.5
    MARKET_MIN_COINS = 30           # Need this many liquid coins to measure the market
    MARKET_BREADTH_MOVE = 1.0       # A coin "moved with the market" if it moved this much the same way
    MARKET_ALERT_COOLDOWN = timedelta(minutes=30)
    MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")

    # Multi-Factor Scoring Thresholds
    VOLUME_SPIKE_MULTIPLIER = 3.0   # Recent trading pace must be 3x the 24h average to score
    MIN_VOLUME_WINDOW_SECONDS = 50  # Need at least this much time between samples
    MOMENTUM_CANDLES_REQUIRED = 3   # 3 consecutive gains = momentum
    MIN_PUMP_SCORE = 50             # Minimum score to trigger early pump alert
    HIGH_PUMP_SCORE = 70            # High confidence pump alert
    EARLY_MIN_RELATIVE_MOVE = 1.5   # Early signals need the coin itself to be beating the market

    # Scoring weights
    SCORE_VOLUME_SPIKE = 30         # Points for volume spike
    SCORE_MOMENTUM = 25             # Points for momentum (consecutive gains)
    SCORE_VOLATILITY = 25           # Points for 5m volatility
    SCORE_DAILY_TREND = 20          # Points for positive 24h trend
    SCORE_ORDER_BOOK = 20           # Points for high buy pressure (>65%)
    SCORE_ORDER_BOOK_STRONG = 35    # Points for very high buy pressure (>80%)

    # Cooldowns per alert type, per coin (across all exchanges). Daily alerts
    # would otherwise repeat while a coin stays in the 30-70% band.
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

    def __init__(self, exchange_client: ExchangeClient, bot: Bot, db: DatabaseClient,
                 limiter: Optional[AlertLimiter] = None):
        self.exchange_client = exchange_client
        self.ws_client = WebSocketClient()  # Initialize Sniper WebSocket
        self.bot = bot
        self.db = db
        self.messages = BotMessages()
        self.broadcaster = AlertBroadcaster(bot, db, limiter)

        # Cache previous prices for comparison
        # Format: { "symbol:exchange": [(price, timestamp), ...] }
        self.price_history: Dict[str, List[tuple]] = {}

        # 24h rolling volume samples, used to estimate the recent trading pace
        # Format: { "symbol:exchange": [(volume_24h, timestamp), ...] }
        self.volume_history: Dict[str, List[tuple]] = {}

        # Track consecutive price movements for momentum
        # Format: { "symbol:exchange": [change1, change2, change3, ...] }
        self.momentum_history: Dict[str, List[float]] = {}

        # Last alert time per (symbol, alert type) - per coin, across exchanges
        self.alerted_spikes: Dict[Tuple[str, str], datetime] = {}

        # Price at the last alert per (symbol, alert type), to detect escalation
        self.alert_prices: Dict[Tuple[str, str], float] = {}

        # Last alert time per symbol, any type
        self.last_alert_for_coin: Dict[str, datetime] = {}

        # Early pump alerts per symbol (different cooldown)
        self.alerted_early_pumps: Dict[str, datetime] = {}

        # Last market-wide summary per direction ("up" / "down")
        self.market_alerted: Dict[str, datetime] = {}

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

    # ==================== SCAN ====================

    async def _check_all_exchanges(self):
        """One scan: record every coin, then decide on alerts once per coin"""
        # Load recipients once per cycle rather than once per alert
        await self.broadcaster.refresh()

        results = await asyncio.gather(
            *(self.exchange_client.get_all_tickers(name) for name in config.EXCHANGES),
            return_exceptions=True
        )

        # Pass 1: record every active pair (not just today's top movers - a
        # coin flat on the day that suddenly moves is what alerts are for)
        now = datetime.utcnow()
        groups: Dict[str, List[Observation]] = {}
        for exchange_name, coins in zip(config.EXCHANGES, results):
            if isinstance(coins, Exception):
                print(f"Error checking {exchange_name}: {coins}")
                continue
            for coin in coins:
                try:
                    obs = self._observe(coin, now)
                except Exception as e:
                    print(f"Error processing {coin.get('symbol')} on {exchange_name}: {e}")
                    continue
                groups.setdefault(obs.symbol, []).append(obs)
            # Let Telegram commands run between exchanges
            await asyncio.sleep(0)

        # Pass 2: measure the market, then judge each coin once
        market_move, moved, total = self._measure_market(groups)
        await self._maybe_send_market_alert(groups, market_move, moved, total, now)

        for symbol, observations in groups.items():
            try:
                await self._evaluate_symbol(symbol, observations, market_move, now)
            except Exception as e:
                print(f"Error evaluating {symbol}: {e}")

        # Summaries for users who hit their hourly cap
        await self.broadcaster.flush_digests()

    async def _process_coin(self, coin: Dict):
        """Record and judge a single coin on its own (no market context)"""
        now = datetime.utcnow()
        obs = self._observe(coin, now)
        await self._evaluate_symbol(obs.symbol, [obs], 0.0, now)

    def _observe(self, coin: Dict, now: datetime) -> Observation:
        """Record one coin's latest price and volume"""
        symbol = coin['symbol']
        exchange = coin['exchange']
        price = coin['price']
        volume = coin['volume_24h']
        cache_key = f"{symbol}:{exchange}"

        self._record_history(cache_key, price, volume, now)
        sample = self._sample_from_window_ago(self.price_history.get(cache_key, []), now)
        move = ((price - sample[0]) / sample[0]) * 100 if sample and sample[0] > 0 else None

        return Observation(
            symbol=symbol, exchange=exchange, price=price,
            change_24h=coin['change_24h'], volume=volume, move=move,
            url=coin.get('url', ''),
        )

    @staticmethod
    def _representative(observations: List[Observation]) -> Observation:
        """The coin's busiest exchange: its numbers are used for decisions"""
        return max(observations, key=lambda o: o.volume or 0)

    # ==================== MARKET-WIDE MOVES ====================

    def _measure_market(self, groups: Dict[str, List[Observation]]) -> Tuple[float, int, int]:
        """
        Median 5-minute move of liquid coins (0 if there aren't enough), plus
        how many of them moved the same way and how many were measured.
        """
        moves = []
        for observations in groups.values():
            rep = self._representative(observations)
            if rep.move is not None and rep.volume >= self.MIN_ALERT_VOLUME_USD:
                moves.append(rep.move)
        if len(moves) < self.MARKET_MIN_COINS:
            return 0.0, 0, len(moves)

        market = median(moves)
        if market >= 0:
            moved = sum(1 for m in moves if m >= self.MARKET_BREADTH_MOVE)
        else:
            moved = sum(1 for m in moves if m <= -self.MARKET_BREADTH_MOVE)
        return market, moved, len(moves)

    async def _maybe_send_market_alert(self, groups: Dict[str, List[Observation]], market_move: float,
                                       moved: int, total: int, now: datetime):
        """One summary message when the whole market moves together"""
        if abs(market_move) < self.MARKET_MOVE_THRESHOLD:
            return
        direction = "up" if market_move > 0 else "down"
        last = self.market_alerted.get(direction)
        if last and now - last < self.MARKET_ALERT_COOLDOWN:
            return

        reps = {
            symbol: self._representative(obs) for symbol, obs in groups.items()
        }
        majors = [(s, reps[s].move) for s in self.MAJORS if s in reps and reps[s].move is not None]
        liquid = [
            (s, r.move) for s, r in reps.items()
            if r.move is not None and r.volume >= self.MIN_ALERT_VOLUME_USD
        ]
        liquid.sort(key=lambda x: x[1], reverse=market_move > 0)
        leaders = liquid[:5]

        message = self.messages.format_market_move(market_move, moved, total, majors, leaders)
        print(f"🌍 MARKET {direction.upper()}: median {market_move:+.2f}% in 5m ({moved}/{total} coins)")
        await self.broadcaster.broadcast(message, "market_moves", priority=True)
        self.market_alerted[direction] = now

    # ==================== PER-COIN DECISIONS ====================

    async def _evaluate_symbol(self, symbol: str, observations: List[Observation],
                               market_move: float, now: datetime):
        """Decide on alerts for one coin, looking at all its exchanges at once"""
        rep = self._representative(observations)
        liquid = rep.volume >= self.MIN_ALERT_VOLUME_USD
        watchers_only = not liquid
        if watchers_only and not self.broadcaster.watchers_of(symbol):
            return  # Too thin to trade and nobody is watching it

        relative = rep.move - market_move if rep.move is not None else None
        venues = [(o.exchange, o.url) for o in sorted(observations, key=lambda o: -(o.volume or 0))]
        exchanges = [o.exchange for o in observations]

        # ===== EARLY PUMP DETECTION =====
        if relative is not None and relative >= self.EARLY_MIN_RELATIVE_MOVE:
            pump_score = await self._calculate_pump_score(
                f"{symbol}:{rep.exchange}", rep.volume, rep.change_24h, relative
            )
            if pump_score >= self.MIN_PUMP_SCORE and self._should_alert_early_pump(symbol, now):
                await self._send_early_pump_alert(
                    rep, pump_score, venues, exchanges, market_move, watchers_only
                )
                self.alerted_early_pumps[symbol] = now

        # ===== THRESHOLD ALERTS =====
        alert_type = self._classify_move(relative or 0.0, rep.change_24h)
        if not alert_type or not await self._should_alert(symbol, alert_type, rep.price, now):
            return

        args = dict(venues=venues)
        if alert_type == "confirmed_pumps":
            message = self.messages.format_pump_alert(
                symbol, rep.exchange, rep.price, rep.move, rep.volume, rep.url,
                change_24h=rep.change_24h, market_move=market_move, **args
            )
            print(f"🚀 PUMP: {symbol} ({rep.move:+.2f}% in 5m, {relative:+.2f}% vs market)")
        elif alert_type == "dumps":
            message = self.messages.format_dump_alert(
                symbol, rep.exchange, rep.price, rep.move, rep.volume, rep.url,
                change_24h=rep.change_24h, market_move=market_move, **args
            )
            print(f"💥 DUMP: {symbol} ({rep.move:+.2f}% in 5m, {relative:+.2f}% vs market)")
        elif alert_type == "daily_spikes":
            message = self.messages.format_spike_alert(
                symbol, rep.exchange, rep.price, rep.change_24h, rep.volume, rep.url, **args
            )
            print(f"🔥 DAILY SPIKE: {symbol} ({rep.change_24h:+.2f}%)")
        else:
            message = self.messages.format_daily_dump_alert(
                symbol, rep.exchange, rep.price, rep.change_24h, rep.volume, rep.url, **args
            )
            print(f"📉 DAILY DUMP: {symbol} ({rep.change_24h:+.2f}%)")

        await self.broadcaster.broadcast(
            message, alert_type, exchange=exchanges, symbol=symbol, watchers_only=watchers_only
        )

        self.alerted_spikes[(symbol, alert_type)] = now
        self.alert_prices[(symbol, alert_type)] = rep.price
        self.last_alert_for_coin[symbol] = now
        change = rep.move if alert_type in self.FAST_ALERT_TYPES else rep.change_24h
        await self.db.save_alert(symbol, rep.exchange, change, alert_type=alert_type)

    def _classify_move(self, relative_move: float, change_24h: float) -> Optional[str]:
        """Return the highest-priority alert type this move qualifies for"""
        if relative_move >= self.MIN_VOLATILITY_THRESHOLD:
            return "confirmed_pumps"
        if relative_move <= self.MIN_DUMP_THRESHOLD:
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
        symbol, exchange = cache_key.split(":", 1)

        # Short-term factors: what is happening right now
        # Factor 1: Volume Spike (30 points)
        short_term = self._get_volume_spike_score(cache_key)

        # Factor 2: Momentum - consecutive gains (25 points)
        short_term += self._get_momentum_score(cache_key)

        # Factor 3: Short-term volatility (25 points)
        if volatility_change >= 3.0:  # 3%+ gain in 5 mins
            short_term += self.SCORE_VOLATILITY
        elif volatility_change >= 1.5:  # 1.5%+ gain
            short_term += int(self.SCORE_VOLATILITY * 0.5)
        score = short_term

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
        # If score is promising but not yet an alert (e.g. 20-49), and something
        # is actually moving now (a big daily gain alone isn't enough), subscribe
        # to the order book to get that boost for the next check
        if (20 <= score < self.MIN_PUMP_SCORE and short_term > 0
                and self.ws_client.supports(exchange)):
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

    def _should_alert_early_pump(self, symbol: str, now: datetime) -> bool:
        """30 min cooldown, and no 'early' signal once a pump was already confirmed"""
        last_alert = self.alerted_early_pumps.get(symbol)
        if last_alert and now - last_alert < self.EARLY_PUMP_COOLDOWN:
            return False
        confirmed = self.alerted_spikes.get((symbol, "confirmed_pumps"))
        return not (confirmed and now - confirmed < self.EARLY_PUMP_COOLDOWN)

    async def _should_alert(self, symbol: str, alert_type: str, price: float, now: datetime) -> bool:
        """Determine if we should send an alert of this type for this coin (any exchange)"""
        key = (symbol, alert_type)

        if alert_type not in self.FAST_ALERT_TYPES:
            last_any = self.last_alert_for_coin.get(symbol)
            if last_any and now - last_any < self.DAILY_ALERT_GAP:
                return False

        cooldown = self.ALERT_COOLDOWNS[alert_type]
        last = self.alerted_spikes.get(key)
        if last and now - last < cooldown:
            # Within cooldown, only a move that keeps going is worth another alert
            return self._has_escalated(key, alert_type, price)

        # Database check covers alerts sent before a restart
        if not last and await self.db.has_recent_alert(
            symbol, None, hours=cooldown.total_seconds() / 3600, alert_type=alert_type
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

        self.market_alerted = {
            k: v for k, v in self.market_alerted.items() if now - v < self.MARKET_ALERT_COOLDOWN
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

    async def _send_early_pump_alert(self, rep: Observation, pump_score: int,
                                     venues: List[Tuple[str, str]], exchanges: List[str],
                                     market_move: float, watchers_only: bool):
        """Send early pump detection alert to subscribed users"""
        if not self.broadcaster.has_recipients():
            return

        confidence = "HIGH" if pump_score >= self.HIGH_PUMP_SCORE else "MEDIUM"
        message = self.messages.format_early_pump_alert(
            rep.symbol, rep.exchange, rep.price, rep.change_24h, rep.volume, pump_score,
            confidence, rep.url, venues=venues, change_5m=rep.move, market_move=market_move
        )
        print(f"🔮 EARLY PUMP ({confidence}, {pump_score}): {rep.symbol}")

        await self.broadcaster.broadcast(
            message, "early_pumps", exchange=exchanges, symbol=rep.symbol, watchers_only=watchers_only
        )
