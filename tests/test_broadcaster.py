import asyncio
from telegram.error import Forbidden

from monitoring.broadcaster import AlertBroadcaster
from tests.fakes import FakeBot, FakeDB, user


def run(coro):
    return asyncio.run(coro)


def make(users, **kwargs):
    bot = FakeBot(kwargs.pop("fail_for", None))
    db = FakeDB(users=users, **kwargs)
    b = AlertBroadcaster(bot, db)
    b.SEND_DELAY = 0
    run(b.refresh())
    return b, bot, db


def recipients(bot):
    return [chat_id for chat_id, _, _ in bot.sent]


def test_respects_alert_type_preference():
    b, bot, _ = make([user(1), user(2, alert_types={"dumps": False})])
    run(b.broadcast("msg", "dumps", exchange="binance", symbol="BTCUSDT"))
    assert recipients(bot) == [1]


def test_daily_dumps_off_by_default():
    b, bot, _ = make([user(1)])
    run(b.broadcast("msg", "daily_dumps", exchange="binance"))
    assert recipients(bot) == []


def test_skips_banned_users():
    b, bot, _ = make([user(1), user(2)], banned=[2])
    run(b.broadcast("msg", "dumps", exchange="binance"))
    assert recipients(bot) == [1]


def test_exchange_filter_and_watchlist_override():
    users = [user(1, exchanges=["bybit"]), user(2, exchanges=["bybit"])]
    b, bot, _ = make(users, watchlists={"BTCUSDT": {2}})
    run(b.broadcast("msg", "confirmed_pumps", exchange="binance", symbol="BTCUSDT"))
    # User 1 filtered out Binance; user 2 watches BTC so still gets it, tagged
    assert recipients(bot) == [2]
    assert bot.sent[0][1].startswith(AlertBroadcaster.WATCHLIST_PREFIX)


def test_blocked_users_get_alerts_disabled():
    b, bot, db = make([user(1), user(2)], fail_for={2: Forbidden("blocked")})
    sent = run(b.broadcast("msg", "dumps", exchange="binance"))
    assert sent == 1
    assert db.alerts_disabled == [2]
    # Not retried on the next alert
    run(b.broadcast("msg", "dumps", exchange="binance"))
    assert recipients(bot) == [1, 1]
