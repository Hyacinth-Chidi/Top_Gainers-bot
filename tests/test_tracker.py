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
    tracker.broadcaster.SEND_DELAY = 0
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
            "change_24h": 40.0, "volume_24h": 1_000_000, "url": ""}

    asyncio.run(tracker._process_coin(coin))
    assert db.saved_alerts == [("XUSDT", "binance", "daily_spikes")]

    # Pretend 2 hours passed: the old code would alert again here
    key = ("XUSDT:binance", "daily_spikes")
    tracker.alerted_spikes[key] -= timedelta(hours=2)
    tracker.last_alert_for_coin["XUSDT:binance"] -= timedelta(hours=2)
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
