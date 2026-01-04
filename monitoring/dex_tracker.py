import asyncio
from datetime import datetime, timedelta
from typing import Dict, List
from telegram import Bot
from telegram.constants import ParseMode

from dex.solana import SolanaClient, TokenActivity, WalletTrade
from database.client import DatabaseClient
from bot.messages import BotMessages
from config import config


class DexTracker:
    """
    Monitor DEX activity for pump signals.
    Sends separate alerts for DEX activity including wallet addresses.
    """
    
    # Thresholds
    BIG_BUY_USD = 5000          # Alert on single buys > $5k
    WHALE_BUY_USD = 25000       # "Whale Alert" threshold
    MIN_VOLUME_SPIKE = 2.0     # 2x normal volume = spike
    
    def __init__(self, bot: Bot, db: DatabaseClient):
        self.bot = bot
        self.db = db
        self.messages = BotMessages()
        
        # Initialize Solana client
        # API key is optional but recommended for higher rate limits
        solana_api_key = getattr(config, 'BIRDEYE_API_KEY', None)
        self.solana = SolanaClient(api_key=solana_api_key)
        
        # Tracking state
        self.is_running = False
        self.monitored_tokens: Dict[str, datetime] = {}  # token -> last_check
        self.alerted_big_buys: Dict[str, datetime] = {}  # tx_hash -> alert_time
        
    async def start(self):
        """Start the DEX monitoring loop"""
        self.is_running = True
        print("🌐 DEX Tracker started (Solana)")
        
        while self.is_running:
            try:
                await self._check_solana_activity()
                self._cleanup_old_data()
                await asyncio.sleep(60)  # Check every 60 seconds
            except Exception as e:
                print(f"DEX Tracker error: {e}")
                await asyncio.sleep(30)
                
    async def stop(self):
        """Stop the DEX tracker"""
        self.is_running = False
        await self.solana.close()
        print("🛑 DEX Tracker stopped")
        
    async def _check_solana_activity(self):
        """Check Solana DEX for pumping tokens and big buys"""
        
        # Get top gainers
        gainers = await self.solana.get_top_gainers(limit=30)
        
        for token in gainers:
            try:
                address = token.get("address")
                if not address:
                    continue
                    
                # Analyze token for big buys
                activity = await self.solana.analyze_token(address)
                
                if not activity:
                    continue
                    
                # Check for BIG BUYS (wallet included!)
                for big_buy in activity.big_buys:
                    if self._should_alert_big_buy(big_buy):
                        await self._send_big_buy_alert(big_buy, activity)
                        self._mark_alerted(big_buy.tx_hash)
                        
                # Optional: Alert on high buyer/seller ratio
                if activity.unique_buyers > 10 and activity.unique_buyers > activity.unique_sellers * 2:
                    # More buyers than sellers = bullish
                    await self._send_activity_alert(activity)
                    
                # Rate limiting
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"Error processing token {token.get('symbol')}: {e}")
                continue
                
    async def _send_big_buy_alert(self, trade: WalletTrade, activity: TokenActivity):
        """Send alert for a big buy with wallet address"""
        
        # Determine alert type
        if trade.amount_usd >= self.WHALE_BUY_USD:
            emoji = "🐋"
            title = "WHALE BUY DETECTED"
        else:
            emoji = "💰"
            title = "BIG BUY DETECTED"
            
        # Format wallet (shortened + link)
        wallet_short = self.solana.format_wallet(trade.wallet)
        wallet_link = self.solana.get_solscan_link(trade.wallet)
        tx_link = self.solana.get_tx_link(trade.tx_hash)
        
        message = (
            f"{emoji} **{title}** {emoji}\n\n"
            f"🪙 **Token:** {trade.token_symbol}\n"
            f"💵 **Amount:** ${trade.amount_usd:,.2f}\n"
            f"📊 **Tokens:** {trade.amount_tokens:,.2f}\n"
            f"💲 **Price:** ${trade.price:.8f}\n\n"
            f"👛 **Wallet:** [{wallet_short}]({wallet_link})\n"
            f"🔗 **TX:** [View on Solscan]({tx_link})\n\n"
            f"📈 **Token Stats:**\n"
            f"   • Buyers: {activity.unique_buyers}\n"
            f"   • Sellers: {activity.unique_sellers}\n"
            f"   • Buy Vol: ${activity.total_buy_volume:,.0f}\n"
            f"   • Sell Vol: ${activity.total_sell_volume:,.0f}\n\n"
            f"🔗 _Solana DEX_"
        )
        
        # Send to users with DEX alerts enabled
        await self._broadcast_dex_alert(message)
        
    async def _send_activity_alert(self, activity: TokenActivity):
        """Send alert for unusual buying activity (many buyers)"""
        
        message = (
            f"🔥 **HIGH DEMAND DETECTED** 🔥\n\n"
            f"🪙 **Token:** {activity.token_symbol}\n"
            f"👥 **Buyers:** {activity.unique_buyers} (vs {activity.unique_sellers} sellers)\n"
            f"💵 **Buy Volume:** ${activity.total_buy_volume:,.0f}\n"
            f"📉 **Sell Volume:** ${activity.total_sell_volume:,.0f}\n\n"
            f"📊 **Top Buyers:**\n"
        )
        
        # Add top 5 buyers
        for i, buyer in enumerate(activity.top_buyers[:5], 1):
            wallet_short = self.solana.format_wallet(buyer["wallet"])
            net_vol = buyer.get("net_volume", 0)
            message += f"   {i}. {wallet_short}: ${net_vol:,.0f}\n"
            
        message += f"\n🔗 _Solana DEX_"
        
        await self._broadcast_dex_alert(message)
        
    async def _broadcast_dex_alert(self, message: str):
        """Send DEX alert to all users with DEX alerts enabled"""
        
        # Get users with alerts enabled
        users = await self.db.get_users_with_alerts_enabled()
        
        if not users:
            return
            
        for user in users:
            try:
                user_id = user['id']
                
                # Check if user has DEX alerts enabled
                # For now, send to all users with alerts on
                # TODO: Add dex_alerts preference
                
                # Check if banned
                if await self.db.is_banned(user_id):
                    continue
                    
                await self.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )
                await asyncio.sleep(0.05)
                
            except Exception as e:
                print(f"Failed to send DEX alert to {user_id}: {e}")
                
    def _should_alert_big_buy(self, trade: WalletTrade) -> bool:
        """Check if we should alert on this trade"""
        # Must be above threshold
        if trade.amount_usd < self.BIG_BUY_USD:
            return False
            
        # Check cooldown (same tx)
        if trade.tx_hash in self.alerted_big_buys:
            if datetime.utcnow() - self.alerted_big_buys[trade.tx_hash] < timedelta(hours=1):
                return False
                
        return True
        
    def _mark_alerted(self, tx_hash: str):
        """Mark transaction as alerted"""
        self.alerted_big_buys[tx_hash] = datetime.utcnow()
        
    def _cleanup_old_data(self):
        """Clean up old tracking data"""
        cutoff = datetime.utcnow() - timedelta(hours=2)
        
        self.alerted_big_buys = {
            k: v for k, v in self.alerted_big_buys.items()
            if v > cutoff
        }
        
        self.solana.cleanup_old_alerts()
