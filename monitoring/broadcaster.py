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

    SEND_DELAY = 0.05  # Stay well below Telegram's ~30 msg/s global limit
    WATCHLIST_PREFIX = "⭐ *On your watchlist*\n\n"

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
        blocked: Set[int] = set()
        sent = 0

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

            text = self.WATCHLIST_PREFIX + message if is_watcher else message
            result = await safe_send(self.bot, user_id, text)
            if result == SendResult.OK:
                sent += 1
            elif result == SendResult.BLOCKED:
                blocked.add(user_id)

            await asyncio.sleep(self.SEND_DELAY)

        # Stop alerting users who blocked the bot or deleted their chat
        if blocked:
            for user_id in blocked:
                await self.db.update_user_alerts(user_id, False)
            self._users = [u for u in self._users if u.get('id') not in blocked]
            print(f"🔕 Disabled alerts for {len(blocked)} unreachable user(s)")

        return sent
