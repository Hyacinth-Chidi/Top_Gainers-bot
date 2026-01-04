import asyncio
import json
import websockets
from typing import Dict, Set, Callable, Optional
from datetime import datetime

class WebSocketClient:
    """
    Manages WebSocket connections to exchanges for real-time order book data.
    Implements a 'Sniper Mode' where it only subscribes to specific coins when needed.
    """
    
    # WebSocket Endpoints
    ENDPOINTS = {
        "binance": "wss://fstream.binance.com/stream",
        "mexc": "wss://wbs.mexc.com/ws",
        # "bybit": "wss://stream.bybit.com/v5/public/linear", 
    }
    
    def __init__(self):
        self.connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.active_subscriptions: Dict[str, Set[str]] = {ex: set() for ex in self.ENDPOINTS}
        self.order_book_cache: Dict[str, Dict] = {}  # { "symbol": { "bids": [], "asks": [], "timestamp": ... } }
        self.is_running = False
        self._lock = asyncio.Lock()
        self.last_ping: Dict[str, float] = {}
        
    async def start(self):
        """Start the WebSocket manager"""
        self.is_running = True
        print("🔌 WebSocket Client initialized (Sniper Mode: Binance + MEXC)")
        
        # Start connection loops for supported exchanges
        for exchange in self.ENDPOINTS:
            asyncio.create_task(self._maintain_connection(exchange))
            # Start ping loop for MEXC
            if exchange == "mexc":
                asyncio.create_task(self._mexc_heartbeat())
            
    async def stop(self):
        """Stop all connections"""
        self.is_running = False
        for exchange, ws in self.connections.items():
            await ws.close()
            
    async def subscribe_order_book(self, exchange: str, symbol: str):
        """
        Subscribe to a specific coin's order book.
        Used when the poller detects a potential pump.
        """
        exchange = exchange.lower()
        symbol = symbol.lower()
        
        if exchange not in self.ENDPOINTS:
            return
            
        async with self._lock:
            if symbol in self.active_subscriptions[exchange]:
                return  # Already subscribed
                
            self.active_subscriptions[exchange].add(symbol)
            print(f"🎯 Sniper targeting: {symbol} on {exchange}")
            
            # Send subscription message
            if exchange == "binance":
                await self._subscribe_binance(symbol)
            elif exchange == "mexc":
                await self._subscribe_mexc(symbol)
                
    async def unsubscribe_order_book(self, exchange: str, symbol: str):
        """Unsubscribe to free up resources"""
        exchange = exchange.lower()
        symbol = symbol.lower()
        
        async with self._lock:
            if symbol in self.active_subscriptions[exchange]:
                self.active_subscriptions[exchange].remove(symbol)
                
                # Cleanup cache
                cache_key = f"{exchange}:{symbol}"
                if cache_key in self.order_book_cache:
                    del self.order_book_cache[cache_key]
                
                # Send unsubscribe message
                if exchange == "binance":
                    await self._unsubscribe_binance(symbol)
                elif exchange == "mexc":
                    await self._unsubscribe_mexc(symbol)
                    
    async def get_order_book_imbalance(self, exchange: str, symbol: str) -> float:
        """
        Calculate Buy Pressure (Bid/Ask Ratio).
        Returns absolute percentage (0-100).
        > 50 means more Buys (Bids).
        """
        cache_key = f"{exchange.lower()}:{symbol.lower()}"
        data = self.order_book_cache.get(cache_key)
        
        if not data:
            return 50.0  # Neutral if no data
            
        # Analyze top 20 levels
        try:
            bids_volume = sum(float(qty) for price, qty in data['bids'][:20])
            asks_volume = sum(float(qty) for price, qty in data['asks'][:20])
        except (ValueError, IndexError):
            return 50.0 # Bad data
        
        total_volume = bids_volume + asks_volume
        if total_volume == 0:
            return 50.0
            
        buy_pressure = (bids_volume / total_volume) * 100
        return buy_pressure

    # ================== INTERNAL METHODS ==================

    async def _maintain_connection(self, exchange: str):
        """Keep the WebSocket alive"""
        while self.is_running:
            try:
                uri = self.ENDPOINTS[exchange]
                async with websockets.connect(uri) as ws:
                    self.connections[exchange] = ws
                    print(f"✅ Connected to {exchange} WebSocket")
                    
                    # Resubscribe to any active symbols (in case of reconnection)
                    for symbol in self.active_subscriptions[exchange]:
                        if exchange == "binance":
                            await self._subscribe_binance(symbol)
                        elif exchange == "mexc":
                            await self._subscribe_mexc(symbol)
                    
                    while self.is_running:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=60)
                            await self._handle_message(exchange, msg)
                        except asyncio.TimeoutError:
                            # Send ping if needed
                            if exchange == "mexc":
                                await ws.send(json.dumps({"method": "PING"}))
                        
            except Exception as e:
                print(f"⚠️ {exchange} WebSocket error: {e}")
                await asyncio.sleep(5)  # Reconnect delay

    async def _mexc_heartbeat(self):
        """Send periodic ping to MEXC"""
        while self.is_running:
            try:
                if "mexc" in self.connections:
                    ws = self.connections["mexc"]
                    await ws.send(json.dumps({"method": "PING"}))
            except:
                pass
            await asyncio.sleep(30)

    async def _handle_message(self, exchange: str, msg: str):
        """Process incoming messages"""
        try:
            data = json.loads(msg)
            
            if exchange == "binance":
                # Binance structure: {"stream": "btcusdt@depth20", "data": {...}}
                if "data" in data and "stream" in data:
                    stream = data["stream"]
                    symbol = stream.split("@")[0]
                    content = data["data"]
                    
                    cache_key = f"{exchange}:{symbol}"
                    self.order_book_cache[cache_key] = {
                        "bids": content["bids"],
                        "asks": content["asks"],
                        "timestamp": datetime.utcnow()
                    }
                    
            elif exchange == "mexc":
                # MEXC structure: {"c": "push.symbol", "d": {"deals": [{"p": "...", "v": "...", "t": ...}]}}
                # Depth structure: {"c": "push.depth", "d": {"asks": [...], "bids": [...]}}
                if "c" in data and data["c"].endswith("depth") and "d" in data:
                    # Channel name eg "spot@public.limit.depth.v3.api@BTCUSDT"
                    # We might need to map it back to symbol if not provided directly
                    if "s" in data: # Some messages have symbol
                        symbol = data["s"].lower()
                    elif "symbol" in data["d"]:
                        symbol = data["d"]["symbol"].lower()
                    else:
                        return # Cant identify symbol
                        
                    content = data["d"]
                    
                    # Store data
                    # MEXC format: {"asks": [{"p": "price", "v": "vol"}], ...}
                    # We need to normalize to [[price, qty], ...]
                    bids = [[x['p'], x['v']] for x in content.get('bids', [])]
                    asks = [[x['p'], x['v']] for x in content.get('asks', [])]
                    
                    cache_key = f"{exchange}:{symbol}"
                    self.order_book_cache[cache_key] = {
                        "bids": bids,
                        "asks": asks,
                        "timestamp": datetime.utcnow()
                    }
                    
        except Exception as e:
            # print(f"Error parsing message: {e}")
            pass

    async def _subscribe_binance(self, symbol: str):
        """Send sub request to Binance"""
        ws = self.connections.get("binance")
        if ws:
            payload = {
                "method": "SUBSCRIBE",
                "params": [f"{symbol.lower()}@depth20@100ms"],
                "id": 1
            }
            await ws.send(json.dumps(payload))

    async def _unsubscribe_binance(self, symbol: str):
        """Send unsub request to Binance"""
        ws = self.connections.get("binance")
        if ws:
            payload = {
                "method": "UNSUBSCRIBE",
                "params": [f"{symbol.lower()}@depth20@100ms"],
                "id": 1
            }
            await ws.send(json.dumps(payload))

    async def _subscribe_mexc(self, symbol: str):
        """Send sub request to MEXC"""
        # MEXC format: spot@public.limit.depth.v3.api@<symbol>
        ws = self.connections.get("mexc")
        if ws:
            payload = {
                "method": "SUBSCRIPTION",
                "params": [f"spot@public.limit.depth.v3.api@{symbol.upper()}"],
            }
            await ws.send(json.dumps(payload))

    async def _unsubscribe_mexc(self, symbol: str):
        """Send unsub request to MEXC"""
        ws = self.connections.get("mexc")
        if ws:
            payload = {
                "method": "UNSUBSCRIPTION",
                "params": [f"spot@public.limit.depth.v3.api@{symbol.upper()}"],
            }
            await ws.send(json.dumps(payload))
