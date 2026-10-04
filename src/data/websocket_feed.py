"""
WebSocket Data Feed
The Autonomous Alpha - Real-time Market Data Ingestion

This module provides real-time market data from exchanges:
- Price ticks (trades)
- Order book updates (L2)
- Candlestick/OHLCV data
- Order Flow Imbalance calculation
"""

import asyncio
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Any
from collections import deque

import websockets
from loguru import logger

# Try uvloop/winloop for performance
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    try:
        import winloop
        asyncio.set_event_loop_policy(winloop.EventLoopPolicy())
    except ImportError:
        pass


@dataclass
class Trade:
    """A single trade tick"""
    symbol: str
    price: float
    quantity: float
    side: str  # "buy" or "sell"
    timestamp: datetime
    trade_id: str | None = None


@dataclass
class OrderBookLevel:
    """Single level in order book"""
    price: float
    quantity: float


@dataclass
class OrderBook:
    """L2 Order book snapshot"""
    symbol: str
    bids: list[OrderBookLevel]  # Sorted high to low
    asks: list[OrderBookLevel]  # Sorted low to high
    timestamp: datetime
    
    @property
    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0.0
    
    @property
    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else 0.0
    
    @property
    def mid_price(self) -> float:
        return (self.best_bid + self.best_ask) / 2 if self.bids and self.asks else 0.0
    
    @property
    def spread(self) -> float:
        return self.best_ask - self.best_bid if self.bids and self.asks else 0.0
    
    @property
    def spread_bps(self) -> float:
        """Spread in basis points"""
        return (self.spread / self.mid_price) * 10000 if self.mid_price else 0.0


@dataclass
class Candle:
    """OHLCV candlestick"""
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: datetime
    is_closed: bool = False


@dataclass
class OFI:
    """Order Flow Imbalance snapshot"""
    symbol: str
    value: float
    timestamp: datetime
    lookback_seconds: int


