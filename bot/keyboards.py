from telegram import InlineKeyboardButton, InlineKeyboardMarkup

class BotKeyboards:
    """Inline keyboard layouts for the bot"""
    
    @staticmethod
    def exchange_selection():
        """Keyboard for selecting exchange"""
        keyboard = [
            [
                InlineKeyboardButton("🌐 All Exchanges", callback_data="exchange:all")
            ],
            [
                InlineKeyboardButton("🟡 Binance", callback_data="exchange:binance"),
                InlineKeyboardButton("🔷 Bybit", callback_data="exchange:bybit"),
            ],
            [
                InlineKeyboardButton("🟢 MEXC", callback_data="exchange:mexc"),
                InlineKeyboardButton("🔵 Bitget", callback_data="exchange:bitget"),
            ],
            [
                InlineKeyboardButton("🟣 Gate.io", callback_data="exchange:gateio"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def top_count_selection():
        """Keyboard for selecting top N count"""
        keyboard = [
            [
                InlineKeyboardButton("Top 5", callback_data="count:5"),
                InlineKeyboardButton("Top 10", callback_data="count:10"),
                InlineKeyboardButton("Top 20", callback_data="count:20"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def back_to_menu():
        """Keyboard with back to menu button"""
        keyboard = [
            [
                InlineKeyboardButton("🔙 Back to Menu", callback_data="menu:main"),
            ],
            [
                InlineKeyboardButton("🔄 View Gainers Again", callback_data="menu:gainers"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def alerts_toggle(enabled: bool):
        """Keyboard for toggling alerts"""
        status = "🔔 ON" if enabled else "🔕 OFF"
        action = "disable" if enabled else "enable"
        
        keyboard = [
            [
                InlineKeyboardButton(
                    f"Alerts: {status} - Click to {action.upper()}", 
                    callback_data=f"alerts:{action}"
                )
            ],
            [
                InlineKeyboardButton("🔙 Back to Menu", callback_data="menu:main"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def main_menu():
        """Main menu keyboard"""
        keyboard = [
            [
                InlineKeyboardButton("📈 View Gainers", callback_data="menu:gainers"),
            ],
            [
                InlineKeyboardButton("🔔 Alert Settings", callback_data="menu:alerts"),
            ],
            [
                InlineKeyboardButton("ℹ️ Help", callback_data="menu:help"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)