import asyncio
from datetime import datetime

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")

import database.client as dbc

COLLECTIONS = ["users", "user_preferences", "price_snapshots", "alert_history",
               "watchlists", "banned_users", "counters"]


def make_db():
    db = dbc.DatabaseClient()
    db.client = mongomock_motor.AsyncMongoMockClient()
    db.db = db.client["test"]
    for name in COLLECTIONS:
        setattr(db, name, db.db[name])
    return db


def test_alert_history_expires_and_total_is_kept():
    async def scenario():
        db = make_db()
        # Alerts stored before this change existed
        await db.alert_history.insert_many(
            [{"symbol": "A", "exchange": "x", "alerted_at": datetime.utcnow()} for _ in range(3)]
        )
        await db._create_indexes()

        ttl = (await db.alert_history.index_information())["alerted_at_ttl"]
        await db.save_alert("BTCUSDT", "binance", 6.0, alert_type="confirmed_pumps")
        await db._create_indexes()  # restart must not reset the counter

        return (
            ttl["expireAfterSeconds"],
            await db.has_recent_alert("BTCUSDT", "binance", hours=1, alert_type="confirmed_pumps"),
            await db.has_recent_alert("BTCUSDT", "binance", hours=1, alert_type="dumps"),
            (await db.get_bot_stats())["alerts_sent_total"],
        )

    ttl, pump, dump, total = asyncio.run(scenario())
    assert ttl == int(dbc.config.ALERT_HISTORY_DAYS * 86400)
    assert pump and not dump
    assert total == 4
