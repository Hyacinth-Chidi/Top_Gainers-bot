import asyncio
from typing import Dict, List, Optional, Set
from telegram import Bot

from database.client import DatabaseClient, DEFAULT_ALERT_TYPES, normalize_symbol
from bot.utils import safe_send, SendResult


class AlertBroadcaster:
    """
    Delivers alerts to subscribed users.

    Recipients, bans and watchlists are loaded once per monitoring cycle
    (via refresh) instead of querying the database for every user on
    every alert.
    """

    # Telegram allows ~30 messages/second overall. Send in parallel batches
    # of this size, at most one batch per second, so alerts reach everyone fast.
    BATCH_SIZE = 25
    BATCH_INTERVAL = 1.0
    # Star goes on the first line so it shows in the phone notification
    WATCHLIST_PREFIX = "⭐ "

    def __init__(self, bot: Bot, db: DatabaseClient):
        self.bot = bot
        self.db = db
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

    async def broadcast(
        self,
        message: str,
        alert_type: str,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> int:
        """
        Send an alert to every eligible user. Returns the number delivered.

        Users who have the symbol on their watchlist get the alert tagged
        as a watchlist hit, even if they filtered out that exchange.
        """
        watchers = self._watchers.get(normalize_symbol(symbol), set()) if symbol else set()

        # Work out who gets the alert (watchlist users first - it's their coin)
        recipients = []
        for user in self._users:
            user_id = user.get('id')
            if user_id is None or user_id in self._banned:
                continue

            prefs = user.get('prefs') or {}
            alert_types = {**DEFAULT_ALERT_TYPES, **prefs.get('alert_types', {})}
            if not alert_types.get(alert_type, False):
                continue

            is_watcher = user_id in watchers
            if exchange and not is_watcher:
                allowed = prefs.get('alert_exchanges')
                if allowed is not None and exchange.lower() not in [e.lower() for e in allowed]:
                    continue

            recipients.append((not is_watcher, user_id))
        recipients.sort(key=lambda r: r[0])

        blocked: Set[int] = set()
        sent = 0
        loop = asyncio.get_running_loop()

        for i in range(0, len(recipients), self.BATCH_SIZE):
            batch = recipients[i:i + self.BATCH_SIZE]
            started = loop.time()

            results = await asyncio.gather(*(
                safe_send(self.bot, user_id,
                          message if not_watcher else self.WATCHLIST_PREFIX + message)
                for not_watcher, user_id in batch
            ))
            for (_, user_id), result in zip(batch, results):
                if result == SendResult.OK:
                    sent += 1
                elif result == SendResult.BLOCKED:
                    blocked.add(user_id)

            # Pace batches to stay under Telegram's rate limit
            if i + self.BATCH_SIZE < len(recipients):
                elapsed = loop.time() - started
                if elapsed < self.BATCH_INTERVAL:
                    await asyncio.sleep(self.BATCH_INTERVAL - elapsed)

        # Stop alerting users who blocked the bot or deleted their chat
        if blocked:
            for user_id in blocked:
                await self.db.update_user_alerts(user_id, False)
            self._users = [u for u in self._users if u.get('id') not in blocked]
            print(f"🔕 Disabled alerts for {len(blocked)} unreachable user(s)")

        return sent
