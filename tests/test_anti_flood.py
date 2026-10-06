"""Rules that keep alerts meaningful instead of flooding users"""
import asyncio
from datetime import datetime, timedelta

from bot.messages import BotMessages
from monitoring.broadcaster import AlertBroadcaster
from monitoring.limiter import AlertLimiter, FAST, SLOW
from monitoring.tracker import SpikeTracker
import monitoring.tracker as tracker_mod
from tests.fakes import FakeBot, FakeDB, user
from tests.test_messages import balanced

LIQUID = 10_000_000
THIN = 200_000


def ticker(symbol, exchange, price, volume=LIQUID, change_24h=2.0):
    return {"symbol": symbol, "exchange": exchange, "price": price,
            "change_24h": change_24h, "volume_24h": volume,
            "url": f"https://{exchange}.example/{symbol}"}


class Feed:
    def __init__(self):
        self.by_exchange = {}

    async def get_all_tickers(self, exchange):
        return self.by_exchange.get(exchange, [])

    def _generate_trade_link(self, exchange, symbol):
        return f"https://{exchange}.example/{symbol}"


def scan(feed, users, watchlists=None, exchanges=("binance",), history=None):
    """
    Run one scan. `history` maps "SYMBOL:exchange" -> price 6 minutes ago,
    so 5-minute moves can be measured.
    """
    db = FakeDB(users=users, watchlists=watchlists or {})
    bot = FakeBot()
    tracker = SpikeTracker(feed, bot, db)
    tracker.broadcaster.BATCH_INTERVAL = 0
    tracker.ws_client.supports = lambda e: False
    for key, price in (history or {}).items():
        tracker.price_history[key] = [(price, datetime.utcnow() - timedelta(minutes=6))]

    original = tracker_mod.config.EXCHANGES
    tracker_mod.config.EXCHANGES = list(exchanges)
    try:
        asyncio.run(tracker._check_all_exchanges())
    finally:
        tracker_mod.config.EXCHANGES = original
    return bot, db


def headlines(bot):
    return [(chat_id, text.splitlines()[0]) for chat_id, text, _ in bot.sent]


# ---------- liquidity ----------

def test_thin_coins_do_not_alert():
    feed = Feed()
    feed.by_exchange["binance"] = [ticker("THINUSDT", "binance", 1.10, volume=THIN)]
    bot, db = scan(feed, [user(1)], history={"THINUSDT:binance": 1.0})
    assert bot.sent == []
    assert db.saved_alerts == []


def test_thin_coin_on_watchlist_reaches_only_its_watchers():
    feed = Feed()
    feed.by_exchange["binance"] = [ticker("THINUSDT", "binance", 1.10, volume=THIN)]
    bot, _ = scan(feed, [user(1), user(2)], watchlists={"THINUSDT": {2}},
                  history={"THINUSDT:binance": 1.0})
    assert [chat for chat, _ in headlines(bot)] == [2]
    assert headlines(bot)[0][1].startswith("⭐ 🚀")


# ---------- one alert per coin across exchanges ----------

def test_same_move_on_several_exchanges_is_one_alert():
    feed = Feed()
    exchanges = ("binance", "bybit", "mexc")
    for i, ex in enumerate(exchanges):
        feed.by_exchange[ex] = [ticker("PEPEUSDT", ex, 1.08, volume=LIQUID * (3 - i))]
    history = {f"PEPEUSDT:{ex}": 1.0 for ex in exchanges}
    bot, db = scan(feed, [user(1)], exchanges=exchanges, history=history)

    pumps = [h for _, h in headlines(bot) if h.startswith("🚀")]
    assert pumps == ["🚀 *PEPEUSDT* +8.00% in 5 min"]
    text = bot.sent[0][1]
    assert "Pump on Binance, Bybit and MEXC" in text
    assert "[Bybit](https://bybit.example/PEPEUSDT)" in text
    assert len([a for a in db.saved_alerts if a[2] == "confirmed_pumps"]) == 1


def test_multi_exchange_alert_respects_exchange_filter():
    feed = Feed()
    for ex in ("binance", "bybit"):
        feed.by_exchange[ex] = [ticker("PEPEUSDT", ex, 1.08)]
    history = {f"PEPEUSDT:{ex}": 1.0 for ex in ("binance", "bybit")}
    users = [user(1, exchanges=["bybit"]), user(2, exchanges=["gateio"])]
    bot, _ = scan(feed, users, exchanges=("binance", "bybit"), history=history)
    assert {chat for chat, _ in headlines(bot)} == {1}


# ---------- market-wide moves ----------

def market(n=40, move=0.03, outlier=None):
    """n liquid coins all moving `move`; optionally one coin moving `outlier`"""
    feed, history = Feed(), {}
    rows = []
    for i in range(n):
        sym = f"C{i:02d}USDT"
        m = outlier if (outlier is not None and i == 0) else move
        rows.append(ticker(sym, "binance", 1 + m))
        history[f"{sym}:binance"] = 1.0
    feed.by_exchange["binance"] = rows
    return feed, history


