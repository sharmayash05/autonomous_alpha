"""
Portfolio State Manager
The Autonomous Alpha - Unified Portfolio Tracking

Manages portfolio state across the trading system:
- Position tracking
- P&L calculation
- Trade history
- Performance metrics
"""

import asyncio
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path
from enum import Enum

from loguru import logger


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class Position:
    """Open position"""
    symbol: str
    side: PositionSide
    quantity: float
    entry_price: float
    entry_time: datetime
    leverage: int = 1
    stop_loss: float | None = None
    take_profit: float | None = None
    current_price: float | None = None
    market_context_entry: dict | None = None  # Market snapshot at entry for reflexion
    
    @property
    def notional_value(self) -> float:
        price = self.current_price or self.entry_price
        return abs(self.quantity) * price
    
    @property
    def margin(self) -> float:
        return self.notional_value / self.leverage
    
    @property
    def unrealized_pnl(self) -> float:
        if not self.current_price:
            return 0.0
        if self.side == PositionSide.LONG:
            return (self.current_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - self.current_price) * self.quantity
    
    @property
    def unrealized_pnl_percent(self) -> float:
        if self.entry_price == 0:
            return 0.0
        base_pnl = self.unrealized_pnl / (self.entry_price * abs(self.quantity))
        return base_pnl * 100 * self.leverage


@dataclass
class ClosedTrade:
    """Completed trade record"""
    trade_id: str
    symbol: str
    side: PositionSide
    quantity: float
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    leverage: int = 1
    pnl_usd: float = 0.0
    pnl_percent: float = 0.0
    fees: float = 0.0
    exit_reason: str = ""
    market_context_entry: dict | None = None  # Market snapshot at entry
    market_context_exit: dict | None = None   # Market snapshot at exit
    snapshot_timestamp: str | None = None     # Timestamp for market memory update_outcome


@dataclass
class PortfolioState:
    """Complete portfolio state"""
    # Balances
    initial_balance: float
    cash_balance: float
    
    # Positions
    positions: dict[str, Position] = field(default_factory=dict)
    
    # History
    closed_trades: list[ClosedTrade] = field(default_factory=list)
    equity_history: list[tuple[datetime, float]] = field(default_factory=list)
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    
    @property
    def total_equity(self) -> float:
        """Total portfolio value"""
        unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        margin_used = sum(p.margin for p in self.positions.values())
        return self.cash_balance + margin_used + unrealized
    
    @property
    def total_pnl_usd(self) -> float:
        """Total P&L in USD"""
        return self.total_equity - self.initial_balance
    
    @property
    def total_pnl_percent(self) -> float:
        """Total P&L as percentage"""
        if self.initial_balance == 0:
            return 0.0
        return (self.total_pnl_usd / self.initial_balance) * 100
    
    @property
    def unrealized_pnl(self) -> float:
        """Total unrealized P&L"""
        return sum(p.unrealized_pnl for p in self.positions.values())
    
    @property
    def realized_pnl(self) -> float:
        """Total realized P&L"""
        return sum(t.pnl_usd for t in self.closed_trades)
    
    @property
    def margin_used(self) -> float:
        """Total margin used"""
        return sum(p.margin for p in self.positions.values())
    
    @property
    def free_margin(self) -> float:
        """Available margin"""
        return self.cash_balance
    
    @property
    def exposure_percent(self) -> float:
        """Portfolio exposure as percentage"""
        if self.total_equity == 0:
            return 0.0
        notional = sum(p.notional_value for p in self.positions.values())
        return (notional / self.total_equity) * 100