class BinanceWebSocket:
    """
    Binance WebSocket client for real-time market data.
    Supports: trades, order book, klines.
    """
    
    BASE_URL = "wss://stream.binance.com:9443/ws"
    TESTNET_URL = "wss://testnet.binance.vision/ws"
    
    def __init__(
        self,
        symbols: list[str],
        testnet: bool = True,
        on_trade: Callable[[Trade], None] | None = None,
        on_orderbook: Callable[[OrderBook], None] | None = None,
        on_candle: Callable[[Candle], None] | None = None,
    ):
        self.symbols = [s.lower().replace("/", "") for s in symbols]
        self.testnet = testnet
        self.base_url = self.TESTNET_URL if testnet else self.BASE_URL
        
        # Callbacks
        self.on_trade = on_trade
        self.on_orderbook = on_orderbook
        self.on_candle = on_candle
        
        # State
        self._ws: Any = None
        self._running = False
        self._reconnect_delay = 1
        self._max_reconnect_delay = 60
        
        # Order book state
        self._order_books: dict[str, OrderBook] = {}
        
        # OFI calculation state
        self._ofi_history: dict[str, deque] = {}
        self._prev_best_bid: dict[str, tuple[float, float]] = {}
        self._prev_best_ask: dict[str, tuple[float, float]] = {}
        
    def _build_streams(self) -> list[str]:
        """Build list of stream names to subscribe to"""
        streams = []
        for symbol in self.symbols:
            streams.append(f"{symbol}@trade")
            streams.append(f"{symbol}@depth20@100ms")
            streams.append(f"{symbol}@kline_1m")
        return streams
        
    async def connect(self):
        """Connect to WebSocket and start receiving data"""
        streams = self._build_streams()
        stream_path = "/".join(streams)
        url = f"{self.base_url}/{stream_path}"
        
        self._running = True
        logger.info(f"Connecting to Binance WebSocket: {len(streams)} streams")
        
        while self._running:
            try:
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=10,
                ) as ws:
                    self._ws = ws
                    self._reconnect_delay = 1  # Reset on successful connect
                    logger.info("WebSocket connected")
                    
                    async for message in ws:
                        await self._handle_message(message)
                        
            except websockets.ConnectionClosed as e:
                logger.warning(f"WebSocket closed: {e}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                
            if self._running:
                logger.info(f"Reconnecting in {self._reconnect_delay}s...")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2,
                    self._max_reconnect_delay
                )
                
    async def disconnect(self):
        """Disconnect from WebSocket"""
        self._running = False
        if self._ws:
            await self._ws.close()
            
    async def _handle_message(self, raw_message: str):
        """Parse and route incoming messages"""
        try:
            data = json.loads(raw_message)
            
            # Handle combined stream format
            if "stream" in data:
                stream = data["stream"]
                payload = data["data"]
            else:
                stream = data.get("e", "")
                payload = data
                
            # Route by stream type
            if "@trade" in stream or payload.get("e") == "trade":
                await self._handle_trade(payload)
            elif "@depth" in stream or payload.get("e") == "depthUpdate":
                await self._handle_depth(payload)
            elif "@kline" in stream or payload.get("e") == "kline":
                await self._handle_kline(payload)
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            
    async def _handle_trade(self, data: dict):
        """Handle trade tick"""
        trade = Trade(
            symbol=data["s"].upper(),
            price=float(data["p"]),
            quantity=float(data["q"]),
            side="buy" if data.get("m", False) is False else "sell",
            timestamp=datetime.fromtimestamp(data["T"] / 1000),
            trade_id=str(data.get("t")),
        )
        
        if self.on_trade:
            self.on_trade(trade)
            
    async def _handle_depth(self, data: dict):
        """Handle order book depth update"""
        symbol = data.get("s", "").upper()
        if not symbol:
            return
            
        bids = [
            OrderBookLevel(price=float(b[0]), quantity=float(b[1]))
            for b in data.get("bids", data.get("b", []))
        ]
        asks = [
            OrderBookLevel(price=float(a[0]), quantity=float(a[1]))
            for a in data.get("asks", data.get("a", []))
        ]
        
        order_book = OrderBook(
            symbol=symbol,
            bids=sorted(bids, key=lambda x: x.price, reverse=True),
            asks=sorted(asks, key=lambda x: x.price),
            timestamp=datetime.now(),
        )
        
        # Update OFI
        self._update_ofi(symbol, order_book)
        
        # Store and callback
        self._order_books[symbol] = order_book
        
        if self.on_orderbook:
            self.on_orderbook(order_book)
            
    async def _handle_kline(self, data: dict):
        """Handle kline/candlestick update"""
        k = data.get("k", data)
        
        candle = Candle(
            symbol=k["s"].upper(),
            timeframe=k["i"],
            open=float(k["o"]),
            high=float(k["h"]),
            low=float(k["l"]),
            close=float(k["c"]),
            volume=float(k["v"]),
            timestamp=datetime.fromtimestamp(k["t"] / 1000),
            is_closed=k.get("x", False),
        )
        
        if self.on_candle:
            self.on_candle(candle)
            
    def _update_ofi(self, symbol: str, book: OrderBook):
        """
        Calculate Order Flow Imbalance.
        
        OFI = Σ(bid_volume_change) - Σ(ask_volume_change)
        Positive OFI = buying pressure
        Negative OFI = selling pressure
        """
        if symbol not in self._ofi_history:
            self._ofi_history[symbol] = deque(maxlen=1000)
            
        ofi_delta = 0.0
        
        prev_bid = self._prev_best_bid.get(symbol)
        prev_ask = self._prev_best_ask.get(symbol)
        
        if book.bids and book.asks:
            curr_bid = (book.best_bid, book.bids[0].quantity)
            curr_ask = (book.best_ask, book.asks[0].quantity)
            
            if prev_bid:
                if curr_bid[0] > prev_bid[0]:
                    ofi_delta += curr_bid[1]
                elif curr_bid[0] < prev_bid[0]:
                    ofi_delta -= prev_bid[1]
                else:
                    ofi_delta += (curr_bid[1] - prev_bid[1])
                    
            if prev_ask:
                if curr_ask[0] < prev_ask[0]:
                    ofi_delta -= curr_ask[1]
                elif curr_ask[0] > prev_ask[0]:
                    ofi_delta += prev_ask[1]
                else:
                    ofi_delta -= (curr_ask[1] - prev_ask[1])
                    
            self._prev_best_bid[symbol] = curr_bid
            self._prev_best_ask[symbol] = curr_ask
            
            self._ofi_history[symbol].append(
                (datetime.now(), ofi_delta)
            )
            
    def get_ofi(self, symbol: str, lookback_seconds: int = 60) -> OFI:
        """Get cumulative OFI over lookback period"""
        history = self._ofi_history.get(symbol, deque())
        cutoff = datetime.now().timestamp() - lookback_seconds
        
        total_ofi = sum(
            delta for ts, delta in history
            if ts.timestamp() > cutoff
        )
        
        return OFI(
            symbol=symbol,
            value=total_ofi,
            timestamp=datetime.now(),
            lookback_seconds=lookback_seconds,
        )
        
    def get_order_book(self, symbol: str) -> OrderBook | None:
        """Get current order book for symbol"""
        return self._order_books.get(symbol.upper())


