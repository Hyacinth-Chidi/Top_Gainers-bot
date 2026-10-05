import asyncio
from types import SimpleNamespace

from bot.handlers import BotHandlers


class FakeQuery:
    def __init__(self, data, user_id=1):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = 0
        self.edits = []
        self.message = SimpleNamespace(reply_text=self._reply)
        self.replies = []

    async def answer(self, *args, **kwargs):
        self.answers += 1

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))

    async def edit_message_reply_markup(self, **kwargs):
        self.edits.append((None, kwargs))

    async def _reply(self, text, **kwargs):
        self.replies.append(text)


class FakeExchangeClient:
    async def get_top_losers(self, exchange, limit=10):
        return [{"symbol": "XUSDT", "exchange": exchange, "price": 1.0,
                 "change_24h": -12.0, "volume_24h": 5e6, "url": ""}]

    get_top_gainers = get_top_losers


class HandlerDB:
    async def is_banned(self, user_id):
        return False

    async def get_user_preferences(self, user_id):
        return None

    async def update_user_alert_exchanges(self, user_id, exchanges):
        self.saved = exchanges


def press(handlers, data):
    query = FakeQuery(data)
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))
    asyncio.run(handlers.button_callback(update, None))
    return query


def test_count_selection_answers_once_and_shows_results():
    handlers = BotHandlers(FakeExchangeClient(), HandlerDB())
    handlers.user_context[1] = {"mode": "losers", "exchange": "binance"}
    query = press(handlers, "count:5")
    assert query.answers == 1
    text, kwargs = query.edits[-1]
    assert "Top 5 Losers* · Binance" in text
    # "View again" button follows the current mode
    button = kwargs["reply_markup"].inline_keyboard[1][0]
    assert button.callback_data == "menu:losers"


def test_exchange_filter_toggle_without_preferences():
    db = HandlerDB()
    handlers = BotHandlers(FakeExchangeClient(), db)
    query = press(handlers, "toggle_exch:mexc")
    assert query.answers == 1
    assert db.saved == ["binance", "bybit", "bitget", "gateio"]


def test_unknown_callback_is_still_answered():
    handlers = BotHandlers(FakeExchangeClient(), HandlerDB())
    assert press(handlers, "bogus:1").answers == 1
