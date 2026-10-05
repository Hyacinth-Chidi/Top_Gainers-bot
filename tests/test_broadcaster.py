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
    b.BATCH_INTERVAL = 0
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


def test_watchers_are_sent_first():
    b, bot, _ = make([user(1), user(2), user(3)], watchlists={"BTCUSDT": {3}})
    run(b.broadcast("msg", "dumps", exchange="binance", symbol="BTCUSDT"))
    assert recipients(bot)[0] == 3


def test_sends_in_parallel_batches():
    class SlowBot(FakeBot):
        async def send_message(self, chat_id, text, **kwargs):
            await asyncio.sleep(0.2)
            await super().send_message(chat_id, text, **kwargs)

    db = FakeDB(users=[user(i) for i in range(50)])
    b = AlertBroadcaster(SlowBot(), db)
    b.BATCH_INTERVAL = 0
    run(b.refresh())

    import time
    start = time.monotonic()
    sent = run(b.broadcast("msg", "dumps", exchange="binance"))
    elapsed = time.monotonic() - start
    assert sent == 50
    # Sequential sending would take 50 * 0.2s = 10s; two batches take ~0.4s
    assert elapsed < 2
