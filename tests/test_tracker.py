import asyncio
from datetime import datetime, timedelta

from monitoring.tracker import SpikeTracker
from tests.fakes import FakeBot, FakeDB, user


class FakeExchangeClient:
    def _generate_trade_link(self, exchange, symbol):
        return f"https://example.com/{exchange}/{symbol}"


def make_tracker(users=None):
    db = FakeDB(users=users or [user(1)])
    bot = FakeBot()
    tracker = SpikeTracker(FakeExchangeClient(), bot, db)
    tracker.broadcaster.BATCH_INTERVAL = 0
    asyncio.run(tracker.broadcaster.refresh())
    return tracker, bot, db


def test_volume_ratio_flat_pace_is_about_one():
    tracker, _, _ = make_tracker()
    t0 = datetime(2026, 1, 1)
    # 24h volume unchanged over 5 minutes = trading at the average pace
    tracker.volume_history["X:binance"] = [(1_000_000, t0), (1_000_000, t0 + timedelta(minutes=5))]
    assert abs(tracker._get_volume_spike_ratio("X:binance") - 1.0) < 1e-9


def test_volume_ratio_detects_burst():
    tracker, _, _ = make_tracker()
    t0 = datetime(2026, 1, 1)
    vol = 8_640_000  # average pace: $100/s -> $30k per 5 minutes
    # $150k traded in 5 minutes (~5x pace): 24h figure rises by 150k - 30k
    tracker.volume_history["X:binance"] = [(vol, t0), (vol + 120_000, t0 + timedelta(minutes=5))]
    ratio = tracker._get_volume_spike_ratio("X:binance")
    assert 4.9 < ratio < 5.1
    assert tracker._get_volume_spike_score("X:binance") == int(tracker.SCORE_VOLUME_SPIKE * 0.7)


def test_volume_ratio_needs_enough_time():
    tracker, _, _ = make_tracker()
    t0 = datetime(2026, 1, 1)
    tracker.volume_history["X:binance"] = [(1, t0), (100, t0 + timedelta(seconds=5))]
    assert tracker._get_volume_spike_ratio("X:binance") == 0.0


def test_volatility_change_uses_price_from_window_ago():
    tracker, _, _ = make_tracker()
    now = datetime(2026, 1, 1, 12, 0)
    tracker.price_history["X:binance"] = [
        (100.0, now - timedelta(minutes=7)),
        (110.0, now - timedelta(minutes=5)),
        (120.0, now - timedelta(minutes=2)),
    ]
    assert abs(tracker._get_volatility_change("X:binance", 121.0, now) - 10.0) < 1e-9


def test_classify_priority():
    tracker, _, _ = make_tracker()
    assert tracker._classify_move(6, 40) == "confirmed_pumps"
    assert tracker._classify_move(-6, -40) == "dumps"
    assert tracker._classify_move(1, 40) == "daily_spikes"
    assert tracker._classify_move(1, -40) == "daily_dumps"
    assert tracker._classify_move(1, 10) is None


def test_daily_spike_not_repeated_hourly():
    tracker, bot, db = make_tracker()
    coin = {"symbol": "XUSDT", "exchange": "binance", "price": 1.0,
            "change_24h": 40.0, "volume_24h": 5_000_000, "url": ""}

    asyncio.run(tracker._process_coin(coin))
    assert db.saved_alerts == [("XUSDT", "binance", "daily_spikes")]

    # Pretend 2 hours passed: the old code would alert again here
    key = ("XUSDT", "daily_spikes")
    tracker.alerted_spikes[key] -= timedelta(hours=2)
    tracker.last_alert_for_coin["XUSDT"] -= timedelta(hours=2)
    asyncio.run(tracker._process_coin(coin))
    assert len(db.saved_alerts) == 1


def test_cleanup_drops_momentum_for_inactive_coins():
    tracker, _, _ = make_tracker()
    old = datetime.utcnow() - timedelta(hours=1)
    tracker.price_history["X:binance"] = [(1.0, old)]
    tracker.volume_history["X:binance"] = [(1.0, old)]
    tracker.momentum_history["X:binance"] = [1.0, 2.0]
    tracker.cleanup_old_history()
    assert tracker.price_history == {}
    assert tracker.momentum_history == {}


