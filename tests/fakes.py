"""In-memory stand-ins for the database and Telegram bot"""
from database.client import DEFAULT_ALERT_TYPES


class FakeBot:
    def __init__(self, fail_for=None):
        self.sent = []
        self.fail_for = fail_for or {}

    async def send_message(self, chat_id, text, **kwargs):
        if chat_id in self.fail_for:
            raise self.fail_for[chat_id]
        self.sent.append((chat_id, text, kwargs))


class FakeDB:
    def __init__(self, users=None, banned=None, watchlists=None):
        self.users = users or []
        self.banned = set(banned or [])
        self.watchlists = watchlists or {}
        self.saved_alerts = []
        self.alerts_disabled = []

    async def get_users_with_alerts_enabled(self):
        return self.users

    async def get_banned_user_ids(self):
        return set(self.banned)

    async def get_watchlists_by_symbol(self):
        return self.watchlists

    async def update_user_alerts(self, user_id, enabled):
        self.alerts_disabled.append(user_id)

    async def has_recent_alert(self, *args, **kwargs):
        return False

    async def save_alert(self, symbol, exchange, change, alert_type=None):
        self.saved_alerts.append((symbol, exchange, alert_type))


def user(user_id, alert_types=None, exchanges=None):
    prefs = {"alert_types": {**DEFAULT_ALERT_TYPES, **(alert_types or {})}}
    if exchanges is not None:
        prefs["alert_exchanges"] = exchanges
    return {"id": user_id, "alerts_enabled": True, "prefs": prefs}