class MarketDataAggregator:
    """
    Aggregates market data from multiple sources.
    Provides unified interface for the trading system.
    """
    
    def __init__(self):
        self._websockets: list[BinanceWebSocket] = []
        self._latest_prices: dict[str, float] = {}
        self._latest_candles: dict[str, Candle] = {}
        self._trade_callbacks: list[Callable[[Trade], None]] = []
        self._orderbook_callbacks: list[Callable[[OrderBook], None]] = []
        
    def add_exchange(
        self,
        exchange: str,
        symbols: list[str],
        testnet: bool = True,
    ):
        """Add an exchange connection"""
        if exchange.lower() == "binance":
            ws = BinanceWebSocket(
                symbols=symbols,
                testnet=testnet,
                on_trade=self._on_trade,
                on_orderbook=self._on_orderbook,
                on_candle=self._on_candle,
            )
            self._websockets.append(ws)
        else:
            raise ValueError(f"Unsupported exchange: {exchange}")
            
    def on_trade(self, callback: Callable[[Trade], None]):
        """Register trade callback"""
        self._trade_callbacks.append(callback)
        
    def on_orderbook(self, callback: Callable[[OrderBook], None]):
        """Register orderbook callback"""
        self._orderbook_callbacks.append(callback)
        
    def _on_trade(self, trade: Trade):
        """Internal trade handler"""
        self._latest_prices[trade.symbol] = trade.price
        for cb in self._trade_callbacks:
            try:
                cb(trade)
            except Exception as e:
                logger.error(f"Trade callback error: {e}")
                
    def _on_orderbook(self, book: OrderBook):
        """Internal orderbook handler"""
        for cb in self._orderbook_callbacks:
            try:
                cb(book)
            except Exception as e:
                logger.error(f"Orderbook callback error: {e}")
                
    def _on_candle(self, candle: Candle):
        """Internal candle handler"""
        key = f"{candle.symbol}_{candle.timeframe}"
        self._latest_candles[key] = candle
        
    async def start(self):
        """Start all exchange connections"""
        tasks = [ws.connect() for ws in self._websockets]
        await asyncio.gather(*tasks)
        
    async def stop(self):
        """Stop all exchange connections"""
        for ws in self._websockets:
            await ws.disconnect()
            
    def get_price(self, symbol: str) -> float | None:
        """Get latest price for symbol"""
        return self._latest_prices.get(symbol.upper())
        
    def get_ofi(self, symbol: str, lookback_seconds: int = 60) -> OFI | None:
        """Get OFI from first available source"""
        for ws in self._websockets:
            ofi = ws.get_ofi(symbol, lookback_seconds)
            if ofi:
                return ofi
        return None


async def main():
    """Test the WebSocket feed"""
    logger.info("Starting market data feed test...")
    
    def on_trade(trade: Trade):
        logger.info(f"Trade: {trade.symbol} {trade.side} {trade.quantity} @ {trade.price}")
        
    def on_orderbook(book: OrderBook):
        logger.debug(
            f"Book: {book.symbol} | "
            f"Bid: {book.best_bid:.2f} | "
            f"Ask: {book.best_ask:.2f} | "
            f"Spread: {book.spread_bps:.1f}bps"
        )
        
    aggregator = MarketDataAggregator()
    aggregator.add_exchange(
        exchange="binance",
        symbols=["BTCUSDT", "ETHUSDT"],
        testnet=True,
    )
    aggregator.on_trade(on_trade)
    aggregator.on_orderbook(on_orderbook)
    
    try:
        await aggregator.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await aggregator.stop()


if __name__ == "__main__":
    asyncio.run(main())
