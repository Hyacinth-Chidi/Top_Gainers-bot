from bot.utils import escape_md, md_bold, format_price, format_volume
from database.client import normalize_symbol


def test_escape_md_escapes_special_characters():
    assert escape_md("A_B*C`D[E") == "A\\_B\\*C\\`D\\[E"


def test_md_bold_plain_and_special():
    assert md_bold("BTCUSDT") == "*BTCUSDT*"
    # Can't escape inside an entity, so special text is escaped and not bolded
    assert md_bold("PEPE_2") == "PEPE\\_2"


def test_format_price_keeps_precision_for_tiny_prices():
    assert format_price(0.00001234) == "$0.00001234"
    assert format_price(0.5) == "$0.50000"
    assert format_price(42.5) == "$42.5000"
    assert format_price(65000) == "$65,000.00"
    assert format_price(None) == "$0"


def test_format_volume():
    assert format_volume(2_500_000_000) == "$2.50B"
    assert format_volume(3_200_000) == "$3.20M"
    assert format_volume(5_000) == "$5.00K"


def test_normalize_symbol():
    for raw in ("btc", "BTCUSDT", "btc/usdt", "BTC-USDT", "BTC_USDT"):
        assert normalize_symbol(raw) == "BTCUSDT"
