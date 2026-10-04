"""
Exchange Executor
The Autonomous Alpha - Order Execution Layer

This module handles order execution on exchanges:
- Order placement (market, limit)
- Position management
- Balance tracking
- Order status monitoring
"""

import asyncio
import time
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from typing import Any
import os

from loguru import logger

try:
    import ccxt
    import ccxt.async_support as ccxt_async
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    logger.warning("ccxt not installed. Exchange execution disabled.")


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    CANCELED = "canceled"
    FAILED = "failed"


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class Order:
    """Order representation"""
    order_id: str
    symbol: str
    side: OrderSide
    type: OrderType
    quantity: float
    price: float | None
    status: OrderStatus
    filled_quantity: float = 0.0
    average_price: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    exchange_order_id: str | None = None
    error: str | None = None


@dataclass
class Position:
    """Position representation"""
    symbol: str
    side: PositionSide
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    leverage: int = 1
    liquidation_price: float | None = None
    margin: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def pnl_percent(self) -> float:
        if self.entry_price == 0:
            return 0.0
        if self.side == PositionSide.LONG:
            return ((self.current_price - self.entry_price) / self.entry_price) * 100 * self.leverage
        else:
            return ((self.entry_price - self.current_price) / self.entry_price) * 100 * self.leverage


@dataclass
class Balance:
    """Account balance"""
    currency: str
    total: float
    available: float
    locked: float = 0.0


