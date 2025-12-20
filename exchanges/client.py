import ccxt
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from config import config

class ExchangeClient:
    """Unified client for fetching futures data from multiple exchanges"""
    
    SUPPORTED_EXCHANGES = {
        'binance': ccxt.binance,
        'bybit': ccxt.bybit,
        'mexc': ccxt.mexc,
        'bitget': ccxt.bitget,
        'gateio': ccxt.gateio,
    }
    
    # Exchange-specific configurations
    EXCHANGE_CONFIGS = {
        'binance': {
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',  # USDT-M Perpetuals (was 'future' which is Coin-M)
            }
        },
        'bybit': {
            'enableRateLimit': True,
            'hostname': config.BYBIT_HOSTNAME,  # Regional endpoint: bybit.com, bybit.us, bybit.eu
            'options': {
                'defaultType': 'linear',  # Bybit uses 'linear' for USDT perpetuals
            }
        },
        'mexc': {
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
            }
        },
        'bitget': {
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
            }
        },
        'gateio': {
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
            }
        },
    }
    
    def __init__(self):
        self.exchanges = {}
        self._initialize_exchanges()
    
    def _initialize_exchanges(self):
        """Initialize exchange connections"""
        for name, exchange_class in self.SUPPORTED_EXCHANGES.items():
            try:
                config = self.EXCHANGE_CONFIGS.get(name, {'enableRateLimit': True})
                exchange = exchange_class(config)
                self.exchanges[name] = exchange
                print(f"✓ Connected to {name.upper()}")
            except Exception as e:
                print(f"✗ Failed to connect to {name}: {e}")
    
    def _generate_trade_link(self, exchange: str, symbol: str) -> str:
        """Generate direct trading link for the exchange"""
        # Symbol format is typically "BTC" or "BTC/USDT"
        base = symbol.replace("/USDT", "").replace("USDT", "")
        
        links = {
            'binance': f"https://www.binance.com/en/futures/{base}USDT",
            'bybit': f"https://www.bybit.com/trade/usdt/{base}USDT",
            'mexc': f"https://www.mexc.com/futures/{base}_USDT",
            'bitget': f"https://www.bitget.com/futures/usdt/{base}USDT",
            'gateio': f"https://www.gate.io/futures_trade/USDT/{base}_USDT",
        }
        return links.get(exchange, "")

    async def _fetch_exchange_tickers(self, exchange_name: str) -> List[Dict]:
        """Fetch and process tickers from an exchange (internal helper)"""
        if exchange_name not in self.exchanges:
            return []
            
        exchange = self.exchanges[exchange_name]
        try:
            # Prepare params
            params = {}
            if exchange_name == 'bybit':
                params = {'category': 'linear'}

            # Load markets first to get status info
            if not exchange.markets:
                await asyncio.wait_for(
                    asyncio.to_thread(exchange.load_markets),
                    timeout=30
                )

            tickers = await asyncio.wait_for(
                asyncio.to_thread(exchange.fetch_tickers, None, params),
                timeout=30
            )
            
            if not tickers:
                return []
                
            processed = []
            for symbol, ticker in tickers.items():
                try:
                    # Filter logic
                    if not ticker or not isinstance(ticker, dict): continue
                    if 'USDT' not in symbol: continue
                    if '/' not in symbol: continue
                    
                    # Check if market is active (filter out delisted/inactive pairs)
                    market = exchange.markets.get(symbol)
                    if market:
                        # Skip inactive markets
                        if not market.get('active', True):
                            continue
                        # Skip markets with specific inactive statuses
                        info = market.get('info', {})
                        status = info.get('status') or info.get('contractStatus')
                        if status and status.upper() in ['BREAK', 'CLOSE', 'SETTLING', 'PENDING_TRADING']:
                            continue
                    
                    percent_change = ticker.get('percentage')
                    if percent_change is None: continue
                    
                    # Filter out pairs with zero/negligible volume (likely inactive)
                    volume = ticker.get('quoteVolume', 0) or 0
                    if volume < 1000:  # Less than $1000 volume = likely dead
                        continue
                    
                    # Clean symbol
                    clean_symbol = symbol.split(':')[0].replace('/', '')
                    
                    processed.append({
                        'symbol': clean_symbol,
                        'exchange': exchange_name,
                        'price': ticker.get('last', 0) or 0,
                        'change_24h': round(percent_change, 2),
                        'volume_24h': volume,
                        'timestamp': datetime.utcnow(),
                        'url': self._generate_trade_link(exchange_name, clean_symbol)
                    })
                except:
                    continue
            
            return processed
            
        except Exception as e:
            print(f"Error fetching from {exchange_name}: {e}")
            return []

    async def get_top_gainers(self, exchange_name: str, limit: int = 10) -> List[Dict]:
        """Get top gainers from a specific exchange"""
        tickers = await self._fetch_exchange_tickers(exchange_name)
        # Sort descending (High to Low)
        tickers.sort(key=lambda x: x['change_24h'], reverse=True)
        return tickers[:limit]

    async def get_top_losers(self, exchange_name: str, limit: int = 10) -> List[Dict]:
        """Get top losers from a specific exchange"""
        tickers = await self._fetch_exchange_tickers(exchange_name)
        # Sort ascending (Low to High - biggest drops first)
        tickers.sort(key=lambda x: x['change_24h'], reverse=False)
        return tickers[:limit]
    
    async def get_top_gainers_all_exchanges(self, limit: int = 10) -> List[Dict]:
        """Get top gainers across all exchanges"""
        tasks = [self._fetch_exchange_tickers(name) for name in self.exchanges.keys()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_coins = []
        for res in results:
            if isinstance(res, list):
                all_coins.extend(res)
                
        all_coins.sort(key=lambda x: x['change_24h'], reverse=True)
        return all_coins[:limit]

    async def get_top_losers_all_exchanges(self, limit: int = 10) -> List[Dict]:
        """Get top losers across all exchanges"""
        tasks = [self._fetch_exchange_tickers(name) for name in self.exchanges.keys()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_coins = []
        for res in results:
            if isinstance(res, list):
                all_coins.extend(res)
                
        all_coins.sort(key=lambda x: x['change_24h'], reverse=False)
        return all_coins[:limit]
    
    async def get_current_price(self, symbol: str, exchange_name: str) -> Optional[Dict]:
        """
        Get current price for a specific symbol on an exchange
        Used for spike detection
        """
        if exchange_name not in self.exchanges:
            return None
        
        exchange = self.exchanges[exchange_name]
        
        try:
            # Try different symbol formats
            for symbol_format in [symbol, f"{symbol.replace('USDT', '')}/USDT", f"{symbol}/USDT"]:
                try:
                    ticker = await asyncio.to_thread(
                        exchange.fetch_ticker, 
                        symbol_format
                    )
                    
                    if ticker:
                        return {
                            'symbol': symbol,
                            'exchange': exchange_name,
                            'price': ticker.get('last', 0) or 0,
                            'change_24h': ticker.get('percentage', 0) or 0,
                            'volume_24h': ticker.get('quoteVolume', 0) or 0,
                            'timestamp': datetime.utcnow(),
                            'url': self._generate_trade_link(exchange_name, symbol)
                        }
                except:
                    continue
            
            return None
            
        except Exception as e:
            # print(f"Error fetching {symbol} from {exchange_name}: {e}")
            return None
    
    def close_all(self):
        """Close all exchange connections"""
        for exchange in self.exchanges.values():
            if hasattr(exchange, 'close'):
                exchange.close()