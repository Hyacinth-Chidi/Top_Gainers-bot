from datetime import datetime
from typing import List, Dict, Optional

from config import config
from .utils import md_bold, escape_md, format_price, format_volume

# Telegram's legacy Markdown uses *bold* and _italic_ (single characters).
#
# Alerts put the coin and the move on the FIRST line: that is the only line
# shown in a phone notification, so people can decide at a glance.

_MIN = int(config.MIN_SPIKE_THRESHOLD)
_MAX = int(config.MAX_SPIKE_THRESHOLD)
_DEX_ON = bool(config.DEX_ENABLED and config.BIRDEYE_API_KEY)

EXCHANGE_NAMES = {
    "binance": "Binance",
    "bybit": "Bybit",
    "mexc": "MEXC",
    "bitget": "Bitget",
    "gateio": "Gate.io",
    "all": "All exchanges",
}

DISCLAIMER = "_Not financial advice. Always do your own research._"


def exchange_name(exchange: str) -> str:
    return EXCHANGE_NAMES.get(exchange.lower(), exchange.upper())


def _pct(value: float) -> str:
    """+6.12% / −3.40% (proper minus sign)"""
    return f"+{value:.2f}%" if value >= 0 else f"−{abs(value):.2f}%"


class BotMessages:
    """Message templates for the bot"""

    # ==================== ONBOARDING ====================

    @staticmethod
    def welcome(first_name: Optional[str], returning: bool = False) -> str:
        name = escape_md(first_name) if first_name else "there"
        if returning:
            return (
                f"👋 Welcome back, {name}!\n\n"
                "What would you like to check?"
            )
        dex_line = "🌐 Spot whale buys on Solana DEXs\n" if _DEX_ON else ""
        return (
            f"👋 Hi {name}, welcome to *Top Gainers Bot*!\n\n"
            "I watch crypto futures on Binance, Bybit, MEXC, Bitget and Gate.io "
            "around the clock and message you the moment something moves.\n\n"
            "*What I can do*\n"
            "📈 Show today's top gainers and losers\n"
            "🚀 Alert you to pumps and dumps within a minute\n"
            f"{dex_line}"
            "⭐ Keep an eye on your favourite coins\n\n"
            "*Get started*\n"
            "1. Tap 🔔 *Alerts* below\n"
            "2. Turn alerts on\n\n"
            "Alerts stay off until you switch them on."
        )

    HELP = (
        "📖 *How to use Top Gainers Bot*\n\n"
        "*Market lists*\n"
        "/gainers - today's biggest risers\n"
        "/losers - today's biggest fallers\n\n"
        "*Alerts*\n"
        "/alerts - turn alerts on or off and choose what you get\n"
        "🔮 Early pump - signs a pump may be starting\n"
        "🚀 Pump / 💥 Dump - a move of 5% or more within 5 minutes\n"
        f"🔥 Daily gainer / 📉 Daily loser - {_MIN}% to {_MAX}% up or down today\n"
        + ("🌐 DEX - big and whale buys on Solana\n" if _DEX_ON else "")
        + "\n*Watchlist*\n"
        "/watchlist - see your coins\n"
        "`/watchlist add BTC` - add a coin\n"
        "`/watchlist remove BTC` - remove a coin\n"
        "⭐ Alerts for your coins are starred and reach you from every exchange.\n\n"
        "Every alert has a link that opens the coin on the exchange.\n\n"
        f"{DISCLAIMER}"
    )

    UNKNOWN = (
        "🤔 Sorry, I didn't catch that.\n\n"
        "Use the buttons below, or /help to see everything I can do."
    )

    # ==================== MARKET LISTS ====================

    SELECT_EXCHANGE = "🏦 *Which exchange?*"
    SELECT_COUNT = "🔢 *How many coins?*"
    LOADING = "⏳ Fetching the latest prices..."

    @staticmethod
    def format_gainers_list(gainers: List[Dict], exchange: str, count: int, title: str = "Gainers") -> str:
        """Format a list of coins: two compact lines per coin"""
        where = exchange_name(exchange)
        if not gainers:
            return (
                f"😕 I couldn't load {title.lower()} from {where} right now.\n\n"
                "The exchange may be busy. Please try again in a minute."
            )

        icon = "📈" if title == "Gainers" else "📉"
        updated = datetime.utcnow().strftime("%d %b, %H:%M UTC")
        lines = [f"{icon} *Top {count} {title}* · {where}", f"_{updated}_", ""]

        for i, coin in enumerate(gainers, 1):
            rank = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            exch = exchange_name(coin['exchange'])
            url = coin.get('url', '')
            venue = f"[{exch}]({url})" if url else exch

            lines.append(f"{rank} {md_bold(coin['symbol'])}  {_pct(coin['change_24h'])}")
            lines.append(
                f"      {format_price(coin['price'])} · Vol {format_volume(coin['volume_24h'])} · {venue}"
            )

        lines.append("")
        lines.append("Tap an exchange name to open the coin.")
        return "\n".join(lines)

    # ==================== ALERTS ====================

    @staticmethod
    def _alert(headline: str, subtitle: str, price: float, change_24h: Optional[float],
               volume: float, exchange: str, url: str, extra: str = "") -> str:
        """Common layout: headline, subtitle, key numbers, link, disclaimer"""
        stats = f"💰 {format_price(price)}"
        if change_24h is not None:
            stats += f"  ·  24h {_pct(change_24h)}"
        stats += f"  ·  Vol {format_volume(volume)}"

        message = f"{headline}\n_{subtitle}_\n\n{stats}\n"
        if extra:
            message += f"{extra}\n"
        if url:
            message += f"\n🔗 [Open on {exchange_name(exchange)}]({url})\n"
        message += f"\n{DISCLAIMER}"
        return message

    @staticmethod
    def format_pump_alert(symbol: str, exchange: str, price: float, change_5m: float,
                          volume: float, url: str = "", change_24h: Optional[float] = None) -> str:
        """5-minute pump"""
        return BotMessages._alert(
            f"🚀 {md_bold(symbol)} {_pct(change_5m)} in 5 min",
            f"Pump on {exchange_name(exchange)}",
            price, change_24h, volume, exchange, url,
        )

    @staticmethod
    def format_dump_alert(symbol: str, exchange: str, price: float, change_5m: float,
                          volume: float, url: str = "", change_24h: Optional[float] = None) -> str:
        """5-minute dump"""
        return BotMessages._alert(
            f"💥 {md_bold(symbol)} {_pct(change_5m)} in 5 min",
            f"Dump on {exchange_name(exchange)}",
            price, change_24h, volume, exchange, url,
        )

    @staticmethod
    def format_spike_alert(symbol: str, exchange: str, price: float, change: float,
                           volume: float, url: str = "") -> str:
        """Daily gainer"""
        return BotMessages._alert(
            f"🔥 {md_bold(symbol)} is up {_pct(change)} today",
            f"Daily gainer on {exchange_name(exchange)}",
            price, None, volume, exchange, url,
        )

    @staticmethod
    def format_daily_dump_alert(symbol: str, exchange: str, price: float, change_24h: float,
                                volume: float, url: str = "") -> str:
        """Daily loser"""
        return BotMessages._alert(
            f"📉 {md_bold(symbol)} is down {_pct(change_24h)} today",
            f"Daily loser on {exchange_name(exchange)}",
            price, None, volume, exchange, url,
        )

    @staticmethod
    def format_early_pump_alert(symbol: str, exchange: str, price: float, change_24h: float,
                                volume: float, pump_score: int, confidence: str, url: str = "") -> str:
        """Score-based early pump signal"""
        if confidence == "HIGH":
            headline = f"🚨 {md_bold(symbol)} looks ready to pump"
        else:
            headline = f"🔮 {md_bold(symbol)} may be starting to pump"
        return BotMessages._alert(
            headline,
            f"Early signal on {exchange_name(exchange)}",
            price, change_24h, volume, exchange, url,
            extra=f"📊 Signal strength: *{pump_score}/100* ({confidence.lower()})",
        )

    # ==================== ALERT SETTINGS ====================

    @staticmethod
    def alert_status(enabled: bool) -> str:
        if enabled:
            return (
                "🔔 *Alerts are ON* ✅\n\n"
                "You'll get a message the moment a coin moves on the exchanges you follow.\n\n"
                "Use the buttons below to choose alert types and exchanges, or switch alerts off."
            )
        return (
            "🔕 *Alerts are OFF*\n\n"
            "Turn them on to get a message the moment a coin pumps or dumps."
        )

    ALERTS_ENABLED = (
        "✅ *Alerts are on!*\n\n"
        "You'll hear from me as soon as something moves.\n\n"
        "Too many messages? Pick fewer alert types or exchanges below."
    )

    ALERTS_DISABLED = (
        "🔕 *Alerts are off.*\n\n"
        "You won't get alerts until you turn them back on, here or with /alerts."
    )

    ALERT_TYPES_PROMPT = (
        "🎚️ *Alert types*\n\n"
        "Tap to switch each one on ✅ or off ❌."
    )

    FILTER_EXCHANGES_PROMPT = (
        "🏦 *Exchanges*\n\n"
        "Tap to choose which exchanges you get alerts from.\n"
        "⭐ Alerts for your watchlist coins always come through."
    )

    # ==================== WATCHLIST ====================

    WATCHLIST_HELP = (
        "⭐ *Watchlist commands*\n\n"
        "`/watchlist` - see your coins\n"
        "`/watchlist add BTC` - add a coin\n"
        "`/watchlist remove BTC` - remove a coin\n"
        "`/watchlist clear` - remove all coins\n\n"
        "`BTC` and `BTCUSDT` both work."
    )

    WATCHLIST_ADD_PROMPT = (
        "➕ *Add a coin*\n\n"
        "Send the command with the coin's symbol, for example:\n"
        "`/watchlist add BTC`"
    )

    @staticmethod
    def format_watchlist(symbols: list) -> str:
        """Format user's watchlist for display"""
        if not symbols:
            return (
                "⭐ *Your watchlist is empty*\n\n"
                "Add coins you care about and their alerts will be starred "
                "and reach you from every exchange.\n\n"
                "Try: `/watchlist add BTC`"
            )

        noun = "coin" if len(symbols) == 1 else "coins"
        lines = [f"⭐ *Your watchlist* ({len(symbols)} {noun})", ""]
        lines += [f"• `{symbol}`" for symbol in symbols]
        lines += ["", "Remove one with `/watchlist remove BTC`"]
        return "\n".join(lines)

    @staticmethod
    def watchlist_added(symbol: str, alerts_enabled: bool) -> str:
        message = f"⭐ Added `{symbol}` to your watchlist."
        if alerts_enabled:
            message += "\n\nYou'll get a starred alert whenever it moves."
        else:
            message += "\n\nTurn on /alerts to get notified when it moves."
        return message
