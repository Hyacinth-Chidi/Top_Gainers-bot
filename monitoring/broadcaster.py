import asyncio
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set, Tuple, Union
from telegram import Bot

from database.client import DatabaseClient, DEFAULT_ALERT_TYPES, normalize_symbol
from bot.utils import safe_send, SendResult
from bot.messages import BotMessages
from .limiter import AlertLimiter, DEFAULT_LIMITER, FAST, SLOW

# Informational alerts get a smaller hourly allowance than time-critical ones
SLOW_ALERT_TYPES = ("daily_spikes", "daily_dumps")


class AlertBroadcaster:
    """
    Delivers alerts to subscribed users.

    Recipients, bans and watchlists are loaded once per monitoring cycle
    (via refresh) instead of querying the database for every user on
    every alert.

    Each user gets a limited number of alerts per hour (more for urgent
    pumps/dumps than for daily movers); the rest are collected into one
    summary message. Watchlist alerts and
    priority alerts (market-wide summaries) always go straight through.
    """

    # Telegram allows ~30 messages/second overall. Send in parallel batches
    # of this size, at most one batch per second, so alerts reach everyone fast.
    BATCH_SIZE = 25
    BATCH_INTERVAL = 1.0
    # Star goes on the first line so it shows in the phone notification
    WATCHLIST_PREFIX = "⭐ "

    def __init__(self, bot: Bot, db: DatabaseClient, limiter: Optional[AlertLimiter] = None):
        self.bot = bot
        self.db = db
        self.limiter = limiter or DEFAULT_LIMITER
        self._users: List[Dict] = []
        self._banned: Set[int] = set()
        self._watchers: Dict[str, Set[int]] = {}

    async def refresh(self):
        """Reload recipients, bans and watchlists from the database"""
        self._users = await self.db.get_users_with_alerts_enabled()
        self._banned = await self.db.get_banned_user_ids()
        self._watchers = await self.db.get_watchlists_by_symbol()

    def has_recipients(self) -> bool:
        return bool(self._users)

    def watchers_of(self, symbol: Optional[str]) -> Set[int]:
        return self._watchers.get(normalize_symbol(symbol), set()) if symbol else set()

    async def broadcast(
        self,
        message: str,
        alert_type: str,
        exchange: Union[str, Iterable[str], None] = None,
        symbol: Optional[str] = None,
        priority: bool = False,
        watchers_only: bool = False,
    ) -> int:
        """
        Send an alert to every eligible user. Returns the number delivered now.

        - `exchange` may be one exchange or several (a coin moving on many
          exchanges is one alert); users get it if they follow any of them.
        - Watchlist users get it tagged ⭐, even from exchanges they filtered out.
        - `watchers_only` limits it to users watching the symbol.
        - `priority` alerts skip the hourly cap.
        """
        if isinstance(exchange, str):
            exchanges = [exchange.lower()]
        else:
            exchanges = [e.lower() for e in exchange] if exchange else []
        watchers = self.watchers_of(symbol)
        now = datetime.utcnow()
        headline = message.splitlines()[0] if message else ""
        kind = SLOW if alert_type in SLOW_ALERT_TYPES else FAST

        # Work out who gets the alert (watchlist users first - it's their coin)
        recipients: List[Tuple[bool, int]] = []
        for user in self._users:
            user_id = user.get('id')
            if user_id is None or user_id in self._banned:
                continue

            prefs = user.get('prefs') or {}
            alert_types = {**DEFAULT_ALERT_TYPES, **prefs.get('alert_types', {})}
            if not alert_types.get(alert_type, False):
                continue

            is_watcher = user_id in watchers
            if watchers_only and not is_watcher:
                continue
            if exchanges and not is_watcher:
                allowed = prefs.get('alert_exchanges')
                if allowed is not None:
                    allowed = {e.lower() for e in allowed}
                    if not any(e in allowed for e in exchanges):
                        continue

            # Over the hourly cap: save it for the user's summary instead
            if not (priority or is_watcher) and not self.limiter.allow(user_id, now, kind):
                self.limiter.defer(user_id, headline, now)
                continue

            recipients.append((is_watcher, user_id))
        recipients.sort(key=lambda r: not r[0])

        sends = [
            (user_id, self.WATCHLIST_PREFIX + message if is_watcher else message)
            for is_watcher, user_id in recipients
        ]
        sent = await self._send_all(sends)
        for _, user_id in recipients:
            self.limiter.record(user_id, now, kind)
        return sent

    async def flush_digests(self) -> int:
        """Send summaries of alerts held back by the hourly cap"""
        due = self.limiter.due_digests(datetime.utcnow())
        sends = [
            (user_id, BotMessages.format_digest(headlines, self.limiter.digest_max_lines))
            for user_id, headlines in due
            if headlines and user_id not in self._banned
        ]
        return await self._send_all(sends)

    async def _send_all(self, sends: List[Tuple[int, str]]) -> int:
        """Send (user_id, text) pairs in rate-limited parallel batches"""
        blocked: Set[int] = set()
        sent = 0
        loop = asyncio.get_running_loop()

        for i in range(0, len(sends), self.BATCH_SIZE):
            batch = sends[i:i + self.BATCH_SIZE]
            started = loop.time()

            results = await asyncio.gather(*(
                safe_send(self.bot, user_id, text) for user_id, text in batch
            ))
            for (user_id, _), result in zip(batch, results):
                if result == SendResult.OK:
                    sent += 1
                elif result == SendResult.BLOCKED:
                    blocked.add(user_id)

            # Pace batches to stay under Telegram's rate limit
            if i + self.BATCH_SIZE < len(sends):
                elapsed = loop.time() - started
                if elapsed < self.BATCH_INTERVAL:
                    await asyncio.sleep(self.BATCH_INTERVAL - elapsed)

        # Stop alerting users who blocked the bot or deleted their chat
        if blocked:
            for user_id in blocked:
                await self.db.update_user_alerts(user_id, False)
                self.limiter.forget(user_id)
            self._users = [u for u in self._users if u.get('id') not in blocked]
            print(f"🔕 Disabled alerts for {len(blocked)} unreachable user(s)")

        return sent