class ExchangeExecutor:
    """
    Execute trades on exchanges via CCXT.
    Supports Binance Futures (testnet and mainnet).
    """
    
    def __init__(
        self,
        exchange: str = "binance",
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool = True,
        default_leverage: int = 1,
    ):
        if not CCXT_AVAILABLE:
            raise ImportError("ccxt is required for exchange execution")
            
        self.exchange_name = exchange
        self.testnet = testnet
        self.default_leverage = default_leverage
        
        # Get API keys from env if not provided
        api_key = api_key or os.getenv("BINANCE_API_KEY")
        api_secret = api_secret or os.getenv("BINANCE_API_SECRET")
        
        # Initialize CCXT exchange
        exchange_class = getattr(ccxt_async, exchange)
        
        config = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",  # Use futures by default
            }
        }
        
        if testnet and exchange == "binance":
            config["options"]["testnet"] = True
            config["urls"] = {
                "api": {
                    "public": "https://testnet.binancefuture.com/fapi/v1",
                    "private": "https://testnet.binancefuture.com/fapi/v1",
                }
            }
            
        self._exchange: Any = exchange_class(config)
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, Order] = {}
        self._balances: dict[str, Balance] = {}
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
        
    async def __aexit__(self, *args):
        """Async context manager exit"""
        await self.disconnect()
        
    async def connect(self):
        """Initialize connection and load markets"""
        try:
            await self._exchange.load_markets()
            logger.info(f"Connected to {self.exchange_name} ({'testnet' if self.testnet else 'mainnet'})")
            logger.info(f"Loaded {len(self._exchange.markets)} markets")
        except Exception as e:
            logger.error(f"Failed to connect to exchange: {e}")
            raise
            
    async def disconnect(self):
        """Close exchange connection"""
        await self._exchange.close()
        
    async def get_balance(self, currency: str = "USDT") -> Balance | None:
        """Get account balance for a currency"""
        try:
            balance_data = await self._exchange.fetch_balance()
            
            if currency in balance_data:
                bal = balance_data[currency]
                balance = Balance(
                    currency=currency,
                    total=float(bal.get("total", 0)),
                    available=float(bal.get("free", 0)),
                    locked=float(bal.get("used", 0)),
                )
                self._balances[currency] = balance
                return balance
                
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            
        return None
        
    async def get_positions(self) -> list[Position]:
        """Get all open positions"""
        try:
            positions = await self._exchange.fetch_positions()
            
            result = []
            for pos in positions:
                if float(pos.get("contracts", 0)) > 0:
                    position = Position(
                        symbol=pos["symbol"],
                        side=PositionSide.LONG if pos["side"] == "long" else PositionSide.SHORT,
                        quantity=float(pos["contracts"]),
                        entry_price=float(pos.get("entryPrice", 0)),
                        current_price=float(pos.get("markPrice", 0)),
                        unrealized_pnl=float(pos.get("unrealizedPnl", 0)),
                        leverage=int(pos.get("leverage", 1)),
                        liquidation_price=float(pos.get("liquidationPrice", 0)) if pos.get("liquidationPrice") else None,
                        margin=float(pos.get("initialMargin", 0)),
                    )
                    result.append(position)
                    self._positions[position.symbol] = position
                    
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            return []
            
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol"""
        try:
            await self._exchange.set_leverage(leverage, symbol)
            logger.info(f"Set leverage for {symbol} to {leverage}x")
            return True
        except Exception as e:
            logger.error(f"Failed to set leverage: {e}")
            return False
            
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: float | None = None,
        leverage: int | None = None,
        reduce_only: bool = False,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> Order:
        """
        Place an order on the exchange.
        
        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            side: BUY or SELL
            quantity: Amount to trade
            order_type: MARKET or LIMIT
            price: Limit price (required for limit orders)
            leverage: Position leverage
            reduce_only: Only reduce position, don't open new
            stop_loss: Stop loss price
            take_profit: Take profit price
            
        Returns:
            Order object with status
        """
        order_id = f"TA-{int(time.time() * 1000)}"
        
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            type=order_type,
            quantity=quantity,
            price=price,
            status=OrderStatus.PENDING,
        )
        
        try:
            # Set leverage if specified
            if leverage:
                await self.set_leverage(symbol, leverage)
            elif self.default_leverage > 1:
                await self.set_leverage(symbol, self.default_leverage)
                
            # Build order params
            params = {}
            if reduce_only:
                params["reduceOnly"] = True
                
            # Place main order
            if order_type == OrderType.MARKET:
                result = await self._exchange.create_market_order(
                    symbol=symbol,
                    side=side.value,
                    amount=quantity,
                    params=params,
                )
            elif order_type == OrderType.LIMIT:
                if price is None:
                    raise ValueError("Limit orders require a price")
                result = await self._exchange.create_limit_order(
                    symbol=symbol,
                    side=side.value,
                    amount=quantity,
                    price=price,
                    params=params,
                )
            else:
                raise ValueError(f"Unsupported order type: {order_type}")
                
            # Update order with exchange response
            order.exchange_order_id = result.get("id")
            order.status = OrderStatus(result.get("status", "open"))
            order.filled_quantity = float(result.get("filled", 0))
            order.average_price = float(result.get("average", 0)) if result.get("average") else 0.0
            order.updated_at = datetime.now()
            
            logger.info(
                f"Order placed: {order.order_id} | "
                f"{side.value.upper()} {quantity} {symbol} @ "
                f"{'MARKET' if order_type == OrderType.MARKET else price}"
            )
            
            # Place stop loss if specified
            if stop_loss:
                await self._place_stop_order(
                    symbol=symbol,
                    side=OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY,
                    quantity=quantity,
                    stop_price=stop_loss,
                    order_type="stop_market",
                )
                
            # Place take profit if specified
            if take_profit:
                await self._place_stop_order(
                    symbol=symbol,
                    side=OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY,
                    quantity=quantity,
                    stop_price=take_profit,
                    order_type="take_profit_market",
                )
                
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            order.status = OrderStatus.FAILED
            order.error = str(e)
            
        self._orders[order.order_id] = order
        return order
        
    async def _place_stop_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        stop_price: float,
        order_type: str,
    ):
        """Place stop loss or take profit order"""
        try:
            params = {
                "stopPrice": stop_price,
                "reduceOnly": True,
            }
            
            await self._exchange.create_order(
                symbol=symbol,
                type=order_type,
                side=side.value,
                amount=quantity,
                params=params,
            )
            logger.info(f"{order_type} placed for {symbol} at {stop_price}")
            
        except Exception as e:
            logger.error(f"Failed to place {order_type}: {e}")
            
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an open order"""
        try:
            order = self._orders.get(order_id)
            if order and order.exchange_order_id:
                await self._exchange.cancel_order(order.exchange_order_id, symbol)
                order.status = OrderStatus.CANCELED
                order.updated_at = datetime.now()
                logger.info(f"Canceled order: {order_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
        return False
        
    async def close_position(self, symbol: str) -> Order | None:
        """Close entire position for a symbol"""
        position = self._positions.get(symbol)
        if not position:
            # Refresh positions
            await self.get_positions()
            position = self._positions.get(symbol)
            
        if position and position.quantity > 0:
            side = OrderSide.SELL if position.side == PositionSide.LONG else OrderSide.BUY
            return await self.place_order(
                symbol=symbol,
                side=side,
                quantity=position.quantity,
                order_type=OrderType.MARKET,
                reduce_only=True,
            )
            
        return None
        
    async def get_ticker(self, symbol: str) -> dict | None:
        """Get current ticker for symbol"""
        try:
            ticker = await self._exchange.fetch_ticker(symbol)
            return {
                "symbol": ticker["symbol"],
                "bid": ticker.get("bid"),
                "ask": ticker.get("ask"),
                "last": ticker.get("last"),
                "volume": ticker.get("baseVolume"),
                "change_24h": ticker.get("percentage"),
            }
        except Exception as e:
            logger.error(f"Failed to fetch ticker: {e}")
            return None


class PaperExecutor:
    """
    Paper trading executor for testing without real money.
    Simulates order execution with realistic fills.
    """
    
    def __init__(
        self,
        initial_balance: float = 10000.0,
        default_leverage: int = 1,
        slippage_bps: float = 5.0,
        fee_bps: float = 4.0,
    ):
        self.initial_balance = initial_balance
        self.default_leverage = default_leverage
        self.slippage_bps = slippage_bps
        self.fee_bps = fee_bps
        
        self._balance = initial_balance
        self._positions: dict[str, Position] = {}
        self._orders: list[Order] = []
        self._trade_count = 0
        self._prices: dict[str, float] = {}
        
    async def connect(self):
        """Initialize paper trading (no-op)"""
        logger.info(f"Paper trading initialized with ${self.initial_balance}")
        
    async def disconnect(self):
        """Cleanup (no-op)"""
        pass
        
    def update_price(self, symbol: str, price: float):
        """Update current price for a symbol"""
        self._prices[symbol] = price
        
        # Update position P&L
        if symbol in self._positions:
            pos = self._positions[symbol]
            pos.current_price = price
            if pos.side == PositionSide.LONG:
                pos.unrealized_pnl = (price - pos.entry_price) * pos.quantity
            else:
                pos.unrealized_pnl = (pos.entry_price - price) * pos.quantity
                
    async def get_balance(self, currency: str = "USDT") -> Balance:
        """Get paper trading balance"""
        locked = sum(pos.margin for pos in self._positions.values())
        return Balance(
            currency=currency,
            total=self._balance,
            available=self._balance - locked,
            locked=locked,
        )
        
    async def get_positions(self) -> list[Position]:
        """Get open paper positions"""
        return list(self._positions.values())
        
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: float | None = None,
        leverage: int | None = None,
        **kwargs,
    ) -> Order:
        """Simulate order placement"""
        self._trade_count += 1
        order_id = f"PAPER-{self._trade_count:05d}"
        
        # Get execution price
        current_price = self._prices.get(symbol, price or 0)
        if current_price == 0:
            return Order(
                order_id=order_id,
                symbol=symbol,
                side=side,
                type=order_type,
                quantity=quantity,
                price=price,
                status=OrderStatus.FAILED,
                error="No price available",
            )
            
        # Apply slippage
        slippage = current_price * (self.slippage_bps / 10000)
        if side == OrderSide.BUY:
            fill_price = current_price + slippage
        else:
            fill_price = current_price - slippage
            
        # Calculate fees
        fee = quantity * fill_price * (self.fee_bps / 10000)
        
        # Check balance
        lev = leverage or self.default_leverage
        margin_required = (quantity * fill_price) / lev
        
        if margin_required + fee > self._balance:
            return Order(
                order_id=order_id,
                symbol=symbol,
                side=side,
                type=order_type,
                quantity=quantity,
                price=price,
                status=OrderStatus.FAILED,
                error="Insufficient balance",
            )
            
        # Execute trade
        self._balance -= fee
        
        if symbol in self._positions:
            pos = self._positions[symbol]
            if (side == OrderSide.BUY and pos.side == PositionSide.LONG) or \
               (side == OrderSide.SELL and pos.side == PositionSide.SHORT):
                # Add to position
                total_quantity = pos.quantity + quantity
                pos.entry_price = (pos.entry_price * pos.quantity + fill_price * quantity) / total_quantity
                pos.quantity = total_quantity
                pos.margin += margin_required
            else:
                # Reduce or close position
                if quantity >= pos.quantity:
                    # Close position
                    realized_pnl = pos.unrealized_pnl
                    self._balance += pos.margin + realized_pnl
                    del self._positions[symbol]
                else:
                    # Reduce position
                    pos.quantity -= quantity
                    pos.margin -= margin_required
        else:
            # New position
            self._positions[symbol] = Position(
                symbol=symbol,
                side=PositionSide.LONG if side == OrderSide.BUY else PositionSide.SHORT,
                quantity=quantity,
                entry_price=fill_price,
                current_price=fill_price,
                unrealized_pnl=0.0,
                leverage=lev,
                margin=margin_required,
            )
            self._balance -= margin_required
            
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            type=order_type,
            quantity=quantity,
            price=fill_price,
            status=OrderStatus.FILLED,
            filled_quantity=quantity,
            average_price=fill_price,
        )
        
        self._orders.append(order)
        
        logger.info(
            f"[PAPER] {side.value.upper()} {quantity} {symbol} @ {fill_price:.2f} | "
            f"Fee: ${fee:.2f} | Balance: ${self._balance:.2f}"
        )
        
        return order
        
    async def close_position(self, symbol: str) -> Order | None:
        """Close paper position"""
        if symbol in self._positions:
            pos = self._positions[symbol]
            side = OrderSide.SELL if pos.side == PositionSide.LONG else OrderSide.BUY
            return await self.place_order(
                symbol=symbol,
                side=side,
                quantity=pos.quantity,
            )
        return None
        
    def get_stats(self) -> dict:
        """Get paper trading statistics"""
        total_pnl = sum(pos.unrealized_pnl for pos in self._positions.values())
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self._balance,
            "unrealized_pnl": total_pnl,
            "total_equity": self._balance + total_pnl,
            "total_trades": self._trade_count,
            "open_positions": len(self._positions),
            "return_pct": ((self._balance + total_pnl - self.initial_balance) / self.initial_balance) * 100,
        }


async def main():
    """Test the executor"""
    # Test paper trading
    executor = PaperExecutor(initial_balance=10000.0)
    await executor.connect()
    
    # Simulate price
    executor.update_price("BTC/USDT", 107000.0)
    
    # Place order
    order = await executor.place_order(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        quantity=0.1,
        leverage=10,
    )
    
    print(f"Order: {order}")
    print(f"Stats: {executor.get_stats()}")
    
    # Simulate price change
    executor.update_price("BTC/USDT", 108000.0)
    positions = await executor.get_positions()
    print(f"Positions: {positions}")
    print(f"Stats after price move: {executor.get_stats()}")
    
    # Close position
    await executor.close_position("BTC/USDT")
    print(f"Final stats: {executor.get_stats()}")


if __name__ == "__main__":
    asyncio.run(main())
