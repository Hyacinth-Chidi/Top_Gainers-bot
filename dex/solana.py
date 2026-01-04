import asyncio
import httpx
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

@dataclass
class WalletTrade:
    """Represents a single trade by a wallet"""
    wallet: str
    token_address: str
    token_symbol: str
    side: str  # "buy" or "sell"
    amount_usd: float
    amount_tokens: float
    price: float
    timestamp: datetime
    tx_hash: str

@dataclass
class TokenActivity:
    """Aggregated activity for a token"""
    token_address: str
    token_symbol: str
    total_buy_volume: float
    total_sell_volume: float
    unique_buyers: int
    unique_sellers: int
    top_buyers: List[Dict]  # [{"wallet": "...", "volume": ...}, ...]
    big_buys: List[WalletTrade]  # Individual large purchases
    price_change_1h: float
    price_change_24h: float
    liquidity_usd: float

class SolanaClient:
    """
    Solana DEX client using Birdeye API for wallet-level tracking.
    Tracks top traders, big buys, and volume by wallet.
    """
    
    # Birdeye API (free tier: 100 req/min)
    BASE_URL = "https://public-api.birdeye.so"
    
    # Thresholds
    BIG_BUY_THRESHOLD_USD = 5000  # Alert on buys > $5k
    TOP_WALLETS_COUNT = 20
    
    def __init__(self, api_key: str = None):
        """
        Initialize Solana client.
        
        Args:
            api_key: Birdeye API key (optional, increases rate limit)
        """
        self.api_key = api_key
        self.headers = {
            "accept": "application/json",
        }
        if api_key:
            self.headers["X-API-KEY"] = api_key
            
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers=self.headers,
            timeout=30.0
        )
        
        # Cache for recent trades (avoid duplicate alerts)
        self.alerted_trades: Dict[str, datetime] = {}
        
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
        
    async def get_top_gainers(self, limit: int = 50) -> List[Dict]:
        """
        Get top gaining tokens on Solana DEX.
        
        Returns list of tokens with price change and volume.
        """
        try:
            response = await self.client.get(
                "/defi/token_trending",
                params={
                    "sort_by": "rank",
                    "sort_type": "asc",
                    "offset": 0,
                    "limit": limit
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                tokens = data.get("data", {}).get("tokens", [])
                
                result = []
                for token in tokens:
                    result.append({
                        "address": token.get("address"),
                        "symbol": token.get("symbol", "UNKNOWN"),
                        "name": token.get("name", ""),
                        "price": token.get("price", 0),
                        "price_change_24h": token.get("price_change_24h_percent", 0),
                        "volume_24h": token.get("volume_24h_usd", 0),
                        "liquidity": token.get("liquidity", 0),
                    })
                return result
            else:
                print(f"Birdeye API error: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"Error fetching Solana gainers: {e}")
            return []
            
    async def get_token_trades(self, token_address: str, limit: int = 100) -> List[WalletTrade]:
        """
        Get recent trades for a token with wallet addresses.
        
        This is the key feature - we can see WHO is buying/selling.
        """
        try:
            response = await self.client.get(
                f"/defi/txs/token",
                params={
                    "address": token_address,
                    "tx_type": "swap",
                    "limit": limit
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                txs = data.get("data", {}).get("items", [])
                
                trades = []
                for tx in txs:
                    try:
                        # Determine if buy or sell
                        # If token is in "to" field, it's a buy
                        is_buy = tx.get("to", {}).get("address") == token_address
                        
                        trade = WalletTrade(
                            wallet=tx.get("owner", ""),
                            token_address=token_address,
                            token_symbol=tx.get("to" if is_buy else "from", {}).get("symbol", "UNKNOWN"),
                            side="buy" if is_buy else "sell",
                            amount_usd=abs(float(tx.get("volume_usd", 0))),
                            amount_tokens=abs(float(tx.get("to" if is_buy else "from", {}).get("amount", 0))),
                            price=float(tx.get("price", 0)),
                            timestamp=datetime.fromtimestamp(tx.get("block_unix_time", 0)),
                            tx_hash=tx.get("tx_hash", "")
                        )
                        trades.append(trade)
                    except Exception as e:
                        continue
                        
                return trades
            else:
                return []
                
        except Exception as e:
            print(f"Error fetching token trades: {e}")
            return []
            
    async def get_top_traders(self, token_address: str) -> List[Dict]:
        """
        Get top 20 traders for a token by volume.
        
        Returns wallet addresses with their buy/sell volumes.
        """
        try:
            response = await self.client.get(
                f"/defi/v2/tokens/{token_address}/top_traders",
                params={"limit": self.TOP_WALLETS_COUNT}
            )
            
            if response.status_code == 200:
                data = response.json()
                traders = data.get("data", {}).get("items", [])
                
                result = []
                for trader in traders:
                    result.append({
                        "wallet": trader.get("owner", ""),
                        "buy_volume": trader.get("volume_buy", 0),
                        "sell_volume": trader.get("volume_sell", 0),
                        "net_volume": trader.get("volume_buy", 0) - trader.get("volume_sell", 0),
                        "trade_count": trader.get("trade_count", 0)
                    })
                return result
            else:
                return []
                
        except Exception as e:
            print(f"Error fetching top traders: {e}")
            return []
            
    async def analyze_token(self, token_address: str) -> Optional[TokenActivity]:
        """
        Full analysis of a token including wallet activity.
        """
        try:
            # Get recent trades
            trades = await self.get_token_trades(token_address, limit=100)
            
            if not trades:
                return None
                
            # Get top traders
            top_traders = await self.get_top_traders(token_address)
            
            # Analyze trades
            buys = [t for t in trades if t.side == "buy"]
            sells = [t for t in trades if t.side == "sell"]
            
            total_buy_volume = sum(t.amount_usd for t in buys)
            total_sell_volume = sum(t.amount_usd for t in sells)
            
            unique_buyers = len(set(t.wallet for t in buys))
            unique_sellers = len(set(t.wallet for t in sells))
            
            # Find BIG buys (> threshold)
            big_buys = [t for t in buys if t.amount_usd >= self.BIG_BUY_THRESHOLD_USD]
            
            # Get symbol from first trade
            symbol = trades[0].token_symbol if trades else "UNKNOWN"
            
            return TokenActivity(
                token_address=token_address,
                token_symbol=symbol,
                total_buy_volume=total_buy_volume,
                total_sell_volume=total_sell_volume,
                unique_buyers=unique_buyers,
                unique_sellers=unique_sellers,
                top_buyers=top_traders[:self.TOP_WALLETS_COUNT],
                big_buys=big_buys,
                price_change_1h=0,  # Would need separate API call
                price_change_24h=0,
                liquidity_usd=0
            )
            
        except Exception as e:
            print(f"Error analyzing token: {e}")
            return None
            
    def should_alert_trade(self, tx_hash: str) -> bool:
        """Check if we've already alerted on this trade (1 hour cooldown)"""
        if tx_hash in self.alerted_trades:
            if datetime.utcnow() - self.alerted_trades[tx_hash] < timedelta(hours=1):
                return False
        return True
        
    def mark_alerted(self, tx_hash: str):
        """Mark a trade as alerted"""
        self.alerted_trades[tx_hash] = datetime.utcnow()
        
    def cleanup_old_alerts(self):
        """Remove old entries from cache"""
        cutoff = datetime.utcnow() - timedelta(hours=2)
        self.alerted_trades = {
            k: v for k, v in self.alerted_trades.items()
            if v > cutoff
        }
        
    @staticmethod
    def format_wallet(wallet: str) -> str:
        """Format wallet address for display (shortened)"""
        if len(wallet) > 12:
            return f"{wallet[:6]}...{wallet[-4:]}"
        return wallet
        
    @staticmethod
    def get_solscan_link(wallet: str) -> str:
        """Generate Solscan link for wallet"""
        return f"https://solscan.io/account/{wallet}"
        
    @staticmethod
    def get_tx_link(tx_hash: str) -> str:
        """Generate Solscan link for transaction"""
        return f"https://solscan.io/tx/{tx_hash}"
