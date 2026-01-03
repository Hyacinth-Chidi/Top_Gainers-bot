from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from database.client import DatabaseClient
from datetime import datetime

from .keyboards import BotKeyboards
from .messages import BotMessages
from exchanges.client import ExchangeClient
from config import config

class BotHandlers:
    """Telegram bot command and callback handlers"""
    
    def __init__(self, exchange_client: ExchangeClient, db: DatabaseClient):
        self.exchange_client = exchange_client
        self.db = db
        self.keyboards = BotKeyboards()
        self.messages = BotMessages()
        
        # Store user context (exchange & count selection)
        self.user_context = {}
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        
        # Create or update user in database
        await self.db.create_or_update_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name
        )
        
        await update.message.reply_text(
            self.messages.WELCOME,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.keyboards.main_menu()
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        await update.message.reply_text(
            self.messages.HELP,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def gainers_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /gainers command - start the flow"""
        user_id = update.effective_user.id
        if user_id not in self.user_context:
            self.user_context[user_id] = {}
        self.user_context[user_id]['mode'] = 'gainers'
        
        await update.message.reply_text(
            self.messages.SELECT_EXCHANGE,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.keyboards.exchange_selection()
        )
        
    async def losers_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /losers command - start the flow"""
        user_id = update.effective_user.id
        if user_id not in self.user_context:
            self.user_context[user_id] = {}
        self.user_context[user_id]['mode'] = 'losers'
        
        await update.message.reply_text(
            self.messages.SELECT_EXCHANGE,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.keyboards.exchange_selection()
        )
    
    async def alerts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /alerts command"""
        user_id = update.effective_user.id
        
        # Get user from database
        user = await self.db.get_user(user_id)
        
        if not user:
            await update.message.reply_text("⚠️ Please use /start first!")
            return
        
        alerts_enabled = user.get('alerts_enabled', True)
        
        status = "enabled ✅" if alerts_enabled else "disabled 🔕"
        message = f"**Alert Status:** {status}\n\n"
        message += "Spike alerts notify you when futures gain 30-70%+ suddenly.\n\n"
        message += "Toggle your alert preference below:"
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.keyboards.alerts_toggle(alerts_enabled)
        )
    
    async def watchlist_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /watchlist command
        Usage:
            /watchlist - Show current watchlist
            /watchlist add BTCUSDT - Add symbol
            /watchlist remove BTCUSDT - Remove symbol
            /watchlist clear - Clear all
        """
        user_id = update.effective_user.id
        args = context.args if context.args else []
        
        # No args - show watchlist
        if not args:
            watchlist = await self.db.get_user_watchlist(user_id)
            message = self.messages.format_watchlist(watchlist)
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.watchlist_menu()
            )
            return
        
        action = args[0].lower()
        
        # Add symbol
        if action == "add":
            if len(args) < 2:
                await update.message.reply_text(
                    "⚠️ Please specify a symbol.\n\nExample: `/watchlist add BTCUSDT`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            symbol = args[1].upper()
            added = await self.db.add_to_watchlist(user_id, symbol)
            
            if added:
                # Normalize symbol for display
                display_symbol = symbol if symbol.endswith("USDT") else f"{symbol}USDT"
                await update.message.reply_text(
                    f"✅ **{display_symbol}** added to your watchlist!\n\nYou'll receive priority alerts for this coin.",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text(
                    f"ℹ️ **{symbol}** is already in your watchlist.",
                    parse_mode=ParseMode.MARKDOWN
                )
        
        # Remove symbol
        elif action == "remove" or action == "delete":
            if len(args) < 2:
                await update.message.reply_text(
                    "⚠️ Please specify a symbol.\n\nExample: `/watchlist remove BTCUSDT`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            symbol = args[1].upper()
            removed = await self.db.remove_from_watchlist(user_id, symbol)
            
            if removed:
                await update.message.reply_text(
                    f"🗑️ **{symbol}** removed from your watchlist.",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text(
                    f"ℹ️ **{symbol}** was not in your watchlist.",
                    parse_mode=ParseMode.MARKDOWN
                )
        
        # Clear all
        elif action == "clear":
            count = await self.db.clear_watchlist(user_id)
            if count > 0:
                await update.message.reply_text(
                    f"🗑️ Cleared **{count}** symbols from your watchlist.",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text(
                    "ℹ️ Your watchlist was already empty.",
                    parse_mode=ParseMode.MARKDOWN
                )
        
        # Show watchlist (explicit)
        elif action == "show" or action == "list":
            watchlist = await self.db.get_user_watchlist(user_id)
            message = self.messages.format_watchlist(watchlist)
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.watchlist_menu()
            )
        
        # Unknown action
        else:
            await update.message.reply_text(
                self.messages.WATCHLIST_HELP,
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all inline button callbacks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = update.effective_user.id
        
        # Route to appropriate handler based on callback data
        if data.startswith("exchange:"):
            await self._handle_exchange_selection(query, user_id, data)
        elif data.startswith("count:"):
            await self._handle_count_selection(query, user_id, data)
        elif data.startswith("alerts:"):
            await self._handle_alerts_toggle(query, user_id, data)
        elif data.startswith("menu:"):
            await self._handle_menu_selection(query, data)
        elif data.startswith("toggle_exch:"):
            await self._handle_exchange_filter_toggle(query, user_id, data)
        elif data.startswith("watchlist:"):
            await self._handle_watchlist_action(query, user_id, data)
        elif data.startswith("toggle_alert:"):
            await self._handle_alert_type_toggle(query, user_id, data)
    
    async def _handle_exchange_selection(self, query, user_id: int, data: str):
        """Handle exchange selection"""
        exchange = data.split(":")[1]
        
        # Store user's exchange choice
        if user_id not in self.user_context:
            self.user_context[user_id] = {}
        self.user_context[user_id]['exchange'] = exchange
        
        # Ask for count
        await query.edit_message_text(
            self.messages.SELECT_COUNT,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.keyboards.top_count_selection()
        )
    
    async def _handle_count_selection(self, query, user_id: int, data: str):
        """Handle count selection and fetch gainers"""
        count = int(data.split(":")[1])
        
        # Get exchange and mode from context
        context_data = self.user_context.get(user_id, {})
        exchange = context_data.get('exchange', 'all')
        mode = context_data.get('mode', 'gainers') # Default to gainers
        
        action_text = "gainers" if mode == "gainers" else "losers"
        title = "Gainers" if mode == "gainers" else "Losers"
        
        # Show loading message
        await query.answer(f"Fetching {action_text}...")
        
        # Fetch data based on mode
        if mode == 'gainers':
            if exchange == 'all':
                items = await self.exchange_client.get_top_gainers_all_exchanges(limit=count)
            else:
                items = await self.exchange_client.get_top_gainers(exchange, limit=count)
        else: # losers
            if exchange == 'all':
                items = await self.exchange_client.get_top_losers_all_exchanges(limit=count)
            else:
                items = await self.exchange_client.get_top_losers(exchange, limit=count)
        
        # Format and send results
        message = self.messages.format_gainers_list(items, exchange, count, title=title)
        
        await query.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.keyboards.back_to_menu()
        )
        
        # Clean up context
        if user_id in self.user_context:
            del self.user_context[user_id]
            
    async def _handle_exchange_filter_toggle(self, query, user_id: int, data: str):
        """Handle toggling of exchanges for alerts"""
        target_exch = data.split(":")[1]
        
        # Get current preferences
        prefs = await self.db.get_user_preferences(user_id)
        current_exchanges = set(prefs.get('alert_exchanges', ["binance", "bybit", "mexc", "bitget", "gateio"]))
        
        # Toggle
        if target_exch in current_exchanges:
            current_exchanges.remove(target_exch)
        else:
            current_exchanges.add(target_exch)
            
        # Save
        await self.db.update_user_alert_exchanges(user_id, list(current_exchanges))
        
        # Update keyboard
        await query.edit_message_reply_markup(
            reply_markup=self.keyboards.alerts_exchange_selection(current_exchanges)
        )
    
    async def _handle_alerts_toggle(self, query, user_id: int, data: str):
        """Handle alerts enable/disable"""
        action = data.split(":")[1]
        new_state = action == "enable"
        
        # Update user in database
        await self.db.update_user_alerts(user_id, new_state)
        
        message = self.messages.ALERTS_ENABLED if new_state else self.messages.ALERTS_DISABLED
        
        await query.edit_message_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.keyboards.alerts_toggle(new_state)
        )
    
    async def _handle_menu_selection(self, query, data: str):
        """Handle main menu selections"""
        action = data.split(":")[1]
        
        if action == "main":
            # Back to main menu - SEND NEW MESSAGE instead of editing
            await query.answer()
            await query.message.reply_text(
                "🏠 **Main Menu**\n\nWhat would you like to do?",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.main_menu()
            )
        elif action == "gainers":
            await query.answer()
            # Set context
            if query.from_user.id not in self.user_context:
                self.user_context[query.from_user.id] = {}
            self.user_context[query.from_user.id]['mode'] = 'gainers'
            
            await query.message.reply_text(
                self.messages.SELECT_EXCHANGE,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.exchange_selection()
            )
        elif action == "losers":
            await query.answer()
            # Set context
            if query.from_user.id not in self.user_context:
                self.user_context[query.from_user.id] = {}
            self.user_context[query.from_user.id]['mode'] = 'losers'
            
            await query.message.reply_text(
                self.messages.SELECT_EXCHANGE,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.exchange_selection()
            )
        elif action == "alerts":
            user_id = query.from_user.id
            user = await self.db.get_user(user_id)
            
            if user:
                alerts_enabled = user.get('alerts_enabled', True)
                status = "enabled ✅" if alerts_enabled else "disabled 🔕"
                message = f"**Alert Status:** {status}\n\n"
                message += "Toggle your alert preference below:"
                
                await query.answer()
                await query.message.reply_text(
                    message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=self.keyboards.alerts_toggle(alerts_enabled)
                )
        elif action == "filter_exchanges":
            user_id = query.from_user.id
            prefs = await self.db.get_user_preferences(user_id)
            if not prefs:
                await self.db.create_default_preferences(user_id)
                prefs = await self.db.get_user_preferences(user_id)
            
            # Default to all if not set
            current_exchanges = set(prefs.get('alert_exchanges', ["binance", "bybit", "mexc", "bitget", "gateio"]))
            
            await query.answer()
            await query.message.reply_text(
                "🛠️ **Filter Exchanges**\n\nSelect which exchanges you want to receive alerts from:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.alerts_exchange_selection(current_exchanges)
            )
        elif action == "alert_types":
            user_id = query.from_user.id
            alert_types = await self.db.get_user_alert_types(user_id)
            
            await query.answer()
            await query.message.reply_text(
                "🎚️ **Alert Types**\n\n"
                "Select which alerts you want to receive:\n\n"
                "_Toggle each type on or off:_",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.alert_types_selection(alert_types)
            )
        elif action == "help":
            await query.answer()
            await query.message.reply_text(
                self.messages.HELP,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.back_to_menu()
            )
        elif action == "watchlist":
            user_id = query.from_user.id
            watchlist = await self.db.get_user_watchlist(user_id)
            message = self.messages.format_watchlist(watchlist)
            
            await query.answer()
            await query.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.watchlist_menu()
            )
    
    async def _handle_watchlist_action(self, query, user_id: int, data: str):
        """Handle watchlist button actions"""
        action = data.split(":")[1]
        
        if action == "add_prompt":
            await query.answer()
            await query.message.reply_text(
                "➕ **Add to Watchlist**\n\n"
                "Send the symbol you want to add:\n\n"
                "Example: `/watchlist add BTCUSDT`\n"
                "Or just: `/watchlist add BTC`",
                parse_mode=ParseMode.MARKDOWN
            )
        elif action == "clear":
            count = await self.db.clear_watchlist(user_id)
            if count > 0:
                await query.answer(f"Cleared {count} coins!")
                await query.edit_message_text(
                    f"🗑️ Cleared **{count}** symbols from your watchlist.\n\n"
                    "Your watchlist is now empty.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=self.keyboards.watchlist_menu()
                )
            else:
                await query.answer("Watchlist already empty")
                await query.edit_message_text(
                    "ℹ️ Your watchlist was already empty.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=self.keyboards.watchlist_menu()
                )
    
    async def _handle_alert_type_toggle(self, query, user_id: int, data: str):
        """Handle toggling individual alert types on/off"""
        alert_type = data.split(":")[1]
        
        # Toggle the alert type
        new_state = await self.db.toggle_alert_type(user_id, alert_type)
        
        # Get updated alert types for keyboard refresh
        alert_types = await self.db.get_user_alert_types(user_id)
        
        # Map alert type to display name
        type_names = {
            "early_pumps": "🔮 Early Pump Signals",
            "confirmed_pumps": "🚀 Confirmed Pumps",
            "dumps": "💥 Dump Alerts",
            "daily_spikes": "🔥 Daily Gainers",
            "daily_dumps": "📉 Daily Losers"
        }
        
        type_name = type_names.get(alert_type, alert_type)
        state_text = "enabled ✅" if new_state else "disabled ❌"
        
        await query.answer(f"{type_name} {state_text}")
        
        await query.edit_message_text(
            "🎚️ **Alert Types**\n\n"
            "Select which alerts you want to receive:\n\n"
            "_Toggle each type on or off:_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.keyboards.alert_types_selection(alert_types)
        )
    
    # ==================== ADMIN COMMANDS ====================
    
    def _is_admin(self, user_id: int) -> bool:
        """Check if user is an admin"""
        return user_id in config.ADMIN_USER_IDS
    
    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /broadcast command - Send message to all users (Admin only)
        Usage: /broadcast Your message here
        """
        user_id = update.effective_user.id
        
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You don't have permission to use this command.")
            return
        
        # Get message to broadcast
        if not context.args:
            await update.message.reply_text(
                "⚠️ Please provide a message to broadcast.\n\n"
                "Usage: `/broadcast Your message here`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        broadcast_message = " ".join(context.args)
        
        # Get all users
        users = await self.db.get_all_users()
        
        if not users:
            await update.message.reply_text("ℹ️ No users to broadcast to.")
            return
        
        # Send status
        status_msg = await update.message.reply_text(
            f"📡 Broadcasting to {len(users)} users...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Broadcast to all users
        success = 0
        failed = 0
        
        for user in users:
            try:
                # Skip banned users
                if await self.db.is_banned(user['id']):
                    continue
                    
                await context.bot.send_message(
                    chat_id=user['id'],
                    text=f"📢 **Announcement**\n\n{broadcast_message}",
                    parse_mode=ParseMode.MARKDOWN
                )
                success += 1
            except Exception:
                failed += 1
        
        await status_msg.edit_text(
            f"✅ **Broadcast Complete**\n\n"
            f"• Sent: {success}\n"
            f"• Failed: {failed}\n"
            f"• Total: {len(users)}",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def stats_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats_admin command - Show bot statistics (Admin only)"""
        user_id = update.effective_user.id
        
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔ You don't have permission to use this command.")
            return
        
        # Get stats
        stats = await self.db.get_bot_stats()
        
        message = f"""
📊 **Bot Statistics**

👥 **Users:**
• Total: {stats['total_users']}
• Active (24h): {stats['active_24h']}
• Alerts Enabled: {stats['alerts_enabled']}
• Banned: {stats['banned_users']}

📋 **Watchlists:**
• Users with watchlist: {stats['users_with_watchlist']}
• Total items tracked: {stats['total_watchlist_items']}

🔔 **Alerts:**
• Total sent (all time): {stats['alerts_sent_total']}

📈 **Exchanges Monitored:** {len(config.EXCHANGES)}
• {', '.join(e.upper() for e in config.EXCHANGES)}
"""
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    async def ban_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ban command - Ban a user (Admin only)
        Usage: /ban <user_id> [reason]
        """
        admin_id = update.effective_user.id
        
        if not self._is_admin(admin_id):
            await update.message.reply_text("⛔ You don't have permission to use this command.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "⚠️ Please provide a user ID to ban.\n\n"
                "Usage: `/ban <user_id> [reason]`\n"
                "Example: `/ban 123456789 Spam`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⚠️ Invalid user ID. Must be a number.")
            return
        
        # Prevent banning admins
        if target_user_id in config.ADMIN_USER_IDS:
            await update.message.reply_text("⚠️ Cannot ban an admin.")
            return
        
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
        
        banned = await self.db.ban_user(target_user_id, admin_id, reason)
        
        if banned:
            await update.message.reply_text(
                f"🚫 **User Banned**\n\n"
                f"• User ID: `{target_user_id}`\n"
                f"• Reason: {reason}",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                f"ℹ️ User `{target_user_id}` is already banned.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def unban_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /unban command - Unban a user (Admin only)
        Usage: /unban <user_id>
        """
        admin_id = update.effective_user.id
        
        if not self._is_admin(admin_id):
            await update.message.reply_text("⛔ You don't have permission to use this command.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "⚠️ Please provide a user ID to unban.\n\n"
                "Usage: `/unban <user_id>`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⚠️ Invalid user ID. Must be a number.")
            return
        
        unbanned = await self.db.unban_user(target_user_id)
        
        if unbanned:
            await update.message.reply_text(
                f"✅ **User Unbanned**\n\n"
                f"• User ID: `{target_user_id}`",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                f"ℹ️ User `{target_user_id}` was not banned.",
                parse_mode=ParseMode.MARKDOWN
            )