def test_market_wide_move_is_one_summary():
    feed, history = market(move=0.03)
    bot, db = scan(feed, [user(1)], history=history)
    heads = [h for _, h in headlines(bot)]
    assert len(heads) == 1
    assert heads[0].startswith("🟢 Market-wide pump: most coins +3.00% in 5 min")
    assert not [a for a in db.saved_alerts if a[2] == "confirmed_pumps"]
    assert balanced(bot.sent[0][1])


def test_coin_beating_the_market_still_alerts():
    feed, history = market(move=0.03, outlier=0.10)  # C00 +10% vs market +3%
    bot, _ = scan(feed, [user(1)], history=history)
    heads = [h for _, h in headlines(bot)]
    assert any(h.startswith("🟢 Market-wide pump") for h in heads)
    assert "🚀 *C00USDT* +10.00% in 5 min" in heads
    text = next(t for _, t, _ in bot.sent if t.startswith("🚀"))
    assert "Market +3.00% in 5 min · this coin +7.00% vs market" in text


def test_market_summary_can_be_switched_off():
    feed, history = market(move=0.03)
    bot, _ = scan(feed, [user(1, alert_types={"market_moves": False})], history=history)
    assert bot.sent == []


# ---------- hourly caps and summaries ----------

def make_broadcaster(users, limiter, watchlists=None):
    db = FakeDB(users=users, watchlists=watchlists or {})
    bot = FakeBot()
    b = AlertBroadcaster(bot, db, limiter=limiter)
    b.BATCH_INTERVAL = 0
    asyncio.run(b.refresh())
    return b, bot


def test_hourly_cap_then_one_summary():
    limiter = AlertLimiter(caps={FAST: 3, SLOW: 1}, digest_delay=timedelta(0))
    b, bot = make_broadcaster([user(1)], limiter)
    for i in range(5):
        asyncio.run(b.broadcast(f"🚀 *C{i}USDT* +6.00% in 5 min\nbody", "confirmed_pumps"))
    assert len(bot.sent) == 3

    asyncio.run(b.flush_digests())
    digest = bot.sent[-1][1]
    assert len(bot.sent) == 4
    assert digest.startswith("🗂 *2 more alerts in the last few minutes*")
    assert "• 🚀 *C3USDT* +6.00% in 5 min" in digest
    assert balanced(digest)


def test_daily_alerts_have_their_own_smaller_allowance():
    limiter = AlertLimiter(caps={FAST: 10, SLOW: 2})
    b, bot = make_broadcaster([user(1)], limiter)
    for i in range(4):
        asyncio.run(b.broadcast(f"🔥 *D{i}USDT* is up +40% today", "daily_spikes"))
    # Daily alerts used up their allowance, but a pump still goes straight through
    asyncio.run(b.broadcast("🚀 *PUMPUSDT* +7% in 5 min", "confirmed_pumps"))
    heads = [t.splitlines()[0] for _, t, _ in bot.sent]
    assert heads == ["🔥 *D0USDT* is up +40% today", "🔥 *D1USDT* is up +40% today",
                     "🚀 *PUMPUSDT* +7% in 5 min"]


def test_watchlist_and_priority_alerts_skip_the_cap():
    limiter = AlertLimiter(caps={FAST: 1, SLOW: 1})
    b, bot = make_broadcaster([user(1)], limiter, watchlists={"BTCUSDT": {1}})
    asyncio.run(b.broadcast("🚀 *AUSDT* +6%", "confirmed_pumps"))
    asyncio.run(b.broadcast("🚀 *BUSDT* +6%", "confirmed_pumps"))                     # capped
    asyncio.run(b.broadcast("🚀 *BTCUSDT* +6%", "confirmed_pumps", symbol="BTCUSDT"))  # watchlist
    asyncio.run(b.broadcast("🟢 Market-wide pump", "market_moves", priority=True))    # priority
    heads = [t.splitlines()[0] for _, t, _ in bot.sent]
    assert heads == ["🚀 *AUSDT* +6%", "⭐ 🚀 *BTCUSDT* +6%", "🟢 Market-wide pump"]


def test_digest_waits_before_sending():
    limiter = AlertLimiter(caps={FAST: 1, SLOW: 1}, digest_delay=timedelta(minutes=15))
    now = datetime(2026, 1, 1, 12, 0)
    limiter.defer(1, "headline", now)
    assert limiter.due_digests(now + timedelta(minutes=5)) == []
    assert limiter.due_digests(now + timedelta(minutes=15)) == [(1, ["headline"])]
    assert limiter.due_digests(now + timedelta(minutes=30)) == []


def test_digest_truncates_long_lists():
    text = BotMessages.format_digest([f"🚀 *C{i}USDT* +6%" for i in range(20)], max_lines=15)
    assert "• ...and 5 more" in text
    assert balanced(text)


def test_limiter_forgets_sends_older_than_an_hour():
    limiter = AlertLimiter(caps={FAST: 2, SLOW: 1})
    t0 = datetime(2026, 1, 1, 12, 0)
    for _ in range(50):  # e.g. watchlist alerts, which skip the cap check
        limiter.record(1, t0)
    limiter.record(1, t0 + timedelta(hours=2))
    assert len(limiter._sent[(1, FAST)]) == 1
    assert limiter.allow(1, t0 + timedelta(hours=2))
