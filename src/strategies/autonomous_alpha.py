"""
Autonomous Alpha Strategy for Freqtrade
The Autonomous Alpha - LLM-Centric Trading Strategy

This module provides a Freqtrade-compatible strategy that uses
the LLM-based multi-agent council for trading decisions.
"""

import asyncio
import json
from datetime import datetime
from typing import Optional
from functools import partial

import numpy as np
import pandas as pd
from pandas import DataFrame

try:
    from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
    from freqtrade.persistence import Trade
    FREQTRADE_AVAILABLE = True
except ImportError:
    FREQTRADE_AVAILABLE = False
    # Create dummy classes for development without freqtrade
    class IStrategy:
        pass
    class IntParameter:
        def __init__(self, *args, **kwargs):
            pass
    class DecimalParameter:
        def __init__(self, *args, **kwargs):
            pass

from loguru import logger


class AutonomousAlphaStrategy(IStrategy):
    """
    LLM-Centric Trading Strategy for Freqtrade.
    
    This strategy overrides traditional indicator-based logic
    with multi-agent LLM reasoning for all trading decisions.
    
    Features:
    - Multi-agent council for entry/exit decisions
    - Reflexion-based learning from past trades
    - Order Flow Imbalance integration
    - Risk Guardian with veto power
    """
    
    # Strategy metadata
    INTERFACE_VERSION = 3
    
    # Minimal ROI - let LLM manage exits
    minimal_roi = {
        "0": 100.0  # Essentially disabled, LLM decides
    }
    
    # Stoploss - set wide, Risk Guardian will manage
    stoploss = -0.10  # 10% max, but Risk Guardian can override
    
    # Trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True
    
    # Timeframe
    timeframe = '5m'
    
    # Can short
    can_short = True
    
    # Use custom stoploss
    use_custom_stoploss = True
    
    # Run on new candle only
    process_only_new_candles = True
    
    # Startup candles needed
    startup_candle_count = 50
    
    # Hyperparameters (can be optimized)
    confidence_threshold = DecimalParameter(
        0.5, 0.9, default=0.7, space='buy', optimize=True
    )
    
    max_open_trades = IntParameter(
        1, 6, default=3, space='buy', optimize=True
    )
    
    def __init__(self, config: dict) -> None:
        super().__init__(config)
        
        self._llm_client = None
        self._council = None
        self._reflexion = None
        self._last_analysis = {}
        self._council_cache = {}
        self._cache_duration_seconds = 60
        
    def _init_llm(self):
        """Lazy initialization of LLM components"""
        if self._llm_client is None:
            try:
                from ..core.llm_client import LLMClient
                from ..core.council import TradingCouncil
                from ..memory.reflector import ReflexionLoop, TradingMemory
                
                self._llm_client = LLMClient()
                self._council = TradingCouncil(self._llm_client)
                self._reflexion = ReflexionLoop(
                    self._llm_client,
                    TradingMemory()
                )
                logger.info("LLM components initialized")
            except Exception as e:
                logger.error(f"Failed to initialize LLM: {e}")
                
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Calculate technical indicators to provide context to LLM.
        The LLM uses these as inputs but makes its own decisions.
        """
        # Trend indicators
        dataframe['ema_20'] = dataframe['close'].ewm(span=20, adjust=False).mean()
        dataframe['ema_50'] = dataframe['close'].ewm(span=50, adjust=False).mean()
        dataframe['sma_200'] = dataframe['close'].rolling(window=200).mean()
        
        # Momentum indicators
        dataframe['rsi_7'] = self._calculate_rsi(dataframe['close'], 7)
        dataframe['rsi_14'] = self._calculate_rsi(dataframe['close'], 14)
        
        # MACD
        exp1 = dataframe['close'].ewm(span=12, adjust=False).mean()
        exp2 = dataframe['close'].ewm(span=26, adjust=False).mean()
        dataframe['macd'] = exp1 - exp2
        dataframe['macd_signal'] = dataframe['macd'].ewm(span=9, adjust=False).mean()
        dataframe['macd_hist'] = dataframe['macd'] - dataframe['macd_signal']
        
        # Volatility
        dataframe['atr'] = self._calculate_atr(dataframe, 14)
        dataframe['bb_upper'], dataframe['bb_middle'], dataframe['bb_lower'] = \
            self._calculate_bollinger_bands(dataframe['close'], 20, 2)
        
        # Volume
        dataframe['volume_sma'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        
        return dataframe
    
    def _calculate_rsi(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_atr(self, df: DataFrame, period: int) -> pd.Series:
        """Calculate ATR"""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
    
    def _calculate_bollinger_bands(
        self, prices: pd.Series, period: int, std_dev: float
    ) -> tuple:
        """Calculate Bollinger Bands"""
        middle = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        return upper, middle, lower
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Query LLM council for entry signals.
        """
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        
        # Only analyze recent candles to save LLM calls
        if len(dataframe) < self.startup_candle_count:
            return dataframe
            
        # Get latest data for LLM
        latest = dataframe.iloc[-1]
        pair = metadata['pair']
        
        # Check cache
        cache_key = f"{pair}_{latest.name}"
        if cache_key in self._council_cache:
            cached = self._council_cache[cache_key]
            if (datetime.now() - cached['time']).seconds < self._cache_duration_seconds:
                decision = cached['decision']
                if decision.get('action') == 'LONG' and decision.get('confidence', 0) >= self.confidence_threshold.value:
                    dataframe.loc[dataframe.index[-1], 'enter_long'] = 1
                elif decision.get('action') == 'SHORT' and decision.get('confidence', 0) >= self.confidence_threshold.value:
                    dataframe.loc[dataframe.index[-1], 'enter_short'] = 1
                return dataframe
        
        # Build context for LLM
        context = self._build_llm_context(dataframe, metadata)
        
        # Query council (async in sync context)
        try:
            self._init_llm()
            if self._council:
                decision = asyncio.get_event_loop().run_until_complete(
                    self._query_council(context)
                )
                
                # Cache result
                self._council_cache[cache_key] = {
                    'time': datetime.now(),
                    'decision': decision,
                }
                
                # Apply decision
                if decision.get('action') == 'LONG':
                    if decision.get('confidence', 0) >= self.confidence_threshold.value:
                        dataframe.loc[dataframe.index[-1], 'enter_long'] = 1
                        logger.info(f"LLM LONG signal for {pair}: confidence={decision.get('confidence')}")
                        
                elif decision.get('action') == 'SHORT':
                    if decision.get('confidence', 0) >= self.confidence_threshold.value:
                        dataframe.loc[dataframe.index[-1], 'enter_short'] = 1
                        logger.info(f"LLM SHORT signal for {pair}: confidence={decision.get('confidence')}")
                        
        except Exception as e:
            logger.error(f"LLM query failed: {e}")
            
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Query LLM council for exit signals.
        """
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        
        # Similar to entry, check if LLM recommends exit
        # For now, rely on trailing stops and custom_stoploss
        
        return dataframe
    
    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs
    ) -> float:
        """
        Dynamic stoploss based on ATR and trade context.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) < 1:
            return self.stoploss
            
        latest = dataframe.iloc[-1]
        atr = latest.get('atr', 0)
        
        if atr > 0 and current_rate > 0:
            # ATR-based stop: 2x ATR from entry
            atr_stop = (2 * atr) / current_rate
            
            # Don't make stop tighter than 2%
            atr_stop = max(atr_stop, 0.02)
            
            # Return negative value for stoploss
            return -atr_stop
            
        return self.stoploss
    
    def _build_llm_context(self, dataframe: DataFrame, metadata: dict) -> dict:
        """Build context dictionary for LLM"""
        latest = dataframe.iloc[-1]
        pair = metadata['pair']
        
        # Get recent price series
        recent_prices = dataframe['close'].tail(20).tolist()
        recent_rsi = dataframe['rsi_14'].tail(10).tolist()
        recent_macd = dataframe['macd_hist'].tail(10).tolist()
        
        return {
            'pair': pair,
            'timestamp': str(latest.name),
            'current_price': float(latest['close']),
            'indicators': {
                'ema_20': float(latest['ema_20']) if not np.isnan(latest['ema_20']) else None,
                'ema_50': float(latest['ema_50']) if not np.isnan(latest['ema_50']) else None,
                'rsi_7': float(latest['rsi_7']) if not np.isnan(latest['rsi_7']) else None,
                'rsi_14': float(latest['rsi_14']) if not np.isnan(latest['rsi_14']) else None,
                'macd_hist': float(latest['macd_hist']) if not np.isnan(latest['macd_hist']) else None,
                'atr': float(latest['atr']) if not np.isnan(latest['atr']) else None,
                'volume_ratio': float(latest['volume_ratio']) if not np.isnan(latest['volume_ratio']) else None,
            },
            'price_series': [float(p) for p in recent_prices if not np.isnan(p)],
            'rsi_series': [float(r) for r in recent_rsi if not np.isnan(r)],
            'macd_series': [float(m) for m in recent_macd if not np.isnan(m)],
        }
    
    async def _query_council(self, context: dict) -> dict:
        """Query the trading council for a decision"""
        if not self._council:
            return {'action': 'HOLD', 'confidence': 0}
            
        try:
            result = await self._council.analyze(context)
            
            decision = result.get('decision', {})
            decisions = decision.get('decisions', [])
            
            if decisions and not decision.get('vetoed', False):
                first_decision = decisions[0]
                return {
                    'action': first_decision.get('direction', 'HOLD'),
                    'confidence': first_decision.get('confidence', 0),
                    'reasoning': first_decision.get('reasoning', ''),
                }
                
        except Exception as e:
            logger.error(f"Council query failed: {e}")
            
        return {'action': 'HOLD', 'confidence': 0}
    
    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> bool:
        """
        Final confirmation before trade entry.
        Risk Guardian has final say here.
        """
        # Get past lessons for similar setups
        if self._reflexion:
            try:
                lessons = self._reflexion.get_relevant_lessons(
                    f"{pair} {side} at price {rate}"
                )
                
                # If we have strong negative lessons for this setup, reconsider
                for lesson in lessons:
                    if lesson.get('trade_grade') in ['D', 'F']:
                        if lesson.get('score', 0) > 0.8:
                            logger.warning(
                                f"Blocking trade due to similar past failure: "
                                f"{lesson.get('lesson_learned')}"
                            )
                            return False
                            
            except Exception as e:
                logger.error(f"Reflexion check failed: {e}")
                
        return True
    
    def confirm_trade_exit(
        self,
        pair: str,
        trade: Trade,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        exit_reason: str,
        current_time: datetime,
        **kwargs,
    ) -> bool:
        """Confirm trade exit"""
        return True
    
    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> Optional[str]:
        """
        Custom exit logic based on LLM analysis.
        """
        # Take partial profits at certain thresholds
        if current_profit > 0.03:  # 3% profit
            return "partial_profit_3pct"
            
        # Cut losses if thesis invalidated
        # This would require re-querying the LLM
        
        return None


# Standalone strategy for testing without Freqtrade
class StandaloneStrategy:
    """
    Standalone version of the strategy for testing without Freqtrade.
    """
    
    def __init__(self, llm_client=None):
        self._llm_client = llm_client
        self._council = None
        
    async def init_async(self):
        """Initialize async components"""
        if self._llm_client is None:
            from ..core.llm_client import LLMClient
            self._llm_client = LLMClient()
            
        from ..core.council import TradingCouncil
        self._council = TradingCouncil(self._llm_client)
        
    async def analyze(self, market_data: dict) -> dict:
        """Analyze market data and return trading decision"""
        if not self._council:
            await self.init_async()
            
        return await self._council.analyze(market_data)


if __name__ == "__main__":
    # Test standalone strategy
    import asyncio
    
    async def test():
        strategy = StandaloneStrategy()
        await strategy.init_async()
        
        result = await strategy.analyze({
            "BTC/USDT": {
                "price": 107000,
                "rsi_14": 55,
                "macd_hist": 50,
            }
        })
        
        print(json.dumps(result, indent=2, default=str))
        
    asyncio.run(test())
