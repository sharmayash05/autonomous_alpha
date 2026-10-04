"""
Configuration Loader
The Autonomous Alpha - Unified Configuration Management

Loads and validates all configuration:
- Agent settings
- Exchange connections
- Risk parameters
- Environment variables
"""

import os
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field

import yaml
from loguru import logger
from pydantic import BaseModel, Field, validator


# ============================================================================
# Configuration Models
# ============================================================================

class AgentModelConfig(BaseModel):
    """Configuration for a single agent's LLM"""
    model: str = "gemini-3.0-pro-preview"  # Default to user's LLM
    temperature: float = Field(default=0.5, ge=0, le=2)
    max_tokens: int = Field(default=16384, ge=128, le=65536)  # Unlimited


class AgentsConfig(BaseModel):
    """Configuration for all agents"""
    bull_researcher: AgentModelConfig = Field(default_factory=AgentModelConfig)
    bear_researcher: AgentModelConfig = Field(default_factory=AgentModelConfig)
    technical_analyst: AgentModelConfig = Field(default_factory=AgentModelConfig)
    sentiment_analyst: AgentModelConfig = Field(default_factory=AgentModelConfig)
    risk_guardian: AgentModelConfig = Field(default_factory=AgentModelConfig)
    portfolio_manager: AgentModelConfig = Field(default_factory=AgentModelConfig)
    
    debate_enabled: bool = True
    debate_rounds: int = 2
    parallel_analysis: bool = True


class ExchangeConfig(BaseModel):
    """Configuration for a single exchange"""
    enabled: bool = True
    api_key_env: str  # Environment variable name for API key
    api_secret_env: str  # Environment variable name for API secret
    testnet: bool = True
    trading_pairs: list[str] = []
    default_leverage: int = 1
    
    @property
    def api_key(self) -> str | None:
        return os.getenv(self.api_key_env)
    
    @property
    def api_secret(self) -> str | None:
        return os.getenv(self.api_secret_env)


class ExchangesConfig(BaseModel):
    """Configuration for all exchanges"""
    binance: ExchangeConfig | None = None
    bybit: ExchangeConfig | None = None
    
    websocket_reconnect_delay: int = 5
    order_timeout_seconds: int = 30


class PositionLimits(BaseModel):
    """Position sizing limits"""
    max_position_pct: float = Field(default=5.0, ge=0, le=100)
    max_portfolio_exposure_pct: float = Field(default=50.0, ge=0, le=100)
    max_leverage: int = Field(default=10, ge=1, le=125)
    max_single_asset_exposure_pct: float = Field(default=15.0, ge=0, le=100)


class StopLossConfig(BaseModel):
    """Stop loss configuration"""
    enabled: bool = True
    default_pct: float = 2.0
    atr_multiplier: float = 2.0
    trailing_enabled: bool = True
    trailing_activation_pct: float = 1.0
    trailing_distance_pct: float = 0.5


class TakeProfitConfig(BaseModel):
    """Take profit configuration"""
    enabled: bool = True
    targets: list[dict] = [
        {"pct": 2.0, "close_pct": 33},
        {"pct": 5.0, "close_pct": 33},
        {"pct": 10.0, "close_pct": 34},
    ]


class CircuitBreakers(BaseModel):
    """Circuit breaker configuration"""
    consecutive_losses_limit: int = 3
    consecutive_losses_pause_hours: int = 4
    daily_loss_limit_pct: float = 3.0
    weekly_loss_limit_pct: float = 7.0
    max_drawdown_pct: float = 10.0


class RiskConfig(BaseModel):
    """Full risk configuration"""
    position_limits: PositionLimits = Field(default_factory=PositionLimits)
    stop_loss: StopLossConfig = Field(default_factory=StopLossConfig)
    take_profit: TakeProfitConfig = Field(default_factory=TakeProfitConfig)
    circuit_breakers: CircuitBreakers = Field(default_factory=CircuitBreakers)
    
    min_sharpe_ratio: float = 1.5
    min_rr_ratio: float = 2.0
    news_blackout_minutes: int = 15


