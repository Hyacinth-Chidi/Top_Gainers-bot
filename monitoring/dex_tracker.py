import asyncio
from datetime import datetime, timedelta
from typing import Dict
from telegram import Bot

from dex.solana import SolanaClient, TokenActivity, WalletTrade
from database.client import DatabaseClient
from bot.utils import escape_md, format_price
from config import config
from .broadcaster import AlertBroadcaster


class DexTracker:
    """
    Monitor DEX activity for pump signals.
    Sends separate alerts for DEX activity including wallet addresses.
    """

    CHECK_INTERVAL = 60                       # Seconds between scans
    BIG_BUY_COOLDOWN = timedelta(hours=1)     # Per transaction
    DEMAND_COOLDOWN = timedelta(hours=2)      # Per token, for "high demand" alerts
    MIN_DEMAND_BUYERS = 10                    # Unique buyers needed for a demand alert
    DEMAND_BUYER_RATIO = 2.0                  # Buyers must outnumber sellers by this much

    def __init__(self, bot: Bot, db: DatabaseClient):
        self.bot = bot
        self.db = db
        self.broadcaster = AlertBroadcaster(bot, db)

        self.BIG_BUY_USD = config.DEX_BIG_BUY_USD
        self.WHALE_BUY_USD = config.DEX_WHALE_BUY_USD

        self.solana = SolanaClient(api_key=config.BIRDEYE_API_KEY or None)
        self.solana.BIG_BUY_THRESHOLD_USD = self.BIG_BUY_USD

        # Tracking state
        self.is_running = False
        self.alerted_big_buys: Dict[str, datetime] = {}   # tx_hash -> alert_time
        self.alerted_demand: Dict[str, datetime] = {}     # token address -> alert_time

    async def start(self):
        """Start the DEX monitoring loop"""
        self.is_running = True
        print("🌐 DEX Tracker started (Solana)")

        while self.is_running:
            try:
                await self._check_solana_activity()
                self._cleanup_old_data()
            except Exception as e:
                print(f"DEX Tracker error: {e}")
            await asyncio.sleep(self.CHECK_INTERVAL)

    async def stop(self):
        """Stop the DEX tracker"""
        self.is_running = False
        await self.solana.close()
        print("🛑 DEX Tracker stopped")

    async def _check_solana_activity(self):
        """Check Solana DEX for pumping tokens and big buys"""
        await self.broadcaster.refresh()
        if not self.broadcaster.has_recipients():
            return  # Nobody to alert - save API quota

        gainers = await self.solana.get_top_gainers(limit=30)

        for token in gainers:
            try:
                address = token.get("address")
                if not address:
                    continue

                activity = await self.solana.analyze_token(address)
                if not activity:
                    continue

                # Trending list has the most reliable symbol
                if token.get("symbol"):
                    activity.token_symbol = token["symbol"]

                # Check for BIG BUYS (wallet included!)
                for big_buy in activity.big_buys:
                    if self._should_alert_big_buy(big_buy):
                        big_buy.token_symbol = activity.token_symbol
                        await self._send_big_buy_alert(big_buy, activity)
                        self.alerted_big_buys[big_buy.tx_hash] = datetime.utcnow()

                # Many more buyers than sellers = bullish
                if self._is_high_demand(activity) and self._should_alert_demand(address):
                    await self._send_activity_alert(activity)
                    self.alerted_demand[address] = datetime.utcnow()

                # Rate limiting
                await asyncio.sleep(0.5)

            except Exception as e:
                print(f"Error processing token {token.get('symbol')}: {e}")
                continue

    def _is_high_demand(self, activity: TokenActivity) -> bool:
        return (
            activity.unique_buyers >= self.MIN_DEMAND_BUYERS
            and activity.unique_buyers >= activity.unique_sellers * self.DEMAND_BUYER_RATIO
        )

    async def _send_big_buy_alert(self, trade: WalletTrade, activity: TokenActivity):
        """Send alert for a big buy with wallet address"""
        if trade.amount_usd >= self.WHALE_BUY_USD:
            emoji = "🐋"
            title = "WHALE BUY DETECTED"
        else:
            emoji = "💰"
            title = "BIG BUY DETECTED"

        wallet_short = self.solana.format_wallet(trade.wallet)
        wallet_link = self.solana.get_solscan_link(trade.wallet)
        tx_link = self.solana.get_tx_link(trade.tx_hash)

        message = (
            f"{emoji} *{title}* {emoji}\n\n"
            f"🪙 *Token:* {escape_md(trade.token_symbol)}\n"
            f"💵 *Amount:* ${trade.amount_usd:,.2f}\n"
            f"📊 *Tokens:* {trade.amount_tokens:,.2f}\n"
            f"💲 *Price:* {format_price(trade.price)}\n\n"
            f"👛 *Wallet:* [{wallet_short}]({wallet_link})\n"
            f"🔗 *TX:* [View on Solscan]({tx_link})\n\n"
            f"📈 *Token Stats:*\n"
            f"   • Buyers: {activity.unique_buyers}\n"
            f"   • Sellers: {activity.unique_sellers}\n"
            f"   • Buy Vol: ${activity.total_buy_volume:,.0f}\n"
            f"   • Sell Vol: ${activity.total_sell_volume:,.0f}\n\n"
            f"🔗 _Solana DEX_ • `{activity.token_address}`"
        )

        await self.broadcaster.broadcast(message, "dex_alerts")

    async def _send_activity_alert(self, activity: TokenActivity):
        """Send alert for unusual buying activity (many buyers)"""
        message = (
            f"🔥 *HIGH DEMAND DETECTED* 🔥\n\n"
            f"🪙 *Token:* {escape_md(activity.token_symbol)}\n"
            f"👥 *Buyers:* {activity.unique_buyers} (vs {activity.unique_sellers} sellers)\n"
            f"💵 *Buy Volume:* ${activity.total_buy_volume:,.0f}\n"
            f"📉 *Sell Volume:* ${activity.total_sell_volume:,.0f}\n"
        )

        if activity.top_buyers:
            message += "\n📊 *Top Buyers:*\n"
            for i, buyer in enumerate(activity.top_buyers[:5], 1):
                wallet_short = self.solana.format_wallet(buyer["wallet"])
                net_vol = buyer.get("net_volume", 0) or 0
                message += f"   {i}. {wallet_short}: ${net_vol:,.0f}\n"

        message += f"\n🔗 _Solana DEX_ • `{activity.token_address}`"

        await self.broadcaster.broadcast(message, "dex_alerts")

    def _should_alert_big_buy(self, trade: WalletTrade) -> bool:
        """Check if we should alert on this trade"""
        if trade.amount_usd < self.BIG_BUY_USD or not trade.tx_hash:
            return False
        last = self.alerted_big_buys.get(trade.tx_hash)
        return last is None or datetime.utcnow() - last >= self.BIG_BUY_COOLDOWN

    def _should_alert_demand(self, address: str) -> bool:
        last = self.alerted_demand.get(address)
        return last is None or datetime.utcnow() - last >= self.DEMAND_COOLDOWN

    def _cleanup_old_data(self):
        """Clean up old tracking data"""
        now = datetime.utcnow()
        self.alerted_big_buys = {
            k: v for k, v in self.alerted_big_buys.items()
            if now - v < self.BIG_BUY_COOLDOWN * 2
        }
        self.alerted_demand = {
            k: v for k, v in self.alerted_demand.items()
            if now - v < self.DEMAND_COOLDOWN
        }
        self.solana.cleanup_old_alerts()
