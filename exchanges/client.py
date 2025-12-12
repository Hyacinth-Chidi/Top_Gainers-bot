import ccxt
import asyncio
from typing import List, Dict, Optional
from datetime import datetime

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
                'defaultType': 'future',  # Binance uses 'future'
            }
        },
        'bybit': {
            'enableRateLimit': True,
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
    
    async def get_top_gainers(
        self, 
        exchange_name: str, 
        limit: int = 10
    ) -> List[Dict]:
        """
        Get top gainers from a specific exchange
        
        Args:
            exchange_name: Exchange to query (binance, bybit, mexc, bitget, gateio)
            limit: Number of top gainers to return (5, 10, or 20)
        
        Returns:
            List of dicts with symbol, price, change%, volume data
        """
        if exchange_name not in self.exchanges:
            raise ValueError(f"Exchange {exchange_name} not supported")
        
        exchange = self.exchanges[exchange_name]
        max_retries = 2
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                # Fetch all futures tickers with timeout
                tickers = await asyncio.wait_for(
                    asyncio.to_thread(exchange.fetch_tickers),
                    timeout=30
                )
                
                # Handle None response
                if not tickers:
                    print(f"No tickers returned from {exchange_name}")
                    return []
                
                # Filter for USDT perpetual futures and extract data
                gainers = []
                for symbol, ticker in tickers.items():
                    try:
                        # Only process USDT perpetual contracts
                        if not ticker or not isinstance(ticker, dict):
                            continue
                        
                        # Check for USDT pairs - handle both formats
                        # Some exchanges use /USDT:USDT or /USDT
                        if 'USDT' not in symbol:
                            continue
                        
                        # Skip if not a trading pair
                        if '/' not in symbol:
                            continue
                        
                        percent_change = ticker.get('percentage')
                        
                        # Skip if no percentage change data
                        if percent_change is None:
                            continue
                        
                        if percent_change > 0:
                            # Clean up symbol - remove :USDT suffix if present
                            clean_symbol = symbol.split(':')[0].replace('/', '')
                            
                            gainers.append({
                                'symbol': clean_symbol,
                                'exchange': exchange_name,
                                'price': ticker.get('last', 0) or 0,
                                'change_24h': round(percent_change, 2),
                                'volume_24h': ticker.get('quoteVolume', 0) or 0,
                                'timestamp': datetime.utcnow()
                            })
                    except Exception as e:
                        # Skip individual ticker errors
                        continue
                
                # Sort by percentage change (descending) and return top N
                gainers.sort(key=lambda x: x['change_24h'], reverse=True)
                return gainers[:limit]
                
            except (asyncio.TimeoutError, Exception) as e:
                if attempt < max_retries - 1:
                    print(f"Retry {attempt + 1}/{max_retries} for {exchange_name} in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    print(f"Error fetching data from {exchange_name}: {e}")
                    return []
        
        return []
    
    async def get_top_gainers_all_exchanges(self, limit: int = 10) -> List[Dict]:
        """
        Get top gainers across all exchanges
        
        Args:
            limit: Number of top gainers to return
        
        Returns:
            Combined list sorted by change%
        """
        all_gainers = []
        
        # Fetch from all exchanges concurrently
        tasks = [
            self.get_top_gainers(exchange_name, limit=50)  # Get more to have better selection
            for exchange_name in self.exchanges.keys()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine all results
        for result in results:
            if isinstance(result, list):
                all_gainers.extend(result)
        
        # Sort by change% and return top N
        all_gainers.sort(key=lambda x: x['change_24h'], reverse=True)
        return all_gainers[:limit]
    
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
                            'timestamp': datetime.utcnow()
                        }
                except:
                    continue
            
            return None
            
        except Exception as e:
            print(f"Error fetching {symbol} from {exchange_name}: {e}")
            return None
    
    def close_all(self):
        """Close all exchange connections"""
        for exchange in self.exchanges.values():
            if hasattr(exchange, 'close'):
                exchange.close()