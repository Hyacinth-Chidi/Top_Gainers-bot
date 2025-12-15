from typing import List, Dict

class BotMessages:
    """Message templates for the bot"""
    
    WELCOME = """
👋 **Welcome to Top Gainers Bot!**

I track the crypto futures market to find the best trading opportunities for you. 🚀

🎯 **What I Do:**
• 📈 **Gainers**: Top 5/10/20 winners 
• 📉 **Losers**: Top 5/10/20 dippers (buy the dip!)
• ⚡ **Spike Alerts**: Notification when price pumps 5% in 5 mins
• 🛡️ **Exchange Filter**: You choose which exchanges to track

📊 **Exchanges Supported:**
🟡 Binance • 🔷 Bybit • 🟢 MEXC • 🔵 Bitget • 🟣 Gate.io

👇 **Click a button below to start:**
"""
    
    HELP = """
🆘 **Top Gainers Bot Help**

I help you catch pumps and trade volatility on major futures exchanges.

✨ **Main Commands:**
• /gainers - View top rising coins 📈
• /losers - View top falling coins 📉
• /alerts - Configure your notifications 🔔

⚡ **About Alerts:**
I watch the market 24/7 and notify you when:
1. **Volatility Spike**: A coin pumps >5% in 5 minutes 🚀
2. **Daily Gainer**: A coin hits +30% to +70% on the day 🔥

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