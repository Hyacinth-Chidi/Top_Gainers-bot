import asyncio
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from database.client import DatabaseClient

from config import config
from exchanges.client import ExchangeClient
from bot.handlers import BotHandlers
from monitoring.tracker import SpikeTracker

class TopGainersBot:
    """Main application class"""
    
    def __init__(self):
        # Validate configuration
        config.validate()
        
        # Initialize components
        self.db = DatabaseClient()
        self.exchange_client = ExchangeClient()
        self.application = None
        self.spike_tracker = None
        self.monitoring_task = None
    
    async def post_init(self, application: Application) -> None:
        """Called after bot initialization"""
        # Connect to database
        await self.db.connect()
        
        # Initialize spike tracker
        self.spike_tracker = SpikeTracker(self.exchange_client, application.bot, self.db)
        
        # Start spike monitoring in background
        self.monitoring_task = asyncio.create_task(self.spike_tracker.start())
        
        print("✅ Bot is running!")
        print(f"📊 Monitoring {len(config.EXCHANGES)} exchanges")
        print(f"⏱️  Check interval: {config.SPIKE_CHECK_INTERVAL}s")
        print(f"📈 Spike threshold: {config.MIN_SPIKE_THRESHOLD}%-{config.MAX_SPIKE_THRESHOLD}%")
    
    async def post_shutdown(self, application: Application) -> None:
        """Called before bot shutdown"""
        print("\n🛑 Shutting down...")
        
        # Stop monitoring
        if self.spike_tracker:
            await self.spike_tracker.stop()
        
        if self.monitoring_task and not self.monitoring_task.done():
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Close exchange connections
        self.exchange_client.close_all()
        
        # Disconnect database
        await self.db.disconnect()
        
        print("✓ Shutdown complete")
    
    def run(self):
        """Build and run the bot"""
        print("🚀 Starting Top Gainers Bot...")
        
        # Build telegram application with lifecycle hooks
        self.application = (
            Application.builder()
            .token(config.TELEGRAM_BOT_TOKEN)
            .post_init(self.post_init)
            .post_shutdown(self.post_shutdown)
            .build()
        )
        
        # Initialize handlers
        handlers = BotHandlers(self.exchange_client, self.db)
        
        # Register command handlers
        self.application.add_handler(CommandHandler("start", handlers.start_command))
        self.application.add_handler(CommandHandler("help", handlers.help_command))
        self.application.add_handler(CommandHandler("gainers", handlers.gainers_command))
        self.application.add_handler(CommandHandler("losers", handlers.losers_command))
        self.application.add_handler(CommandHandler("alerts", handlers.alerts_command))
        self.application.add_handler(CommandHandler("watchlist", handlers.watchlist_command))
        
        # Admin commands
        self.application.add_handler(CommandHandler("broadcast", handlers.broadcast_command))
        self.application.add_handler(CommandHandler("stats_admin", handlers.stats_admin_command))
        self.application.add_handler(CommandHandler("ban", handlers.ban_command))
        self.application.add_handler(CommandHandler("unban", handlers.unban_command))
        
        # Register callback query handler for buttons
        self.application.add_handler(CallbackQueryHandler(handlers.button_callback))
        
        print("✓ Registered command handlers")
        
        # Run the bot with polling (this is synchronous and blocks)
        self.application.run_polling(
            allowed_updates=['message', 'callback_query'],
            drop_pending_updates=True
        )

def main():
    """Main entry point"""
    try:
        bot = TopGainersBot()
        bot.run()
    except KeyboardInterrupt:
        print("\n⚠️ Interrupt received...")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()