class PortfolioManager:
    """
    Manages portfolio state and provides trading operations.
    """
    
    def __init__(
        self,
        initial_balance: float = 10000.0,
        persist_path: Path | None = None,
    ):
        self.state = PortfolioState(
            initial_balance=initial_balance,
            cash_balance=initial_balance,
        )
        self.persist_path = persist_path
        self._trade_counter = 0
        
        # Performance tracking
        self._high_water_mark = initial_balance
        self._max_drawdown = 0.0
        self._consecutive_losses = 0
        self._daily_pnl = 0.0
        self._last_trading_day = datetime.now().date()
        
        # Callback for self-evolving system (called when trade closes)
        self.on_trade_closed = None  # Set to function(closed_trade, market_context)
        
    def update_price(self, symbol: str, price: float):
        """Update current price for a symbol"""
        if symbol in self.state.positions:
            self.state.positions[symbol].current_price = price
            self._update_metrics()
            
    def _update_metrics(self):
        """Update performance metrics"""
        equity = self.state.total_equity
        
        # Update high water mark and drawdown
        if equity > self._high_water_mark:
            self._high_water_mark = equity
            
        current_drawdown = (self._high_water_mark - equity) / self._high_water_mark * 100
        self._max_drawdown = max(self._max_drawdown, current_drawdown)
        
        # Track daily P&L
        today = datetime.now().date()
        if today != self._last_trading_day:
            self._daily_pnl = 0.0
            self._last_trading_day = today
            
        # Record equity history (hourly)
        if not self.state.equity_history or \
           (datetime.now() - self.state.equity_history[-1][0]).seconds > 3600:
            self.state.equity_history.append((datetime.now(), equity))
            
        self.state.last_updated = datetime.now()
        
    def open_position(
        self,
        symbol: str,
        side: PositionSide,
        quantity: float,
        price: float,
        leverage: int = 1,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        market_context_entry: dict | None = None,
    ) -> Position | None:
        """Open a new position"""
        # Check if position already exists
        if symbol in self.state.positions:
            logger.warning(f"Position already exists for {symbol}")
            return None
            
        # Calculate margin required
        notional = quantity * price
        margin_required = notional / leverage
        
        # Check balance
        if margin_required > self.state.cash_balance:
            logger.error(f"Insufficient balance: need ${margin_required:.2f}, have ${self.state.cash_balance:.2f}")
            return None
            
        # Create position
        position = Position(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=price,
            entry_time=datetime.now(),
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            current_price=price,
            market_context_entry=market_context_entry,
        )
        
        # Update state
        self.state.positions[symbol] = position
        self.state.cash_balance -= margin_required
        
        logger.info(
            f"Opened {side.value.upper()} {quantity} {symbol} @ {price} "
            f"(Leverage: {leverage}x, Margin: ${margin_required:.2f})"
        )
        
        return position
        
    def close_position(
        self,
        symbol: str,
        price: float,
        exit_reason: str = "manual",
        fees_percent: float = 0.04,
        market_context_exit: dict | None = None,
        snapshot_timestamp: str | None = None,
        close_percent: float = 100.0,  # NEW: Partial close support (default: full close)
    ) -> ClosedTrade | None:
        """
        Close an existing position (fully or partially).
        
        Args:
            close_percent: Percentage of position to close (1-100). 
                          Default 100 = full close.
                          Use 50 to close half and let the rest run.
        """
        if symbol not in self.state.positions:
            logger.warning(f"No position found for {symbol}")
            return None
        
        # Validate close_percent
        close_percent = max(1.0, min(100.0, close_percent))
        is_partial = close_percent < 100.0
            
        position = self.state.positions[symbol]
        position.current_price = price
        
        # Calculate quantities for partial close
        close_quantity = position.quantity * (close_percent / 100.0)
        close_margin = position.margin * (close_percent / 100.0)
        
        # Calculate P&L for the closed portion
        if position.side == PositionSide.LONG:
            pnl_usd = (price - position.entry_price) * close_quantity
        else:
            pnl_usd = (position.entry_price - price) * close_quantity
            
        notional = abs(close_quantity) * price
        fees = notional * (fees_percent / 100)
        pnl_usd_after_fees = pnl_usd - fees
        pnl_percent = (pnl_usd_after_fees / close_margin) * 100 if close_margin > 0 else 0
        
        # Create closed trade record
        self._trade_counter += 1
        closed_trade = ClosedTrade(
            trade_id=f"T-{self._trade_counter:05d}",
            symbol=symbol,
            side=position.side,
            quantity=close_quantity,  # Record closed quantity, not full
            entry_price=position.entry_price,
            exit_price=price,
            entry_time=position.entry_time,
            exit_time=datetime.now(),
            leverage=position.leverage,
            pnl_usd=pnl_usd_after_fees,
            pnl_percent=pnl_percent,
            fees=fees,
            exit_reason=exit_reason + (f" (partial {close_percent:.0f}%)" if is_partial else ""),
            market_context_entry=position.market_context_entry,
            market_context_exit=market_context_exit,
            snapshot_timestamp=snapshot_timestamp,
        )
        
        # Update state
        self.state.cash_balance += close_margin + pnl_usd_after_fees
        self.state.closed_trades.append(closed_trade)
        
        if is_partial:
            # Partial close: reduce position, keep rest open
            position.quantity -= close_quantity
            logger.info(f"📊 PARTIAL CLOSE: Closed {close_percent:.0f}% of {symbol}, {100-close_percent:.0f}% remains")
        else:
            # Full close: remove position entirely
            del self.state.positions[symbol]
        
        # Update metrics
        self._daily_pnl += pnl_usd_after_fees
        if pnl_usd_after_fees < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
            
        self._update_metrics()
        
        emoji = "✅" if pnl_usd_after_fees > 0 else "❌"
        close_type = f"PARTIAL ({close_percent:.0f}%)" if is_partial else "FULL"
        logger.info(
            f"{emoji} Closed {symbol} [{close_type}]: {pnl_percent:+.2f}% (${pnl_usd_after_fees:+.2f}) "
            f"[{exit_reason}]"
        )
        
        # Trigger self-evolving callback if registered
        if self.on_trade_closed:
            try:
                self.on_trade_closed(closed_trade)
            except Exception as e:
                logger.warning(f"Trade closed callback failed: {e}")
        
        return closed_trade
        
    def get_stats(self) -> dict:
        """Get portfolio statistics"""
        trades = self.state.closed_trades
        winning_trades = [t for t in trades if t.pnl_usd > 0]
        losing_trades = [t for t in trades if t.pnl_usd < 0]
        
        total_wins = sum(t.pnl_usd for t in winning_trades)
        total_losses = abs(sum(t.pnl_usd for t in losing_trades))
        
        return {
            # Portfolio
            "initial_balance": self.state.initial_balance,
            "total_equity": self.state.total_equity,
            "cash_balance": self.state.cash_balance,
            "margin_used": self.state.margin_used,
            "exposure_percent": self.state.exposure_percent,
            
            # P&L
            "total_pnl_usd": self.state.total_pnl_usd,
            "total_pnl_percent": self.state.total_pnl_percent,
            "realized_pnl": self.state.realized_pnl,
            "unrealized_pnl": self.state.unrealized_pnl,
            "daily_pnl": self._daily_pnl,
            
            # Drawdown
            "high_water_mark": self._high_water_mark,
            "max_drawdown_percent": self._max_drawdown,
            "current_drawdown_percent": (self._high_water_mark - self.state.total_equity) / self._high_water_mark * 100,
            
            # Trade stats
            "total_trades": len(trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": len(winning_trades) / len(trades) * 100 if trades else 0,
            "profit_factor": total_wins / total_losses if total_losses > 0 else float('inf'),
            "avg_win": total_wins / len(winning_trades) if winning_trades else 0,
            "avg_loss": total_losses / len(losing_trades) if losing_trades else 0,
            "consecutive_losses": self._consecutive_losses,
            
            # Positions
            "open_positions": len(self.state.positions),
        }
        
    def check_risk_limits(self, config: dict) -> list[str]:
        """Check if any risk limits are breached"""
        violations = []
        stats = self.get_stats()
        
        # Check drawdown
        if stats["max_drawdown_percent"] > config.get("max_drawdown_pct", 10):
            violations.append(f"Max drawdown exceeded: {stats['max_drawdown_percent']:.1f}%")
            
        # Check consecutive losses
        if stats["consecutive_losses"] >= config.get("consecutive_losses_limit", 3):
            violations.append(f"Consecutive losses: {stats['consecutive_losses']}")
            
        # Check daily loss
        if stats["daily_pnl"] < -self.state.initial_balance * config.get("daily_loss_limit_pct", 3) / 100:
            violations.append(f"Daily loss limit: ${stats['daily_pnl']:.2f}")
            
        # Check exposure
        if stats["exposure_percent"] > config.get("max_exposure_pct", 50):
            violations.append(f"Exposure too high: {stats['exposure_percent']:.1f}%")
            
        return violations
        
    def save(self, path: Path | None = None):
        """Save portfolio state to file"""
        path = path or self.persist_path
        if not path:
            return
            
        data = {
            "initial_balance": self.state.initial_balance,
            "cash_balance": self.state.cash_balance,
            "positions": {
                k: {
                    "symbol": v.symbol,
                    "side": v.side.value,
                    "quantity": v.quantity,
                    "entry_price": v.entry_price,
                    "entry_time": v.entry_time.isoformat(),
                    "leverage": v.leverage,
                    "stop_loss": v.stop_loss,
                    "take_profit": v.take_profit,
                    "market_context_entry": v.market_context_entry,
                }
                for k, v in self.state.positions.items()
            },
            "closed_trades": [
                {
                    "trade_id": t.trade_id,
                    "symbol": t.symbol,
                    "side": t.side.value,
                    "quantity": t.quantity,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "pnl_usd": t.pnl_usd,
                    "pnl_percent": t.pnl_percent,
                    "exit_reason": t.exit_reason,
                    "leverage": t.leverage,
                    "market_context_entry": t.market_context_entry,
                    "market_context_exit": t.market_context_exit,
                    "snapshot_timestamp": t.snapshot_timestamp,
                }
                for t in self.state.closed_trades
            ],
            "metrics": {
                "high_water_mark": self._high_water_mark,
                "max_drawdown": self._max_drawdown,
                "consecutive_losses": self._consecutive_losses,
            },
            "saved_at": datetime.now().isoformat(),
        }
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
            
        logger.info(f"Portfolio saved to {path}")
        
    @classmethod
    def load(cls, path: Path) -> "PortfolioManager":
        """Load portfolio state from file"""
        with open(path) as f:
            data = json.load(f)
            
        manager = cls(initial_balance=data["initial_balance"], persist_path=path)
        manager.state.cash_balance = data["cash_balance"]
        
        # Restore positions
        for k, v in data.get("positions", {}).items():
            manager.state.positions[k] = Position(
                symbol=v["symbol"],
                side=PositionSide(v["side"]),
                quantity=v["quantity"],
                entry_price=v["entry_price"],
                entry_time=datetime.fromisoformat(v["entry_time"]),
                leverage=v.get("leverage", 1),
                stop_loss=v.get("stop_loss"),
                take_profit=v.get("take_profit"),
                market_context_entry=v.get("market_context_entry"),
            )
            
        # Restore closed trades
        for t in data.get("closed_trades", []):
            manager.state.closed_trades.append(ClosedTrade(
                trade_id=t["trade_id"],
                symbol=t["symbol"],
                side=PositionSide(t["side"]),
                quantity=t["quantity"],
                entry_price=t["entry_price"],
                exit_price=t["exit_price"],
                entry_time=datetime.fromisoformat(t["entry_time"]),
                exit_time=datetime.fromisoformat(t["exit_time"]),
                pnl_usd=t["pnl_usd"],
                pnl_percent=t["pnl_percent"],
                exit_reason=t.get("exit_reason", ""),
                leverage=t.get("leverage", 1),
                market_context_entry=t.get("market_context_entry"),
                market_context_exit=t.get("market_context_exit"),
                snapshot_timestamp=t.get("snapshot_timestamp"),
            ))
            
        # Restore metrics
        metrics = data.get("metrics", {})
        manager._high_water_mark = metrics.get("high_water_mark", manager.state.initial_balance)
        manager._max_drawdown = metrics.get("max_drawdown", 0)
        manager._consecutive_losses = metrics.get("consecutive_losses", 0)
        manager._trade_counter = len(manager.state.closed_trades)
        
        logger.info(f"Portfolio loaded from {path}")
        return manager


if __name__ == "__main__":
    # Test portfolio manager
    pm = PortfolioManager(initial_balance=10000.0)
    
    # Open a position
    pm.open_position(
        symbol="BTC/USDT",
        side=PositionSide.LONG,
        quantity=0.1,
        price=50000.0,
        leverage=10,
        stop_loss=48000.0,
        take_profit=55000.0,
    )
    
    # Update price
    pm.update_price("BTC/USDT", 52000.0)
    
    print("\n" + "="*60)
    print("PORTFOLIO STATE")
    print("="*60)
    
    stats = pm.get_stats()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")
            
    # Close position
    pm.close_position("BTC/USDT", 52000.0, "take_profit")
    
    print("\n" + "="*60)
    print("AFTER CLOSING")
    print("="*60)
    
    stats = pm.get_stats()
    print(f"  Total P&L: ${stats['total_pnl_usd']:.2f} ({stats['total_pnl_percent']:.2f}%)")
    print(f"  Win Rate: {stats['win_rate']:.1f}%")
