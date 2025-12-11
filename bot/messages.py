from typing import List, Dict

class BotMessages:
    """Message templates for the bot"""
    
    WELCOME = """
👋 Welcome to **Top Gainers Bot**!

I help you track the hottest futures/derivatives gainers across major exchanges.

🎯 **Features:**
• View top 5/10/20 gainers on any exchange
• Real-time alerts for 30-70% spikes
• Track Binance, Bybit, MEXC & Bitget

📊 **Quick Start:**
Use /gainers to see top performers
Use /alerts to manage notifications

Let's find those pumps! 🚀
"""
    
    HELP = """
🆘 **How to Use Top Gainers Bot**

**Commands:**
/gainers - View top gainers by exchange
/alerts - Enable/disable spike alerts
/help - Show this help message

**How Alerts Work:**
🚨 You'll be notified when any futures contract gains 30-70%+ suddenly
📊 Alerts include: Symbol, Exchange, Price, % Gain

**Exchanges Tracked:**
• Binance Futures
• Bybit Derivatives
• MEXC Futures
• Bitget Futures

**Tips:**
✓ Use filters to focus on specific exchanges
✓ Enable alerts to never miss big moves
✓ Check multiple times a day for best results

Questions? Feedback? Use the feedback button below any message.
"""
    
    @staticmethod
    def format_gainers_list(gainers: List[Dict], exchange: str, count: int) -> str:
        """Format list of gainers into readable message"""
        if not gainers:
            return f"❌ No gainers found on {exchange.upper()} right now."
        
        header = f"📈 **Top {count} Gainers"
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
            
            # Format volume in millions/billions
            if volume >= 1_000_000_000:
                vol_str = f"${volume/1_000_000_000:.2f}B"
            elif volume >= 1_000_000:
                vol_str = f"${volume/1_000_000:.2f}M"
            else:
                vol_str = f"${volume/1_000:.2f}K"
            
            line = f"{emoji} **{symbol}** ({exch})\n"
            line += f"   💰 ${price:.4f}\n"
            line += f"   📊 +{change}%\n"
            line += f"   📈 Vol: {vol_str}"
            
            lines.append(line)
        
        lines.append("\n_Updated: Just now_")
        lines.append("\n💡 Go to your preferred exchange to trade these coins!")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_spike_alert(symbol: str, exchange: str, price: float, change: float, volume: float) -> str:
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

⚡ This coin just spiked! Check your exchange now!
"""
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
    
    SELECT_EXCHANGE = "📊 **Select an exchange to view top gainers:**"
    SELECT_COUNT = "🔢 **How many top gainers do you want to see?**"
    
    LOADING = "⏳ Fetching latest data from exchanges..."