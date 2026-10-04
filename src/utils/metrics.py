"""
Metrics Module
The Autonomous Alpha - Prometheus Metrics Exporter

Exposes trading metrics for monitoring:
- Trade performance
- LLM latency
- System health
"""

import time
from functools import wraps
from typing import Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

from loguru import logger

try:
    from prometheus_client import (
        Counter, Histogram, Gauge, Info,
        start_http_server, REGISTRY,
        generate_latest, CollectorRegistry
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed. Metrics disabled.")


# ============================================================================
# Metric Definitions
# ============================================================================

if PROMETHEUS_AVAILABLE:
    # Trade metrics
    TRADES_TOTAL = Counter(
        'trading_trades_total',
        'Total number of trades executed',
        ['symbol', 'direction', 'outcome']
    )
    
    TRADE_PNL = Histogram(
        'trading_trade_pnl_percent',
        'Trade P&L distribution in percent',
        ['symbol', 'direction'],
        buckets=[-10, -5, -3, -2, -1, -0.5, 0, 0.5, 1, 2, 3, 5, 10, 20]
    )
    
    POSITION_VALUE = Gauge(
        'trading_position_value_usd',
        'Current position value in USD',
        ['symbol', 'direction']
    )
    
    PORTFOLIO_VALUE = Gauge(
        'trading_portfolio_value_usd',
        'Total portfolio value in USD'
    )
    
    PORTFOLIO_PNL_TOTAL = Gauge(
        'trading_portfolio_pnl_percent',
        'Total portfolio P&L in percent'
    )
    
    # LLM metrics
    LLM_REQUESTS_TOTAL = Counter(
        'trading_llm_requests_total',
        'Total LLM requests',
        ['model', 'agent', 'status']
    )
    
    LLM_LATENCY = Histogram(
        'trading_llm_latency_seconds',
        'LLM request latency in seconds',
        ['model', 'agent'],
        buckets=[0.5, 1, 2, 5, 10, 20, 30, 60, 120]
    )
    
    LLM_TOKENS = Counter(
        'trading_llm_tokens_total',
        'Total tokens used',
        ['model', 'type']  # type: prompt, completion
    )
    
    # Council metrics
    COUNCIL_DECISIONS = Counter(
        'trading_council_decisions_total',
        'Council decision outcomes',
        ['action', 'vetoed']
    )
    
    COUNCIL_LATENCY = Histogram(
        'trading_council_latency_seconds',
        'Full council analysis latency',
        buckets=[5, 10, 20, 30, 60, 120, 180]
    )
    
    # Risk metrics
    RISK_VETOS = Counter(
        'trading_risk_vetos_total',
        'Risk Guardian veto count',
        ['reason']
    )
    
    DRAWDOWN_CURRENT = Gauge(
        'trading_drawdown_current_percent',
        'Current drawdown percentage'
    )
    
    # System metrics
    SYSTEM_INFO = Info(
        'trading_system',
        'System information'
    )
    
    HEARTBEAT = Gauge(
        'trading_heartbeat_timestamp',
        'Last heartbeat timestamp'
    )
    
    INVOCATION_COUNT = Counter(
        'trading_invocations_total',
        'Total trading loop invocations'
    )


# ============================================================================
# Metric Collection Classes
# ============================================================================

@dataclass
class TradeMetrics:
    """Collect metrics for a single trade"""
    symbol: str
    direction: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime | None = None
    exit_price: float | None = None
    pnl_percent: float | None = None
    outcome: str | None = None  # win, loss, breakeven
    
    def record_close(self, exit_price: float, exit_time: datetime | None = None):
        """Record trade close and update metrics"""
        self.exit_price = exit_price
        self.exit_time = exit_time or datetime.now()
        
        if self.direction == "LONG":
            self.pnl_percent = ((exit_price - self.entry_price) / self.entry_price) * 100
        else:
            self.pnl_percent = ((self.entry_price - exit_price) / self.entry_price) * 100
            
        if self.pnl_percent > 0.1:
            self.outcome = "win"
        elif self.pnl_percent < -0.1:
            self.outcome = "loss"
        else:
            self.outcome = "breakeven"
            
        if PROMETHEUS_AVAILABLE:
            TRADES_TOTAL.labels(
                symbol=self.symbol,
                direction=self.direction,
                outcome=self.outcome
            ).inc()
            
            TRADE_PNL.labels(
                symbol=self.symbol,
                direction=self.direction
            ).observe(self.pnl_percent)


class MetricsCollector:
    """
    Central metrics collector for the trading system.
    """
    
    def __init__(self, port: int = 8080):
        self.port = port
        self._started = False
        self._start_time = datetime.now()
        
    def start_server(self):
        """Start Prometheus metrics HTTP server"""
        if not PROMETHEUS_AVAILABLE:
            logger.warning("Prometheus not available, metrics server not started")
            return
            
        if not self._started:
            start_http_server(self.port)
            self._started = True
            logger.info(f"Metrics server started on port {self.port}")
            
            # Set system info
            SYSTEM_INFO.info({
                'version': '0.1.0',
                'name': 'autonomous_alpha',
                'start_time': self._start_time.isoformat(),
            })
            
    def heartbeat(self):
        """Update heartbeat timestamp"""
        if PROMETHEUS_AVAILABLE:
            HEARTBEAT.set(time.time())
            
    def record_invocation(self):
        """Record a trading loop invocation"""
        if PROMETHEUS_AVAILABLE:
            INVOCATION_COUNT.inc()
            self.heartbeat()
            
    def record_portfolio(self, value: float, pnl_percent: float):
        """Record portfolio metrics"""
        if PROMETHEUS_AVAILABLE:
            PORTFOLIO_VALUE.set(value)
            PORTFOLIO_PNL_TOTAL.set(pnl_percent)
            
    def record_position(self, symbol: str, direction: str, value: float):
        """Record position metrics"""
        if PROMETHEUS_AVAILABLE:
            POSITION_VALUE.labels(symbol=symbol, direction=direction).set(value)
            
    def record_llm_request(
        self,
        model: str,
        agent: str,
        latency_seconds: float,
        tokens: int,
        success: bool = True,
    ):
        """Record LLM request metrics"""
        if PROMETHEUS_AVAILABLE:
            status = "success" if success else "error"
            LLM_REQUESTS_TOTAL.labels(model=model, agent=agent, status=status).inc()
            LLM_LATENCY.labels(model=model, agent=agent).observe(latency_seconds)
            LLM_TOKENS.labels(model=model, type="total").inc(tokens)
            
    def record_council_decision(
        self,
        action: str,
        vetoed: bool,
        latency_seconds: float,
    ):
        """Record council decision metrics"""
        if PROMETHEUS_AVAILABLE:
            COUNCIL_DECISIONS.labels(action=action, vetoed=str(vetoed)).inc()
            COUNCIL_LATENCY.observe(latency_seconds)
            
    def record_veto(self, reason: str):
        """Record Risk Guardian veto"""
        if PROMETHEUS_AVAILABLE:
            RISK_VETOS.labels(reason=reason).inc()
            
    def record_drawdown(self, percent: float):
        """Record current drawdown"""
        if PROMETHEUS_AVAILABLE:
            DRAWDOWN_CURRENT.set(percent)


# ============================================================================
# Decorators for automatic metric collection
# ============================================================================

def track_llm_latency(model: str = "unknown", agent: str = "unknown"):
    """Decorator to track LLM request latency"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                latency = time.perf_counter() - start
                if PROMETHEUS_AVAILABLE:
                    LLM_LATENCY.labels(model=model, agent=agent).observe(latency)
                    LLM_REQUESTS_TOTAL.labels(model=model, agent=agent, status="success").inc()
                return result
            except Exception as e:
                if PROMETHEUS_AVAILABLE:
                    LLM_REQUESTS_TOTAL.labels(model=model, agent=agent, status="error").inc()
                raise
                
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                latency = time.perf_counter() - start
                if PROMETHEUS_AVAILABLE:
                    LLM_LATENCY.labels(model=model, agent=agent).observe(latency)
                    LLM_REQUESTS_TOTAL.labels(model=model, agent=agent, status="success").inc()
                return result
            except Exception as e:
                if PROMETHEUS_AVAILABLE:
                    LLM_REQUESTS_TOTAL.labels(model=model, agent=agent, status="error").inc()
                raise
                
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


# Global collector instance
metrics = MetricsCollector()


if __name__ == "__main__":
    # Test metrics
    metrics.start_server()
    
    # Simulate some metrics
    metrics.record_invocation()
    metrics.record_portfolio(10000, 5.5)
    metrics.record_llm_request("deepseek-r1", "bull_researcher", 2.5, 1500)
    metrics.record_council_decision("LONG", False, 15.5)
    
    print("Metrics server running on :8080/metrics")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            time.sleep(1)
            metrics.heartbeat()
    except KeyboardInterrupt:
        print("\nStopped")
