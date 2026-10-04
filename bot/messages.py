from typing import List, Dict

from config import config
from .utils import md_bold, format_price, format_volume

# Telegram's legacy Markdown uses *bold* and _italic_ (single characters)

_MIN = int(config.MIN_SPIKE_THRESHOLD)
_MAX = int(config.MAX_SPIKE_THRESHOLD)


class BotMessages:
    """Message templates for the bot"""

    WELCOME = """
👋 *Welcome to Top Gainers Bot!*

I track the crypto futures market to find the best trading opportunities for you. 🚀

🔔 *Important:* Alerts are *OFF* by default.
To start receiving real-time Pump & Dump alerts, click "🔔 Alerts" below and enable them!

🎯 *What I Do:*
• 📈 *Gainers*: Top 5/10/20 winners
• 📉 *Losers*: Top 5/10/20 dippers (buy the dip!)
• 📝 *Watchlist*: Track your favorite coins
• 🔮 *Early Pump Signals*: Multi-factor pump detection
• ⚡ *Pump Alerts*: Price pumps 5%+ in 5 mins
• 💥 *Dump Alerts*: Price drops 5%+ in 5 mins
• 🛡️ *Exchange Filter*: You choose which exchanges to track

📊 *Exchanges Supported:*
🟡 Binance • 🔷 Bybit • 🟢 MEXC • 🔵 Bitget • 🟣 Gate.io

👇 *Click a button below to start:*
"""

    HELP = f"""
🆘 *Top Gainers Bot Help*

I help you catch pumps, dumps, and trade volatility on major futures exchanges.

✨ *Main Commands:*
• /gainers - View top rising coins 📈
• /losers - View top falling coins 📉
• /watchlist - Manage your watchlist 📝
• /alerts - Configure your notifications 🔔

📝 *Watchlist Commands:*
• `/watchlist` - View your list
• `/watchlist add BTC` - Add a coin
• `/watchlist remove BTC` - Remove a coin
• `/watchlist clear` - Clear all

⚡ *About Alerts:*
I watch the market 24/7 and notify you when:
1. *Early Pump Signal*: Volume, momentum & order book point to a pump 🔮
2. *Pump Alert*: A coin pumps >5% in 5 minutes 🚀
3. *Dump Alert*: A coin drops >5% in 5 minutes 💥
4. *Daily Gainer*: A coin hits +{_MIN}% to +{_MAX}% on the day 🔥
5. *Daily Loser*: A coin drops -{_MIN}% to -{_MAX}% on the day 📉
6. *DEX Alerts*: Big buys and demand spikes on Solana 🌐

⭐ Coins on your watchlist are flagged in alerts and always reach you, even from exchanges you filtered out.

🛠️ *Settings:*
Use /alerts → "Alert Types" and "Filter Exchanges" to tune what you receive.

💡 *Pro Tip:*
All alerts contain *Direct Trading Links*. Click the link to open the futures pair immediately!

_Questions? Feedback? Contact the developer._
"""

    @staticmethod
    def format_gainers_list(gainers: List[Dict], exchange: str, count: int, title: str = "Gainers") -> str:
        """Format list of coins into readable message"""
        if not gainers:
            where = "any exchange" if exchange == "all" else exchange.upper()
            return f"❌ No {title.lower()} found on {where} right now. Please try again shortly."

        where = "All Exchanges" if exchange == "all" else exchange.upper()
        lines = [f"*Top {count} {title} - {where}*", ""]

        for i, coin in enumerate(gainers, 1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."

            exch = coin['exchange'].upper()
            change = coin['change_24h']
            sign = "+" if change > 0 else ""
            url = coin.get('url', '')

            line = f"{emoji} {md_bold(coin['symbol'])} ({exch})\n"
            line += f"   💰 {format_price(coin['price'])}\n"
            line += f"   📊 {sign}{change:.2f}%\n"
            line += f"   📈 Vol: {format_volume(coin['volume_24h'])}"
            if url:
                line += f"\n   🔗 [Trade on {exch}]({url})"

            lines.append(line)

        lines.append("\n_Updated: Just now_")
        lines.append("\n💡 Click links to trade immediately!")

        return "\n".join(lines)

    @staticmethod
    def _alert(header: str, symbol: str, exchange: str, price: float, move_line: str,
               volume: float, url: str, footer: str) -> str:
        """Common layout for price alerts"""
        message = (
            f"{header}\n\n"
            f"🪙 {md_bold(symbol)}\n"
            f"📍 Exchange: {exchange.upper()}\n"
            f"💰 Price: {format_price(price)}\n"
            f"{move_line}\n"
            f"📊 Volume: {format_volume(volume)}\n"
        )
        if url:
            message += f"🔗 [Trade Now]({url})\n"
        message += f"\n{footer}"
        return message

    @staticmethod
    def format_spike_alert(symbol: str, exchange: str, price: float, change: float, volume: float, url: str = "") -> str:
        """Format daily spike alert message"""
        return BotMessages._alert(
            "🔥 *DAILY GAINER ALERT!*", symbol, exchange, price,
            f"📈 Gain: +{change:.2f}% (24h)", volume, url,
            "⚡ This coin is running today! DYOR."
        )

    @staticmethod
    def format_pump_alert(symbol: str, exchange: str, price: float, change_5m: float, volume: float, url: str = "") -> str:
        """Format volatility pump alert message"""
        return BotMessages._alert(
            "🚀 *PUMP DETECTED!*", symbol, exchange, price,
            f"⚡ *Move: +{change_5m:.2f}% (5m)*", volume, url,
            "⚠️ High volatility alert! DYOR."
        )

    @staticmethod
    def format_early_pump_alert(
        symbol: str,
        exchange: str,
        price: float,
        change_24h: float,
        volume: float,
        pump_score: int,
        confidence: str,
        url: str = ""
    ) -> str:
        """Format early pump detection alert message"""
        if confidence == "HIGH":
            header = "🚨 *HIGH PROBABILITY PUMP*"
        else:
            header = "🔮 *POTENTIAL PUMP DETECTED*"

        message = (
            f"{header}\n\n"
            f"🪙 {md_bold(symbol)}\n"
            f"📍 Exchange: {exchange.upper()}\n"
            f"💰 Price: {format_price(price)}\n"
            f"📈 24h: {'+' if change_24h >= 0 else ''}{change_24h:.2f}%\n"
            f"📊 Volume: {format_volume(volume)}\n\n"
            f"📊 *Pump Score: {pump_score}/100*\n"
            f"✅ Confidence: {confidence}\n\n"
            f"_Multi-factor analysis detected unusual activity._\n"
        )
        if url:
            message += f"🔗 [Trade Now]({url})\n"
        message += "\n⚠️ Early detection signal. DYOR!"
        return message

    @staticmethod
    def format_dump_alert(symbol: str, exchange: str, price: float, change_5m: float, volume: float, url: str = "") -> str:
        """Format volatility dump alert message (5-min crash)"""
        return BotMessages._alert(
            "💥 *DUMP DETECTED!*", symbol, exchange, price,
            f"📉 *Drop: {change_5m:.2f}% (5m)*", volume, url,
            "⚠️ Sharp drop detected! Check for short opportunities. DYOR."
        )

    @staticmethod
    def format_daily_dump_alert(symbol: str, exchange: str, price: float, change_24h: float, volume: float, url: str = "") -> str:
        """Format daily dump alert message (24h loser)"""
        return BotMessages._alert(
            "📉 *BIG DROP ALERT!*", symbol, exchange, price,
            f"🔻 Loss: {change_24h:.2f}% (24h)", volume, url,
            "⚠️ Major daily loser! Potential short or buy-the-dip opportunity. DYOR."
        )

    ALERTS_ENABLED = """
✅ *Alerts Enabled!*

You'll now receive real-time pump, dump and early-signal alerts.

Use "🎚️ Alert Types" to choose which alerts you get, and "🛠️ Filter Exchanges" to pick exchanges.

Stay ready for those pumps! 🚀
"""

    ALERTS_DISABLED = """
🔕 *Alerts Disabled*

You won't receive alert notifications anymore.

You can re-enable them anytime with /alerts
"""

    ALERT_TYPES_PROMPT = (
        "🎚️ *Alert Types*\n\n"
        "Select which alerts you want to receive:\n\n"
        "_Toggle each type on or off:_"
    )

    SELECT_EXCHANGE = "🏦 *Select Exchange*\n\nWhich exchange data would you like to see?"
    SELECT_COUNT = "🔢 *How many coins?*\n\nSelect the number of results to display:"

    LOADING = "⏳ *Fetching data...* Please wait."

    WATCHLIST_HELP = """
📋 *Watchlist Commands*

• `/watchlist` - View your watchlist
• `/watchlist add BTCUSDT` - Add a coin
• `/watchlist remove BTCUSDT` - Remove a coin
• `/watchlist clear` - Clear all coins

*Example:*
`/watchlist add BTC` → Adds BTCUSDT
`/watchlist add ETH` → Adds ETHUSDT
"""

    @staticmethod
    def alert_status(enabled: bool) -> str:
        status = "enabled ✅" if enabled else "disabled 🔕"
        return (
            f"*Alert Status:* {status}\n\n"
            "Get notified about early pump signals, 5-minute pumps & dumps, "
            "and big daily movers.\n\n"
            "Toggle your alert preference below:"
        )

    @staticmethod
    def format_watchlist(symbols: list) -> str:
        """Format user's watchlist for display"""
        if not symbols:
            return """
📋 *Your Watchlist*

_No coins in your watchlist yet._

Add coins with:
`/watchlist add BTCUSDT`
`/watchlist add ETH`

Watchlist coins are flagged ⭐ in alerts and reach you from every exchange!
"""

        header = f"📋 *Your Watchlist* ({len(symbols)} coins)\n\n"
        lines = [f"{i}. `{symbol}`" for i, symbol in enumerate(symbols, 1)]
        footer = "\n\n💡 Use `/watchlist remove SYMBOL` to remove a coin"

        return header + "\n".join(lines) + footer
