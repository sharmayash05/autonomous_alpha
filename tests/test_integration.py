"""
Integration Tests for The Autonomous Alpha
Run with: python -m pytest tests/ -v
"""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


class TestLLMClient:
    """Tests for the LLM client"""
    
    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test client can be initialized"""
        from src.core.llm_client import LLMClient
        
        client = LLMClient()
        assert "localhost:3001" in client.base_url
        assert client.default_model == "gemini-3-pro-preview"
        
    @pytest.mark.asyncio
    async def test_format_prompt(self):
        """Test prompt formatting"""
        from src.core.llm_client import format_prompt
        
        template = "Hello {name}, price is {price}"
        result = format_prompt(template, name="BTC", price=107000)
        assert result == "Hello BTC, price is 107000"


class TestTradingCouncil:
    """Tests for the multi-agent council"""
    
    def test_agent_config(self):
        """Test agent configuration"""
        from src.core.council import AgentConfig
        
        config = AgentConfig(
            name="Test Agent",
            model="test-model",
            temperature=0.5,
            max_tokens=1024,
            prompt_template="test",
            role="test_role",
        )
        
        assert config.name == "Test Agent"
        assert config.temperature == 0.5
        
    @pytest.mark.asyncio
    async def test_trading_state(self):
        """Test trading state structure"""
        from src.core.council import TradingState
        
        state: TradingState = {
            "market_data": {"BTC": {"price": 107000}},
            "timestamp": datetime.now().isoformat(),
            "bull_thesis": None,
            "bear_thesis": None,
            "technical_view": None,
            "sentiment_score": None,
            "sentiment_analysis": None,
            "debate_rounds": [],
            "current_round": 0,
            "consensus_reached": False,
            "proposed_decision": None,
            "final_decision": None,
            "risk_assessment": None,
            "risk_veto": False,
            "veto_reason": None,
        }
        
        assert state["market_data"]["BTC"]["price"] == 107000


class TestReflexion:
    """Tests for the Reflexion memory system"""
    
    def test_trade_record(self):
        """Test trade record creation"""
        from src.memory.reflector import TradeRecord
        
        trade = TradeRecord(
            trade_id="TEST-001",
            symbol="BTC",
            direction="LONG",
            entry_price=105000.0,
            exit_price=107000.0,
            entry_time=datetime.now(),
            exit_time=datetime.now(),
            pnl_dollars=200.0,
            pnl_percent=1.9,
            original_thesis="Test thesis",
            market_context_entry={"rsi": 50},
            market_context_exit={"rsi": 60},
        )
        
        assert trade.pnl_percent == 1.9
        assert trade.symbol == "BTC"
        
    def test_trading_memory_fallback(self):
        """Test trading memory with in-memory fallback"""
        from src.memory.reflector import TradingMemory, TradeReflection
        
        memory = TradingMemory()
        
        reflection = TradeReflection(
            trade_id="TEST-001",
            trade_grade="A",
            thesis_flaw=None,
            missed_signals=[],
            lesson_learned="Test lesson",
            embedding_text="BTC long test",
            timestamp=datetime.now().isoformat(),
            pnl_percent=5.0,
        )
        
        result = memory.store_lesson(reflection)
        assert result is True
        
        stats = memory.get_stats()
        assert stats["total_lessons"] == 1


class TestIndicators:
    """Tests for technical indicators"""
    
    def test_sma(self):
        """Test simple moving average"""
        from src.utils.indicators import sma
        
        data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        result = sma(data, 3)
        
        # First 2 values should be NaN
        assert len(result) == 10
        assert result[2] == 2.0  # (1+2+3)/3 = 2
        assert result[9] == 9.0  # (8+9+10)/3 = 9
        
    def test_ema(self):
        """Test exponential moving average"""
        from src.utils.indicators import ema
        
        data = [10] * 20  # Constant prices
        result = ema(data, 10)
        
        # EMA of constant should equal constant
        assert result[-1] == 10.0
        
    def test_rsi(self):
        """Test RSI calculation"""
        from src.utils.indicators import rsi
        
        # Increasing prices should have high RSI
        data = list(range(100, 150))
        result = rsi(data, 14)
        
        # Last RSI should be high (>70) for uptrend
        assert result[-1] > 70
        
    def test_technical_analyzer(self):
        """Test the technical analyzer wrapper"""
        from src.utils.indicators import TechnicalAnalyzer
        import random
        
        # Generate sample data
        prices = [100 + i * 0.1 + random.uniform(-0.5, 0.5) for i in range(100)]
        
        analyzer = TechnicalAnalyzer(prices)
        indicators = analyzer.get_all()
        signal = analyzer.get_signal()
        
        assert "ema_20" in indicators
        assert signal in ["STRONG_LONG", "WEAK_LONG", "NEUTRAL", "WEAK_SHORT", "STRONG_SHORT"]


class TestWebSocketFeed:
    """Tests for WebSocket data feed"""
    
    def test_order_book(self):
        """Test order book structure"""
        from src.data.websocket_feed import OrderBook, OrderBookLevel
        
        book = OrderBook(
            symbol="BTCUSDT",
            bids=[
                OrderBookLevel(price=107000, quantity=1.5),
                OrderBookLevel(price=106999, quantity=2.0),
            ],
            asks=[
                OrderBookLevel(price=107001, quantity=1.0),
                OrderBookLevel(price=107002, quantity=1.5),
            ],
            timestamp=datetime.now(),
        )
        
        assert book.best_bid == 107000
        assert book.best_ask == 107001
        assert book.mid_price == 107000.5
        assert book.spread == 1
        
    def test_trade(self):
        """Test trade structure"""
        from src.data.websocket_feed import Trade
        
        trade = Trade(
            symbol="BTCUSDT",
            price=107000.0,
            quantity=0.5,
            side="buy",
            timestamp=datetime.now(),
        )
        
        assert trade.price == 107000.0
        assert trade.side == "buy"


class TestExecutor:
    """Tests for exchange executor"""
    
    @pytest.mark.asyncio
    async def test_paper_executor(self):
        """Test paper trading executor"""
        from src.core.executor import PaperExecutor, OrderSide
        
        executor = PaperExecutor(initial_balance=10000.0)
        await executor.connect()
        
        # Set price
        executor.update_price("BTC/USDT", 50000.0)
        
        # Place order
        order = await executor.place_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            quantity=0.1,
            leverage=10,
        )
        
        assert order.status.value == "filled"
        
        # Check position
        positions = await executor.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "BTC/USDT"
        
        # Close position
        await executor.close_position("BTC/USDT")
        positions = await executor.get_positions()
        assert len(positions) == 0
        
        # Check stats
        stats = executor.get_stats()
        assert stats["total_trades"] == 2  # Open + Close


class TestSentiment:
    """Tests for sentiment fetcher"""
    
    def test_fear_greed_conversion(self):
        """Test Fear & Greed value conversion"""
        from src.data.sentiment_fetcher import FearGreedFetcher
        
        fetcher = FearGreedFetcher()
        
        # Extreme fear (0) should be -1
        assert fetcher.value_to_score(0) == -1.0
        
        # Neutral (50) should be 0
        assert fetcher.value_to_score(50) == 0.0
        
        # Extreme greed (100) should be +1
        assert fetcher.value_to_score(100) == 1.0
        
    def test_funding_conversion(self):
        """Test funding rate to sentiment conversion"""
        from src.data.sentiment_fetcher import BinanceFundingFetcher
        
        fetcher = BinanceFundingFetcher()
        
        # Positive funding = crowded long = bearish signal
        assert fetcher.funding_to_sentiment(0.001) < 0
        
        # Negative funding = crowded short = bullish signal
        assert fetcher.funding_to_sentiment(-0.001) > 0


# Quick run without pytest
if __name__ == "__main__":
    print("Running basic tests...")
    
    # Test indicators
    from src.utils.indicators import TechnicalAnalyzer
    import random
    
    prices = [100 + i * 0.1 for i in range(100)]
    analyzer = TechnicalAnalyzer(prices)
    print(f"Indicators: {analyzer.get_all()}")
    print(f"Signal: {analyzer.get_signal()}")
    
    # Test paper executor
    async def test_executor():
        from src.core.executor import PaperExecutor, OrderSide
        
        executor = PaperExecutor()
        await executor.connect()
        executor.update_price("BTC/USDT", 50000)
        
        order = await executor.place_order(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            quantity=0.1,
        )
        print(f"Order: {order}")
        print(f"Stats: {executor.get_stats()}")
        
    asyncio.run(test_executor())
    
    print("\n✅ All basic tests passed!")