class TradingConfig(BaseModel):
    """Main trading configuration"""
    mode: str = "paper"  # paper, live
    interval_minutes: int = 5
    log_level: str = "INFO"
    metrics_port: int = 8080
    
    # LLM API configuration
    llm_base_url: str = "http://localhost:3000/gemini-antigravity/v1"
    llm_api_key: str = "123456"
    llm_model: str = "gemini-3.0-pro-preview"


class Config(BaseModel):
    """Root configuration"""
    trading: TradingConfig = Field(default_factory=TradingConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    exchanges: ExchangesConfig = Field(default_factory=ExchangesConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)


# ============================================================================
# Configuration Loader
# ============================================================================

class ConfigLoader:
    """
    Loads configuration from YAML files and environment variables.
    """
    
    def __init__(self, config_dir: Path | str | None = None):
        if config_dir is None:
            # Default to project config directory
            config_dir = Path(__file__).parent.parent.parent / "config"
        self.config_dir = Path(config_dir)
        self._config: Config | None = None
        
    def load(self) -> Config:
        """Load all configuration"""
        if self._config is not None:
            return self._config
            
        config_dict = {}
        
        # Load YAML files
        yaml_files = {
            "agents": "agents.yaml",
            "exchanges": "exchanges.yaml",
            "risk": "risk_params.yaml",
        }
        
        for key, filename in yaml_files.items():
            filepath = self.config_dir / filename
            if filepath.exists():
                try:
                    with open(filepath) as f:
                        data = yaml.safe_load(f)
                        if data:
                            config_dict[key] = data
                    logger.debug(f"Loaded config: {filename}")
                except Exception as e:
                    logger.error(f"Failed to load {filename}: {e}")
            else:
                logger.warning(f"Config file not found: {filepath}")
                
        # Load environment variables for trading config
        config_dict["trading"] = {
            "mode": os.getenv("TRADING_MODE", "paper"),
            "interval_minutes": int(os.getenv("TRADING_INTERVAL", "5")),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
            "metrics_port": int(os.getenv("METRICS_PORT", "8080")),
            "llm_base_url": os.getenv("LLM_BASE_URL", "http://localhost:3000/gemini-antigravity/v1"),
            "llm_api_key": os.getenv("LLM_API_KEY", "123456"),
            "llm_model": os.getenv("LLM_MODEL", "gemini-3.0-pro-preview"),
        }
        
        # Create config object
        try:
            self._config = Config(**config_dict)
            logger.info("Configuration loaded successfully")
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            logger.info("Using default configuration")
            self._config = Config()
            
        return self._config
        
    def reload(self) -> Config:
        """Force reload configuration"""
        self._config = None
        return self.load()
        
    @property
    def config(self) -> Config:
        """Get current configuration"""
        if self._config is None:
            return self.load()
        return self._config


# Global config loader instance
config_loader = ConfigLoader()


def get_config() -> Config:
    """Get the global configuration"""
    return config_loader.config


if __name__ == "__main__":
    # Test config loading
    config = get_config()
    
    print("\n" + "="*60)
    print("CONFIGURATION")
    print("="*60)
    
    print(f"\nTrading Mode: {config.trading.mode}")
    print(f"Interval: {config.trading.interval_minutes} min")
    print(f"Ollama URL: {config.trading.ollama_url}")
    
    print(f"\nRisk Limits:")
    print(f"  Max Position: {config.risk.position_limits.max_position_pct}%")
    print(f"  Max Leverage: {config.risk.position_limits.max_leverage}x")
    print(f"  Max Drawdown: {config.risk.circuit_breakers.max_drawdown_pct}%")
    
    print(f"\nAgents:")
    print(f"  PM Model: {config.agents.portfolio_manager.model}")
    print(f"  Debate: {config.agents.debate_enabled}")
