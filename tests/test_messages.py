import re

from bot.messages import BotMessages as M


def balanced(text):
    """Telegram legacy Markdown: bold/italic/code markers must pair up"""
    t = re.sub(r"\[[^\]]*\]\([^)]*\)", "", text)   # links
    t = re.sub(r"`[^`]*`", "", t)                    # code
    t = re.sub(r"\\[_*`\[]", "", t)                  # escaped characters
    return t.count("*") % 2 == 0 and t.count("_") % 2 == 0 and "`" not in t


URL = "https://example.com/x"

ALERTS = {
    "pump": M.format_pump_alert("PEPEUSDT", "binance", 0.0000123, 6.12, 5e6, URL, change_24h=18.4),
    "dump": M.format_dump_alert("PEPEUSDT", "mexc", 1.5, -7.3, 5e6, URL),
    "daily": M.format_spike_alert("PEPEUSDT", "gateio", 1.5, 42.0, 5e6, URL),
    "daily_dump": M.format_daily_dump_alert("PEPEUSDT", "bybit", 1.5, -40.0, 5e6, URL),
    "early": M.format_early_pump_alert("PEPEUSDT", "bitget", 1.5, 12.0, 5e6, 72, "HIGH", URL),
}


def test_alert_first_line_has_coin_and_move():
    # The first line is all a phone notification shows
    assert ALERTS["pump"].splitlines()[0] == "🚀 *PEPEUSDT* +6.12% in 5 min"
    assert ALERTS["dump"].splitlines()[0] == "💥 *PEPEUSDT* −7.30% in 5 min"
    assert "PEPEUSDT" in ALERTS["daily"].splitlines()[0]
    assert "+42.00%" in ALERTS["daily"].splitlines()[0]
    assert "PEPEUSDT" in ALERTS["early"].splitlines()[0]


def test_alerts_show_exchange_price_and_link():
    assert "Pump on Binance" in ALERTS["pump"]
    assert "$0.00001230" in ALERTS["pump"]
    assert "24h +18.40%" in ALERTS["pump"]
    assert "[Open on Gate.io](https://example.com/x)" in ALERTS["daily"]
    assert "72/100" in ALERTS["early"]


def test_every_template_has_balanced_markdown():
    texts = list(ALERTS.values()) + [
        M.welcome("Ada"), M.welcome("Ada", returning=True), M.welcome(None),
        M.HELP, M.UNKNOWN, M.ALERTS_ENABLED, M.ALERTS_DISABLED,
        M.alert_status(True), M.alert_status(False), M.ALERT_TYPES_PROMPT,
        M.FILTER_EXCHANGES_PROMPT, M.WATCHLIST_HELP, M.WATCHLIST_ADD_PROMPT,
        M.format_watchlist([]), M.format_watchlist(["BTCUSDT", "ETHUSDT"]),
        M.watchlist_added("BTCUSDT", True), M.watchlist_added("BTCUSDT", False),
        M.format_gainers_list([], "all", 10),
        M.format_gainers_list([{"symbol": "BTCUSDT", "exchange": "binance", "price": 65000,
                                "change_24h": 3.2, "volume_24h": 2e9, "url": URL}], "all", 10),
    ]
    for text in texts:
        assert balanced(text), text


def test_welcome_escapes_user_names():
    # Names are user-controlled; an underscore must not break formatting
    text = M.welcome("cool_trader*")
    assert "cool\\_trader\\*" in text
    assert balanced(text)


def test_welcome_mentions_how_to_start():
    assert "Turn alerts on" in M.welcome("Ada")
    assert M.welcome("Ada", returning=True).startswith("👋 Welcome back, Ada!")
