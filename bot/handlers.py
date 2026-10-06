import asyncio
import re
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest
from database.client import DatabaseClient, ALL_EXCHANGES, normalize_symbol

from .keyboards import BotKeyboards
from .messages import BotMessages
from .utils import safe_send, SendResult
from exchanges.client import ExchangeClient
from config import config

# A plausible ticker: letters/digits only, optionally with a USDT suffix
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,20}$")


class BotHandlers:
    """Telegram bot command and callback handlers"""

    def __init__(self, exchange_client: ExchangeClient, db: DatabaseClient):
        self.exchange_client = exchange_client
        self.db = db
        self.keyboards = BotKeyboards()
        self.messages = BotMessages()

        # Store user context (exchange & count selection)
        self.user_context = {}

    async def _is_blocked(self, update: Update) -> bool:
        """Banned users can't use the bot"""
        user = update.effective_user
        if not user or self._is_admin(user.id):
            return False
        return await self.db.is_banned(user.id)

    def _set_mode(self, user_id: int, mode: str):
        self.user_context.setdefault(user_id, {})['mode'] = mode

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if await self._is_blocked(update):
            return
        user = update.effective_user
        returning = await self.db.get_user(user.id) is not None
        await self._register(user)

        await update.message.reply_text(
            self.messages.welcome(user.first_name, returning=returning),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.keyboards.main_menu()
        )

    async def _register(self, user):
        """Create or update the user so every command works without /start"""
        await self.db.create_or_update_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name
        )

    async def _get_or_create_user(self, tg_user) -> dict:
        user = await self.db.get_user(tg_user.id)
        if not user:
            await self._register(tg_user)
            user = await self.db.get_user(tg_user.id) or {}
        return user

    async def unknown_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Friendly reply to text or commands the bot doesn't understand"""
        if not update.message or await self._is_blocked(update):
            return
        await update.message.reply_text(
            self.messages.UNKNOWN,
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
        await self._start_list_flow(update, 'gainers')

    async def losers_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /losers command - start the flow"""
        await self._start_list_flow(update, 'losers')

    async def _start_list_flow(self, update: Update, mode: str):
        if await self._is_blocked(update):
            return
        self._set_mode(update.effective_user.id, mode)
        await update.message.reply_text(
            self.messages.SELECT_EXCHANGE,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.keyboards.exchange_selection()
        )

    async def alerts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /alerts command"""
        if await self._is_blocked(update):
            return
        user = await self._get_or_create_user(update.effective_user)
        alerts_enabled = user.get('alerts_enabled', False)
        await update.message.reply_text(
            self.messages.alert_status(alerts_enabled),
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
        if await self._is_blocked(update):
            return
        user_id = update.effective_user.id
        args = context.args if context.args else []
        action = args[0].lower() if args else "show"

        if action in ("show", "list"):
            watchlist = await self.db.get_user_watchlist(user_id)
            await update.message.reply_text(
                self.messages.format_watchlist(watchlist),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.watchlist_menu()
            )

        elif action in ("add", "remove", "delete"):
            verb = "add" if action == "add" else "remove"
            if len(args) < 2:
                await update.message.reply_text(
                    f"Which coin? For example: `/watchlist {verb} BTC`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            raw = args[1].upper().replace("/", "").replace("-", "").replace("_", "")
            if not _SYMBOL_RE.match(raw):
                await update.message.reply_text(
                    "🤔 That doesn't look like a coin symbol. Try something like `BTC` or `BTCUSDT`.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            symbol = normalize_symbol(raw)

            if verb == "add":
                if await self.db.add_to_watchlist(user_id, symbol):
                    user = await self._get_or_create_user(update.effective_user)
                    text = self.messages.watchlist_added(symbol, user.get('alerts_enabled', False))
                else:
                    text = f"ℹ️ `{symbol}` is already on your watchlist."
            else:
                if await self.db.remove_from_watchlist(user_id, symbol):
                    text = f"🗑️ `{symbol}` removed from your watchlist."
                else:
                    text = f"ℹ️ `{symbol}` wasn't on your watchlist."
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

        elif action == "clear":
            count = await self.db.clear_watchlist(user_id)
            if count > 0:
                text = f"🗑️ Removed *{count}* coin{'s' if count != 1 else ''} from your watchlist."
            else:
                text = "ℹ️ Your watchlist is already empty."
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

        else:
            await update.message.reply_text(
                self.messages.WATCHLIST_HELP,
                parse_mode=ParseMode.MARKDOWN
            )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle all inline button callbacks.

        Each handler answers the callback query exactly once - Telegram
        rejects a second answer, which used to abort some handlers.
        """
        query = update.callback_query
        data = query.data or ""
        user_id = update.effective_user.id

        if await self._is_blocked(update):
            await query.answer("⛔ Your access to this bot has been restricted.", show_alert=True)
            return

        routes = {
            "exchange": self._handle_exchange_selection,
            "count": self._handle_count_selection,
            "alerts": self._handle_alerts_toggle,
            "menu": self._handle_menu_selection,
            "toggle_exch": self._handle_exchange_filter_toggle,
            "watchlist": self._handle_watchlist_action,
            "toggle_alert": self._handle_alert_type_toggle,
        }
        prefix, _, value = data.partition(":")
        handler = routes.get(prefix)

        if handler is None:
            await query.answer()
            return

        try:
            await handler(query, user_id, value)
        except BadRequest as e:
            # Pressing a button that doesn't change anything is harmless
            if "message is not modified" not in str(e).lower():
                raise

    async def _handle_exchange_selection(self, query, user_id: int, exchange: str):
        """Handle exchange selection"""
        await query.answer()
        self.user_context.setdefault(user_id, {})['exchange'] = exchange

        await query.edit_message_text(
            self.messages.SELECT_COUNT,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.keyboards.top_count_selection()
        )

    async def _handle_count_selection(self, query, user_id: int, value: str):
        """Handle count selection and fetch gainers/losers"""
        try:
            count = max(1, min(int(value), 20))
        except ValueError:
            await query.answer()
            return

        context_data = self.user_context.pop(user_id, {})
        exchange = context_data.get('exchange', 'all')
        mode = context_data.get('mode', 'gainers')
        title = "Gainers" if mode == "gainers" else "Losers"

        await query.answer(f"Fetching {title.lower()}...")
        await query.edit_message_text(self.messages.LOADING, parse_mode=ParseMode.MARKDOWN)

        if mode == 'gainers':
            if exchange == 'all':
                items = await self.exchange_client.get_top_gainers_all_exchanges(limit=count)
            else:
                items = await self.exchange_client.get_top_gainers(exchange, limit=count)
        else:
            if exchange == 'all':
                items = await self.exchange_client.get_top_losers_all_exchanges(limit=count)
            else:
                items = await self.exchange_client.get_top_losers(exchange, limit=count)

        message = self.messages.format_gainers_list(items, exchange, count, title=title)

        # Replace the loading message with the results
        await query.edit_message_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=self.keyboards.back_to_menu(mode)
        )

    async def _handle_exchange_filter_toggle(self, query, user_id: int, target_exch: str):
        """Handle toggling of exchanges for alerts"""
        await query.answer()
        if target_exch not in ALL_EXCHANGES:
            return

        prefs = await self.db.get_user_preferences(user_id) or {}
        current_exchanges = set(prefs.get('alert_exchanges', ALL_EXCHANGES))
        current_exchanges ^= {target_exch}  # Toggle

        # Save in a stable order
        await self.db.update_user_alert_exchanges(
            user_id, [e for e in ALL_EXCHANGES if e in current_exchanges]
        )

        await query.edit_message_reply_markup(
            reply_markup=self.keyboards.alerts_exchange_selection(current_exchanges)
        )

    async def _handle_alerts_toggle(self, query, user_id: int, action: str):
        """Handle alerts enable/disable"""
        await query.answer()
        new_state = action == "enable"

        await self.db.update_user_alerts(user_id, new_state)
        if new_state:
            # Make sure the user has preferences so alert type toggles work
            await self.db.create_default_preferences(user_id)

        message = self.messages.ALERTS_ENABLED if new_state else self.messages.ALERTS_DISABLED

        await query.edit_message_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=self.keyboards.alerts_toggle(new_state)
        )

    async def _handle_menu_selection(self, query, user_id: int, action: str):
        """Handle main menu selections (each sends a new message)"""
        await query.answer()
        reply = query.message.reply_text

        if action == "main":
            await reply(
                "🏠 *Main menu*\n\nWhat would you like to check?",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.main_menu()
            )
        elif action in ("gainers", "losers"):
            self._set_mode(user_id, action)
            await reply(
                self.messages.SELECT_EXCHANGE,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.exchange_selection()
            )
        elif action == "alerts":
            user = await self._get_or_create_user(query.from_user)
            alerts_enabled = user.get('alerts_enabled', False)
            await reply(
                self.messages.alert_status(alerts_enabled),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.alerts_toggle(alerts_enabled)
            )
        elif action == "filter_exchanges":
            await self.db.create_default_preferences(user_id)
            prefs = await self.db.get_user_preferences(user_id) or {}
            current_exchanges = set(prefs.get('alert_exchanges', ALL_EXCHANGES))

            await reply(
                self.messages.FILTER_EXCHANGES_PROMPT,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.alerts_exchange_selection(current_exchanges)
            )
        elif action == "alert_types":
            alert_types = await self.db.get_user_alert_types(user_id)
            await reply(
                self.messages.ALERT_TYPES_PROMPT,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.alert_types_selection(alert_types)
            )
        elif action == "help":
            await reply(
                self.messages.HELP,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.back_to_menu()
            )
        elif action == "watchlist":
            watchlist = await self.db.get_user_watchlist(user_id)
            await reply(
                self.messages.format_watchlist(watchlist),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.watchlist_menu()
            )

    async def _handle_watchlist_action(self, query, user_id: int, action: str):
        """Handle watchlist button actions"""
        if action == "add_prompt":
            await query.answer()
            await query.message.reply_text(
                self.messages.WATCHLIST_ADD_PROMPT,
                parse_mode=ParseMode.MARKDOWN
            )
        elif action == "clear":
            count = await self.db.clear_watchlist(user_id)
            if count > 0:
                await query.answer(f"Cleared {count} coins!")
                text = f"🗑️ Removed *{count}* coin{'s' if count != 1 else ''} from your watchlist."
            else:
                await query.answer("Watchlist already empty")
                text = "ℹ️ Your watchlist is already empty."
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboards.watchlist_menu()
            )
        else:
            await query.answer()

    async def _handle_alert_type_toggle(self, query, user_id: int, alert_type: str):
        """Handle toggling individual alert types on/off"""
        type_names = {
            "early_pumps": "🔮 Early Pump Signals",
            "confirmed_pumps": "🚀 Confirmed Pumps",
            "dumps": "💥 Dump Alerts",
            "daily_spikes": "🔥 Daily Gainers",
            "daily_dumps": "📉 Daily Losers",
            "dex_alerts": "🌐 DEX Alerts (Solana)",
            "market_moves": "🌍 Market-wide moves",
        }
        if alert_type not in type_names:
            await query.answer()
            return

        new_state = await self.db.toggle_alert_type(user_id, alert_type)
        alert_types = await self.db.get_user_alert_types(user_id)

        state_text = "enabled ✅" if new_state else "disabled ❌"
        await query.answer(f"{type_names[alert_type]} {state_text}")

        await query.edit_message_text(
            self.messages.ALERT_TYPES_PROMPT,
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
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ You don't have permission to use this command.")
            return

        # Keep the admin's formatting (newlines etc.): strip only the command itself,
        # which may be "/broadcast" or "/broadcast@botname"
        full_text = update.message.text or ""
        parts = full_text.split(maxsplit=1)
        broadcast_message = parts[1].strip() if len(parts) > 1 else ""

        if not broadcast_message:
            await update.message.reply_text(
                "⚠️ Please provide a message to broadcast.\n\n"
                "Usage: `/broadcast Your message here`\n\n"
                "💡 Tip: You can use multiple lines for formatting!",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        users = await self.db.get_all_users()
        if not users:
            await update.message.reply_text("ℹ️ No users to broadcast to.")
            return

        banned = await self.db.get_banned_user_ids()
        recipients = [u['id'] for u in users if u.get('id') not in banned]

        status_msg = await update.message.reply_text(
            f"📡 Broadcasting to {len(recipients)} users..."
        )

        success = failed = blocked = 0
        text = f"📢 *Announcement*\n\n{broadcast_message}"

        for user_id in recipients:
            # safe_send falls back to plain text if the admin's Markdown is invalid
            result = await safe_send(context.bot, user_id, text, disable_web_page_preview=False)
            if result == SendResult.OK:
                success += 1
            elif result == SendResult.BLOCKED:
                blocked += 1
            else:
                failed += 1
            await asyncio.sleep(0.05)  # Respect Telegram rate limits

        await status_msg.edit_text(
            f"✅ *Broadcast Complete*\n\n"
            f"• Sent: {success}\n"
            f"• Blocked bot: {blocked}\n"
            f"• Failed: {failed}\n"
            f"• Skipped (banned): {len(users) - len(recipients)}\n"
            f"• Total users: {len(users)}",
            parse_mode=ParseMode.MARKDOWN
        )

    async def stats_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats_admin command - Show bot statistics (Admin only)"""
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ You don't have permission to use this command.")
            return

        stats = await self.db.get_bot_stats()

        message = f"""
📊 *Bot Statistics*

👥 *Users:*
• Total: {stats['total_users']}
• Active (24h): {stats['active_24h']}
• Alerts Enabled: {stats['alerts_enabled']}
• Banned: {stats['banned_users']}

📋 *Watchlists:*
• Users with watchlist: {stats['users_with_watchlist']}
• Total items tracked: {stats['total_watchlist_items']}

🔔 *Alerts:*
• Total sent (all time): {stats['alerts_sent_total']}

📈 *Exchanges Monitored:* {len(config.EXCHANGES)}
• {', '.join(e.upper() for e in config.EXCHANGES)}

🌐 *DEX Tracking:* {'ON' if config.DEX_ENABLED and config.BIRDEYE_API_KEY else 'OFF'}
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

        if target_user_id in config.ADMIN_USER_IDS:
            await update.message.reply_text("⚠️ Cannot ban an admin.")
            return

        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"

        if await self.db.ban_user(target_user_id, admin_id, reason):
            # Plain text: the reason is free-form and may contain Markdown characters
            await update.message.reply_text(
                f"🚫 User Banned\n\n"
                f"• User ID: {target_user_id}\n"
                f"• Reason: {reason}"
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
        if not self._is_admin(update.effective_user.id):
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

        if await self.db.unban_user(target_user_id):
            await update.message.reply_text(
                f"✅ *User Unbanned*\n\n"
                f"• User ID: `{target_user_id}`",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                f"ℹ️ User `{target_user_id}` was not banned.",
                parse_mode=ParseMode.MARKDOWN
            )
