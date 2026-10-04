"""
Backtesting Engine
The Autonomous Alpha - Historical Strategy Validation

Simulates trading on historical data:
- OHLCV data loading
- Strategy execution
- Performance metrics
- Trade visualization
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Callable, Any
from pathlib import Path

from loguru import logger

from .portfolio import PortfolioManager, PositionSide, ClosedTrade


@dataclass
class BacktestConfig:
    """Backtest configuration"""
    initial_balance: float = 10000.0
    leverage: int = 1
    commission_pct: float = 0.04  # 0.04% per trade
    slippage_pct: float = 0.02   # 0.02% slippage
    
    # Risk params
    max_position_pct: float = 10.0
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 5.0
    
    # Backtest params
    warmup_periods: int = 50
    verbose: bool = True


@dataclass
class BacktestResult:
    """Backtest result summary"""
    # Core metrics
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: float
    
    # Trade stats
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win_pct: float
    avg_loss_pct: float
    avg_trade_duration: timedelta
    
    # Portfolio
    final_equity: float
    peak_equity: float
    
    # Time series
    equity_curve: pd.Series = field(default=None)
    trade_log: list[ClosedTrade] = field(default_factory=list)
    
    def __str__(self) -> str:
        return f"""
╔══════════════════════════════════════════════════════════════╗
║                    BACKTEST RESULTS                          ║
╠══════════════════════════════════════════════════════════════╣
║  Total Return:    {self.total_return_pct:>8.2f}%                              ║
║  Sharpe Ratio:    {self.sharpe_ratio:>8.2f}                                ║
║  Max Drawdown:    {self.max_drawdown_pct:>8.2f}%                              ║
║  Win Rate:        {self.win_rate:>8.2f}%                              ║
║  Profit Factor:   {self.profit_factor:>8.2f}                                ║
╠══════════════════════════════════════════════════════════════╣
║  Total Trades:    {self.total_trades:>8d}                                ║
║  Winners:         {self.winning_trades:>8d}                                ║
║  Losers:          {self.losing_trades:>8d}                                ║
║  Avg Win:         {self.avg_win_pct:>8.2f}%                              ║
║  Avg Loss:        {self.avg_loss_pct:>8.2f}%                              ║
╠══════════════════════════════════════════════════════════════╣
║  Final Equity:    ${self.final_equity:>10.2f}                          ║
║  Peak Equity:     ${self.peak_equity:>10.2f}                          ║
╚══════════════════════════════════════════════════════════════╝
"""


class BacktestEngine:
    """
    Backtesting engine for strategy validation.
    """
    
    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()
        self.portfolio: PortfolioManager | None = None
        self.equity_curve: list[tuple[datetime, float]] = []
        
    def load_data(
        self,
        data: pd.DataFrame,
        symbol: str = "BTC/USDT",
    ) -> pd.DataFrame:
        """
        Prepare OHLCV data for backtesting.
        
        Expected columns: timestamp/date, open, high, low, close, volume
        """
        df = data.copy()
        
        # Ensure we have required columns
        required = ['open', 'high', 'low', 'close', 'volume']
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
                
        # Ensure index is datetime
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
        elif 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
        df['symbol'] = symbol
        
        return df.sort_index()
        
    def run(
        self,
        data: pd.DataFrame,
        strategy: Callable[[pd.DataFrame, int, "BacktestEngine"], dict | None],
        symbol: str = "BTC/USDT",
    ) -> BacktestResult:
        """
        Run backtest with a strategy function.
        
        The strategy function receives:
        - data: Full DataFrame
        - idx: Current bar index
        - engine: BacktestEngine instance
        
        And returns a signal dict:
        {"action": "LONG"|"SHORT"|"CLOSE"|None, "size_pct": float}
        """
        df = self.load_data(data, symbol)
        
        # Initialize portfolio
        self.portfolio = PortfolioManager(
            initial_balance=self.config.initial_balance
        )
        self.equity_curve = []
        
        logger.info(f"Starting backtest: {len(df)} bars, {symbol}")
        
        # Main backtest loop
        for idx in range(self.config.warmup_periods, len(df)):
            current_bar = df.iloc[idx]
            current_time = df.index[idx]
            current_price = current_bar['close']
            
            # Update position prices
            self.portfolio.update_price(symbol, current_price)
            
            # Check stop loss / take profit
            self._check_exits(symbol, current_bar)
            
            # Get strategy signal
            try:
                signal = strategy(df, idx, self)
            except Exception as e:
                logger.error(f"Strategy error at bar {idx}: {e}")
                signal = None
                
            if signal:
                self._process_signal(signal, symbol, current_bar, current_time)
                
            # Record equity
            equity = self.portfolio.state.total_equity
            self.equity_curve.append((current_time, equity))
            
        # Close any remaining positions
        for sym in list(self.portfolio.state.positions.keys()):
            self.portfolio.close_position(
                sym,
                df.iloc[-1]['close'],
                exit_reason="backtest_end"
            )
            
        # Calculate results
        return self._calculate_results()
        
    def _check_exits(self, symbol: str, bar: pd.Series):
        """Check and execute stop loss / take profit"""
        if symbol not in self.portfolio.state.positions:
            return
            
        pos = self.portfolio.state.positions[symbol]
        high = bar['high']
        low = bar['low']
        
        # Stop loss
        if pos.stop_loss:
            if pos.side == PositionSide.LONG and low <= pos.stop_loss:
                self.portfolio.close_position(
                    symbol, pos.stop_loss, "stop_loss"
                )
                return
            elif pos.side == PositionSide.SHORT and high >= pos.stop_loss:
                self.portfolio.close_position(
                    symbol, pos.stop_loss, "stop_loss"
                )
                return
                
        # Take profit
        if pos.take_profit:
            if pos.side == PositionSide.LONG and high >= pos.take_profit:
                self.portfolio.close_position(
                    symbol, pos.take_profit, "take_profit"
                )
                return
            elif pos.side == PositionSide.SHORT and low <= pos.take_profit:
                self.portfolio.close_position(
                    symbol, pos.take_profit, "take_profit"
                )
                return
                
    def _process_signal(
        self,
        signal: dict,
        symbol: str,
        bar: pd.Series,
        timestamp: datetime,
    ):
        """Process trading signal"""
        action = signal.get("action")
        size_pct = signal.get("size_pct", self.config.max_position_pct)
        
        close = bar['close']
        
        # Apply slippage
        slippage = close * (self.config.slippage_pct / 100)
        
        if action == "CLOSE":
            if symbol in self.portfolio.state.positions:
                self.portfolio.close_position(
                    symbol, close, "signal", self.config.commission_pct
                )
                
        elif action == "LONG":
            if symbol in self.portfolio.state.positions:
                self.portfolio.close_position(
                    symbol, close, "reverse", self.config.commission_pct
                )
                
            entry_price = close + slippage
            equity = self.portfolio.state.total_equity
            position_value = equity * (size_pct / 100)
            quantity = position_value / entry_price * self.config.leverage
            
            stop_loss = entry_price * (1 - self.config.stop_loss_pct / 100)
            take_profit = entry_price * (1 + self.config.take_profit_pct / 100)
            
            self.portfolio.open_position(
                symbol=symbol,
                side=PositionSide.LONG,
                quantity=quantity,
                price=entry_price,
                leverage=self.config.leverage,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
            
        elif action == "SHORT":
            if symbol in self.portfolio.state.positions:
                self.portfolio.close_position(
                    symbol, close, "reverse", self.config.commission_pct
                )
                
            entry_price = close - slippage
            equity = self.portfolio.state.total_equity
            position_value = equity * (size_pct / 100)
            quantity = position_value / entry_price * self.config.leverage
            
            stop_loss = entry_price * (1 + self.config.stop_loss_pct / 100)
            take_profit = entry_price * (1 - self.config.take_profit_pct / 100)
            
            self.portfolio.open_position(
                symbol=symbol,
                side=PositionSide.SHORT,
                quantity=quantity,
                price=entry_price,
                leverage=self.config.leverage,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
            
    def _calculate_results(self) -> BacktestResult:
        """Calculate backtest results"""
        stats = self.portfolio.get_stats()
        trades = self.portfolio.state.closed_trades
        
        # Build equity curve
        equity_df = pd.DataFrame(
            self.equity_curve,
            columns=['timestamp', 'equity']
        ).set_index('timestamp')
        
        # Calculate returns
        returns = equity_df['equity'].pct_change().dropna()
        
        # Sharpe ratio (annualized, assuming hourly data)
        if len(returns) > 0 and returns.std() > 0:
            sharpe = np.sqrt(252 * 24) * returns.mean() / returns.std()
        else:
            sharpe = 0.0
            
        # Trade stats
        winning = [t for t in trades if t.pnl_usd > 0]
        losing = [t for t in trades if t.pnl_usd < 0]
        
        avg_win = np.mean([t.pnl_percent for t in winning]) if winning else 0
        avg_loss = np.mean([abs(t.pnl_percent) for t in losing]) if losing else 0
        
        # Average trade duration
        if trades:
            durations = [(t.exit_time - t.entry_time) for t in trades]
            avg_duration = sum(durations, timedelta()) / len(durations)
        else:
            avg_duration = timedelta()
            
        return BacktestResult(
            total_return_pct=stats['total_pnl_percent'],
            sharpe_ratio=sharpe,
            max_drawdown_pct=stats['max_drawdown_percent'],
            win_rate=stats['win_rate'],
            profit_factor=stats['profit_factor'],
            total_trades=len(trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            avg_win_pct=avg_win,
            avg_loss_pct=avg_loss,
            avg_trade_duration=avg_duration,
            final_equity=stats['total_equity'],
            peak_equity=stats['high_water_mark'],
            equity_curve=equity_df['equity'],
            trade_log=trades,
        )


# ============================================================================
# Example Strategies
# ============================================================================

def sma_crossover_strategy(
    data: pd.DataFrame,
    idx: int,
    engine: BacktestEngine,
    fast_period: int = 10,
    slow_period: int = 30,
) -> dict | None:
    """Simple SMA crossover strategy"""
    if idx < slow_period:
        return None
        
    close = data['close'].iloc[:idx+1]
    
    fast_sma = close.rolling(fast_period).mean().iloc[-1]
    slow_sma = close.rolling(slow_period).mean().iloc[-1]
    
    prev_fast = close.rolling(fast_period).mean().iloc[-2]
    prev_slow = close.rolling(slow_period).mean().iloc[-2]
    
    # Golden cross
    if prev_fast <= prev_slow and fast_sma > slow_sma:
        return {"action": "LONG", "size_pct": 5}
        
    # Death cross
    if prev_fast >= prev_slow and fast_sma < slow_sma:
        return {"action": "SHORT", "size_pct": 5}
        
    return None


def rsi_strategy(
    data: pd.DataFrame,
    idx: int,
    engine: BacktestEngine,
    period: int = 14,
    oversold: float = 30,
    overbought: float = 70,
) -> dict | None:
    """RSI mean reversion strategy"""
    if idx < period + 1:
        return None
        
    close = data['close'].iloc[:idx+1]
    
    # Calculate RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    current_rsi = rsi.iloc[-1]
    prev_rsi = rsi.iloc[-2]
    
    # Oversold -> Long
    if prev_rsi <= oversold and current_rsi > oversold:
        return {"action": "LONG", "size_pct": 5}
        
    # Overbought -> Short
    if prev_rsi >= overbought and current_rsi < overbought:
        return {"action": "SHORT", "size_pct": 5}
        
    return None


if __name__ == "__main__":
    # Generate sample data for testing
    np.random.seed(42)
    
    dates = pd.date_range(start='2024-01-01', periods=1000, freq='1h')
    
    # Random walk with trend
    returns = np.random.randn(1000) * 0.01 + 0.0001
    prices = 50000 * np.cumprod(1 + returns)
    
    data = pd.DataFrame({
        'timestamp': dates,
        'open': prices * (1 + np.random.randn(1000) * 0.001),
        'high': prices * (1 + abs(np.random.randn(1000) * 0.005)),
        'low': prices * (1 - abs(np.random.randn(1000) * 0.005)),
        'close': prices,
        'volume': np.random.randint(1000, 10000, 1000),
    })
    
    # Run backtest
    config = BacktestConfig(
        initial_balance=10000,
        leverage=5,
        stop_loss_pct=2,
        take_profit_pct=5,
    )
    
    engine = BacktestEngine(config)
    result = engine.run(data, sma_crossover_strategy, "BTC/USDT")
    
    print(result)
