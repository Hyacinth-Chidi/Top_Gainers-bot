from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from database.client import DatabaseClient
from datetime import datetime

from .keyboards import BotKeyboards
from .messages import BotMessages
from exchanges.client import ExchangeClient

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
        elif action == "help":
            await query.answer()
            await query.message.reply_text(
                self.messages.HELP,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.back_to_menu()
            )