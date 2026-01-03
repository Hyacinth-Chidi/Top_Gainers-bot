from typing import List, Dict

class BotMessages:
    """Message templates for the bot"""
    
    WELCOME = """
👋 **Welcome to Top Gainers Bot!**

I track the crypto futures market to find the best trading opportunities for you. 🚀

🔔 **Important:** Alerts are **OFF** by default. 
To start receiving real-time Pump & Dump alerts, click "🔔 Alerts" below and enable them!

🎯 **What I Do:**
• 📈 **Gainers**: Top 5/10/20 winners 
• 📉 **Losers**: Top 5/10/20 dippers (buy the dip!)
• 📝 **Watchlist**: Track your favorite coins
• ⚡ **Pump Alerts**: Notification when price pumps 5%+ in 5 mins
• 💥 **Dump Alerts**: Notification when price drops 5%+ in 5 mins
• 🛡️ **Exchange Filter**: You choose which exchanges to track

📊 **Exchanges Supported:**
🟡 Binance • 🔷 Bybit • 🟢 MEXC • 🔵 Bitget • 🟣 Gate.io

👇 **Click a button below to start:**
"""
    
    HELP = """
🆘 **Top Gainers Bot Help**

I help you catch pumps, dumps, and trade volatility on major futures exchanges.

✨ **Main Commands:**
• /gainers - View top rising coins 📈
• /losers - View top falling coins 📉
• /watchlist - Manage your watchlist 📝
• /alerts - Configure your notifications 🔔

📝 **Watchlist Commands:**
• `/watchlist` - View your list
• `/watchlist add BTC` - Add a coin
• `/watchlist remove BTC` - Remove a coin
• `/watchlist clear` - Clear all

⚡ **About Alerts:**
I watch the market 24/7 and notify you when:
1. **Pump Alert**: A coin pumps >5% in 5 minutes 🚀
2. **Dump Alert**: A coin drops >5% in 5 minutes 💥
3. **Daily Gainer**: A coin hits +30% to +70% on the day 🔥
4. **Daily Loser**: A coin drops -30% to -70% on the day 📉

🛠️ **Settings:**
Use /alerts → "Filter Exchanges" to select only the exchanges you trade on.

💡 **Pro Tip:**
All alerts contain **Direct Trading Links**. Click the link to open the futures pair immediately!

_Questions? Feedback? Contact the developer._
"""
    
    @staticmethod
    def format_gainers_list(gainers: List[Dict], exchange: str, count: int, title: str = "Gainers") -> str:
        """Format list of coins into readable message"""
        if not gainers:
            return f"❌ No {title.lower()} found on {exchange.upper()} right now."
        
        header = f"**Top {count} {title}"
        if exchange != "all":
            header += f" - {exchange.upper()}**"
        else:
            header += " - All Exchanges**"
        
        lines = [header, ""]
        
        for i, gainer in enumerate(gainers, 1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            
            symbol = gainer['symbol']
            price = gainer['price']
            change = gainer['change_24h']
            volume = gainer['volume_24h']
            exch = gainer['exchange'].upper()
            url = gainer.get('url', '')
            
            # Format volume in millions/billions
            if volume >= 1_000_000_000:
                vol_str = f"${volume/1_000_000_000:.2f}B"
            elif volume >= 1_000_000:
                vol_str = f"${volume/1_000_000:.2f}M"
            else:
                vol_str = f"${volume/1_000:.2f}K"
            
            # Format title line
            line = f"{emoji} **{symbol}** ({exch})\n"
            line += f"   💰 ${price:.4f}\n"
            
            # Change color for gainers/losers if needed, but standard text is fine
            sign = "+" if change > 0 else ""
            line += f"   📊 {sign}{change}%\n"
            line += f"   📈 Vol: {vol_str}"
            
            if url:
                line += f"\n   🔗 [Trade on {exch}]({url})"
            
            lines.append(line)
        
        lines.append("\n_Updated: Just now_")
        lines.append("\n💡 Click links to trade immediately!")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_spike_alert(symbol: str, exchange: str, price: float, change: float, volume: float, url: str = "") -> str:
        """Format spike alert message"""
        # Format volume
        if volume >= 1_000_000_000:
            vol_str = f"${volume/1_000_000_000:.2f}B"
        elif volume >= 1_000_000:
            vol_str = f"${volume/1_000_000:.2f}M"
        else:
            vol_str = f"${volume/1_000:.2f}K"
        
        message = f"""
🚀 **SPIKE ALERT!**

🪙 **{symbol}**
📍 Exchange: {exchange.upper()}
💰 Price: ${price:.4f}
📈 Gain: +{change:.2f}%
📊 Volume: {vol_str}
"""
        if url:
            message += f"🔗 [Trade Now]({url})\n"
            
        message += "\n⚡ This coin just spiked! Check your exchange now!"
        return message.strip()
        
    @staticmethod
    def format_pump_alert(symbol: str, exchange: str, price: float, change_5m: float, volume: float, url: str = "") -> str:
        """Format volatility pump alert message"""
        # Format volume
        if volume >= 1_000_000_000:
            vol_str = f"${volume/1_000_000_000:.2f}B"
        elif volume >= 1_000_000:
            vol_str = f"${volume/1_000_000:.2f}M"
        else:
            vol_str = f"${volume/1_000:.2f}K"
        
        message = f"""
🚀 **PUMP DETECTED!**

🪙 **{symbol}**
📍 Exchange: {exchange.upper()}
💰 Price: ${price:.4f}
⚡ **Move: +{change_5m:.2f}% (5m)**
📊 Volume: {vol_str}
"""
        if url:
            message += f"🔗 [Trade Now]({url})\n"
            
        message += "\n⚠️ High volatility alert! DYOR."
        return message.strip()
    
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
        # Format volume
        if volume >= 1_000_000_000:
            vol_str = f"${volume/1_000_000_000:.2f}B"
        elif volume >= 1_000_000:
            vol_str = f"${volume/1_000_000:.2f}M"
        else:
            vol_str = f"${volume/1_000:.2f}K"
        
        # Choose emoji based on confidence
        if confidence == "HIGH":
            emoji = "🚨"
            header = "HIGH PROBABILITY PUMP"
        else:
            emoji = "🔮"
            header = "POTENTIAL PUMP DETECTED"
        
        message = f"""
{emoji} **{header}**

🪙 **{symbol}**
📍 Exchange: {exchange.upper()}
💰 Price: ${price:.6f}
📈 24h: {'+' if change_24h >= 0 else ''}{change_24h:.2f}%
📊 Volume: {vol_str}

📊 **Pump Score: {pump_score}/100**
✅ Confidence: {confidence}

_Multi-factor analysis detected unusual activity._
"""
        if url:
            message += f"🔗 [Trade Now]({url})\n"
            
        message += "\n⚠️ Early detection signal. DYOR!"
        return message.strip()
    
    @staticmethod
    def format_dump_alert(symbol: str, exchange: str, price: float, change_5m: float, volume: float, url: str = "") -> str:
        """Format volatility dump alert message (5-min crash)"""
        # Format volume
        if volume >= 1_000_000_000:
            vol_str = f"${volume/1_000_000_000:.2f}B"
        elif volume >= 1_000_000:
            vol_str = f"${volume/1_000_000:.2f}M"
        else:
            vol_str = f"${volume/1_000:.2f}K"
        
        message = f"""
💥 **DUMP DETECTED!**

🪙 **{symbol}**
📍 Exchange: {exchange.upper()}
💰 Price: ${price:.4f}
📉 **Drop: {change_5m:.2f}% (5m)**
📊 Volume: {vol_str}
"""
        if url:
            message += f"🔗 [Trade Now]({url})\n"
            
        message += "\n⚠️ Sharp drop detected! Check for short opportunities. DYOR."
        return message.strip()
    
    @staticmethod
    def format_daily_dump_alert(symbol: str, exchange: str, price: float, change_24h: float, volume: float, url: str = "") -> str:
        """Format daily dump alert message (24h loser)"""
        # Format volume
        if volume >= 1_000_000_000:
            vol_str = f"${volume/1_000_000_000:.2f}B"
        elif volume >= 1_000_000:
            vol_str = f"${volume/1_000_000:.2f}M"
        else:
            vol_str = f"${volume/1_000:.2f}K"
        
        message = f"""
📉 **BIG DROP ALERT!**

🪙 **{symbol}**
📍 Exchange: {exchange.upper()}
💰 Price: ${price:.4f}
🔻 Loss: {change_24h:.2f}% (24h)
📊 Volume: {vol_str}
"""
        if url:
            message += f"🔗 [Trade Now]({url})\n"
            
        message += "\n⚠️ Major daily loser! Potential short or buy-the-dip opportunity. DYOR."
        return message.strip()
    
    ALERTS_ENABLED = """
✅ **Alerts Enabled!**

You'll now receive notifications when any futures contract gains 30-70%+ suddenly.

Stay ready for those pumps! 🚀
"""
    
    ALERTS_DISABLED = """
🔕 **Alerts Disabled**

You won't receive spike notifications anymore.

You can re-enable them anytime with /alerts
"""
    
    SELECT_EXCHANGE = "🏦 **Select Exchange**\n\nWhich exchange data would you like to see?"
    SELECT_COUNT = "🔢 **How many coins?**\n\nSelect the number of results to display:"
    
    LOADING = "⏳ **Fetching data...** Please wait."
    
    WATCHLIST_HELP = """
📋 **Watchlist Commands**

• `/watchlist` - View your watchlist
• `/watchlist add BTCUSDT` - Add a coin
• `/watchlist remove BTCUSDT` - Remove a coin
• `/watchlist clear` - Clear all coins

**Example:**
`/watchlist add BTC` → Adds BTCUSDT
`/watchlist add ETH` → Adds ETHUSDT
"""
    
    @staticmethod
    def format_watchlist(symbols: list) -> str:
        """Format user's watchlist for display"""
        if not symbols:
            return """
📋 **Your Watchlist**

_No coins in your watchlist yet._

Add coins with:
`/watchlist add BTCUSDT`
`/watchlist add ETH`

Watchlist coins get **priority alerts** when they pump or dump!
"""
        
        header = f"📋 **Your Watchlist** ({len(symbols)} coins)\n\n"
        
        lines = []
        for i, symbol in enumerate(symbols, 1):
            lines.append(f"{i}. `{symbol}`")
        
        footer = "\n\n💡 Use `/watchlist remove SYMBOL` to remove a coin"
        
        return header + "\n".join(lines) + footer