def _coin(price, change_24h=10.0):
    return {"symbol": "XUSDT", "exchange": "binance", "price": price,
            "change_24h": change_24h, "volume_24h": 5_000_000, "url": ""}


def _seed_price(tracker, price, minutes_ago=6):
    tracker.price_history["XUSDT:binance"] = [
        (price, datetime.utcnow() - timedelta(minutes=minutes_ago))
    ]


def test_pump_is_not_blocked_by_earlier_daily_alert():
    tracker, _, db = make_tracker()
    # Coin is a daily gainer -> daily alert goes out
    asyncio.run(tracker._process_coin(_coin(1.00, change_24h=40.0)))
    # Minutes later it rips +8% in 5m -> the pump alert must still go out
    _seed_price(tracker, 1.00)
    asyncio.run(tracker._process_coin(_coin(1.08, change_24h=48.0)))
    assert [a[2] for a in db.saved_alerts] == ["daily_spikes", "confirmed_pumps"]


def test_dump_right_after_pump_is_sent():
    tracker, _, db = make_tracker()
    _seed_price(tracker, 1.00)
    asyncio.run(tracker._process_coin(_coin(1.10)))
    _seed_price(tracker, 1.10)
    asyncio.run(tracker._process_coin(_coin(1.00)))
    assert [a[2] for a in db.saved_alerts] == ["confirmed_pumps", "dumps"]


def test_pump_realerts_when_it_keeps_running():
    tracker, _, db = make_tracker()
    _seed_price(tracker, 1.00)
    asyncio.run(tracker._process_coin(_coin(1.06)))
    # Still pumping but not much further than the last alert -> no repeat
    _seed_price(tracker, 1.03)
    asyncio.run(tracker._process_coin(_coin(1.09)))
    assert len(db.saved_alerts) == 1
    # +5% beyond the last alerted price -> alert again despite the cooldown
    _seed_price(tracker, 1.05)
    asyncio.run(tracker._process_coin(_coin(1.12)))
    assert [a[2] for a in db.saved_alerts] == ["confirmed_pumps", "confirmed_pumps"]


def test_daily_alert_held_back_after_recent_pump():
    tracker, _, db = make_tracker()
    _seed_price(tracker, 1.00)
    asyncio.run(tracker._process_coin(_coin(1.40, change_24h=40.0)))
    # Next scan: no 5m move any more, but daily band still hit -> skipped
    _seed_price(tracker, 1.40)
    asyncio.run(tracker._process_coin(_coin(1.40, change_24h=40.0)))
    assert [a[2] for a in db.saved_alerts] == ["confirmed_pumps"]


def test_scan_covers_coins_outside_daily_top_movers():
    """A coin flat on the day that suddenly pumps must still be alerted"""
    import monitoring.tracker as tracker_mod

    class Feed:
        price = 1.0
        async def get_all_tickers(self, exchange):
            # 200 coins with bigger daily moves crowd QUIET out of any top-N list
            coins = [{"symbol": f"BIG{i}USDT", "exchange": exchange, "price": 1.0,
                      "change_24h": 20.0 if i % 2 else -20.0, "volume_24h": 5e6, "url": ""}
                     for i in range(200)]
            coins.append({"symbol": "QUIETUSDT", "exchange": exchange, "price": self.price,
                          "change_24h": 1.0, "volume_24h": 5e6, "url": ""})
            return coins
        def _generate_trade_link(self, exchange, symbol):
            return ""

    feed = Feed()
    db = FakeDB(users=[user(1)])
    tracker = SpikeTracker(feed, FakeBot(), db)
    tracker.broadcaster.BATCH_INTERVAL = 0
    original = tracker_mod.config.EXCHANGES
    tracker_mod.config.EXCHANGES = ["binance"]
    try:
        tracker.price_history["QUIETUSDT:binance"] = [
            (1.0, datetime.utcnow() - timedelta(minutes=6))
        ]
        feed.price = 1.07
        asyncio.run(tracker._check_all_exchanges())
    finally:
        tracker_mod.config.EXCHANGES = original

    assert ("QUIETUSDT", "binance", "confirmed_pumps") in db.saved_alerts
