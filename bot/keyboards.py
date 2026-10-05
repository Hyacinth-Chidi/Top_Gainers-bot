from telegram import InlineKeyboardButton, InlineKeyboardMarkup

class BotKeyboards:
    """Inline keyboard layouts for the bot"""
    
    @staticmethod
    def exchange_selection():
        """Keyboard for selecting exchange"""
        keyboard = [
            [
                InlineKeyboardButton("🌐 All exchanges", callback_data="exchange:all")
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
    def back_to_menu(mode: str = "gainers"):
        """Keyboard with back to menu button"""
        label = "🔄 Losers again" if mode == "losers" else "🔄 Gainers again"
        keyboard = [
            [
                InlineKeyboardButton("🏠 Main menu", callback_data="menu:main"),
            ],
            [
                InlineKeyboardButton(label, callback_data=f"menu:{mode}"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def alerts_toggle(enabled: bool):
        """Keyboard for toggling alerts"""
        if enabled:
            toggle = InlineKeyboardButton("🔕 Turn alerts off", callback_data="alerts:disable")
        else:
            toggle = InlineKeyboardButton("🔔 Turn alerts on", callback_data="alerts:enable")
        
        keyboard = [
            [toggle],
            [
                InlineKeyboardButton("🎚️ Alert types", callback_data="menu:alert_types"),
            ],
            [
                InlineKeyboardButton("🏦 Exchanges", callback_data="menu:filter_exchanges"),
            ],
            [
                InlineKeyboardButton("🏠 Main menu", callback_data="menu:main"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def alert_types_selection(alert_types: dict):
        """Keyboard for selecting which alert types to receive"""
        
        def get_text(label, key):
            is_enabled = alert_types.get(key, False)
            return f"{'✅' if is_enabled else '❌'} {label}"
        
        keyboard = [
            [
                InlineKeyboardButton(
                    get_text("🔮 Early Pump Signals", "early_pumps"), 
                    callback_data="toggle_alert:early_pumps"
                ),
            ],
            [
                InlineKeyboardButton(
                    get_text("🚀 Confirmed Pumps", "confirmed_pumps"), 
                    callback_data="toggle_alert:confirmed_pumps"
                ),
            ],
            [
                InlineKeyboardButton(
                    get_text("💥 Dump Alerts", "dumps"), 
                    callback_data="toggle_alert:dumps"
                ),
            ],
            [
                InlineKeyboardButton(
                    get_text("🔥 Daily Gainers", "daily_spikes"), 
                    callback_data="toggle_alert:daily_spikes"
                ),
            ],
            [
                InlineKeyboardButton(
                    get_text("📉 Daily Losers", "daily_dumps"), 
                    callback_data="toggle_alert:daily_dumps"
                ),
            ],
            [
                InlineKeyboardButton(
                    get_text("🌐 DEX Alerts (Solana)", "dex_alerts"), 
                    callback_data="toggle_alert:dex_alerts"
                ),
            ],
            [
                InlineKeyboardButton("✅ Done", callback_data="menu:alerts"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def alerts_exchange_selection(enabled_exchanges: set):
        """Keyboard for selecting exchanges to alert on"""
        
        def get_text(name, key):
            is_enabled = key in enabled_exchanges
            return f"{'✅' if is_enabled else '❌'} {name}"

        keyboard = [
            [
                InlineKeyboardButton(get_text("Binance", "binance"), callback_data="toggle_exch:binance"),
                InlineKeyboardButton(get_text("Bybit", "bybit"), callback_data="toggle_exch:bybit"),
            ],
            [
                InlineKeyboardButton(get_text("MEXC", "mexc"), callback_data="toggle_exch:mexc"),
                InlineKeyboardButton(get_text("Bitget", "bitget"), callback_data="toggle_exch:bitget"),
            ],
            [
                InlineKeyboardButton(get_text("Gate.io", "gateio"), callback_data="toggle_exch:gateio"),
            ],
            [
                InlineKeyboardButton("✅ Done", callback_data="menu:alerts"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def main_menu():
        """Main menu keyboard"""
        keyboard = [
            [
                InlineKeyboardButton("📈 Top gainers", callback_data="menu:gainers"),
                InlineKeyboardButton("📉 Top losers", callback_data="menu:losers"),
            ],
            [
                InlineKeyboardButton("⭐ Watchlist", callback_data="menu:watchlist"),
                InlineKeyboardButton("🔔 Alerts", callback_data="menu:alerts"),
            ],
            [
                InlineKeyboardButton("ℹ️ Help", callback_data="menu:help"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def watchlist_menu():
        """Watchlist action keyboard"""
        keyboard = [
            [
                InlineKeyboardButton("➕ Add coin", callback_data="watchlist:add_prompt"),
                InlineKeyboardButton("🗑️ Clear all", callback_data="watchlist:clear"),
            ],
            [
                InlineKeyboardButton("🏠 Main menu", callback_data="menu:main"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)