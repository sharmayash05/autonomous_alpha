"""
Logging & Alerts Utility
The Autonomous Alpha - Structured Logging and Notifications

Provides:
- Structured logging with rotation
- Trade alerts via multiple channels
- Performance notifications
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Any
from dataclasses import dataclass
from enum import Enum

from loguru import logger

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    TRADE = "trade"
    PROFIT = "profit"
    LOSS = "loss"


@dataclass
class Alert:
    """Alert message"""
    level: AlertLevel
    title: str
    message: str
    timestamp: datetime = None
    data: dict = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


def setup_logging(
    log_dir: Path | str = "logs",
    log_level: str = "INFO",
    rotation: str = "10 MB",
    retention: str = "1 week",
    console: bool = True,
    structured: bool = True,
):
    """
    Configure logging for the trading system.
    
    Args:
        log_dir: Directory for log files
        log_level: Minimum log level
        rotation: Log file rotation size
        retention: How long to keep old logs
        console: Enable console output
        structured: Use structured JSON logs
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Remove default handler
    logger.remove()
    
    # Console handler
    if console:
        logger.add(
            sys.stderr,
            level=log_level,
            format="<green>{time:HH:mm:ss}</green> | "
                   "<level>{level: <8}</level> | "
                   "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
                   "<level>{message}</level>",
            colorize=True,
        )
    
    # File handler - human readable
    logger.add(
        log_dir / "trading_{time:YYYY-MM-DD}.log",
        level=log_level,
        rotation=rotation,
        retention=retention,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    )
    
    # File handler - JSON structured (for analysis)
    if structured:
        logger.add(
            log_dir / "trading_{time:YYYY-MM-DD}.json",
            level=log_level,
            rotation=rotation,
            retention=retention,
            serialize=True,
        )
    
    # Trade-specific log
    logger.add(
        log_dir / "trades.log",
        level="INFO",
        filter=lambda record: "trade" in record["extra"],
        format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
        rotation="1 month",
    )
    
    logger.info(f"Logging configured: level={log_level}, dir={log_dir}")


class TelegramAlerts:
    """
    Send alerts via Telegram bot.
    """
    
    API_URL = "https://api.telegram.org/bot{token}/sendMessage"
    
    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
    ):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self._enabled = bool(self.bot_token and self.chat_id)
        
        if not self._enabled:
            logger.warning("Telegram alerts not configured")
            
    async def send(self, alert: Alert) -> bool:
        """Send alert to Telegram"""
        if not self._enabled or not HTTPX_AVAILABLE:
            return False
            
        # Format message
        emoji_map = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.ERROR: "❌",
            AlertLevel.CRITICAL: "🚨",
            AlertLevel.TRADE: "📊",
            AlertLevel.PROFIT: "✅",
            AlertLevel.LOSS: "🔴",
        }
        
        emoji = emoji_map.get(alert.level, "📢")
        
        text = f"{emoji} <b>{alert.title}</b>\n\n{alert.message}"
        
        if alert.data:
            text += "\n\n<pre>"
            for key, value in alert.data.items():
                text += f"{key}: {value}\n"
            text += "</pre>"
            
        text += f"\n\n<i>{alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</i>"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.API_URL.format(token=self.bot_token),
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                    },
                    timeout=10.0,
                )
                return response.status_code == 200
                
        except Exception as e:
            logger.error(f"Telegram alert failed: {e}")
            return False


class DiscordAlerts:
    """
    Send alerts via Discord webhook.
    """
    
    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        self._enabled = bool(self.webhook_url)
        
        if not self._enabled:
            logger.warning("Discord alerts not configured")
            
    async def send(self, alert: Alert) -> bool:
        """Send alert to Discord"""
        if not self._enabled or not HTTPX_AVAILABLE:
            return False
            
        # Color map
        color_map = {
            AlertLevel.INFO: 0x3498DB,      # Blue
            AlertLevel.WARNING: 0xF39C12,   # Orange
            AlertLevel.ERROR: 0xE74C3C,     # Red
            AlertLevel.CRITICAL: 0x9B59B6,  # Purple
            AlertLevel.TRADE: 0x2ECC71,     # Green
            AlertLevel.PROFIT: 0x2ECC71,    # Green
            AlertLevel.LOSS: 0xE74C3C,      # Red
        }
        
        embed = {
            "title": alert.title,
            "description": alert.message,
            "color": color_map.get(alert.level, 0x95A5A6),
            "timestamp": alert.timestamp.isoformat(),
        }
        
        if alert.data:
            embed["fields"] = [
                {"name": k, "value": str(v), "inline": True}
                for k, v in alert.data.items()
            ]
            
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json={"embeds": [embed]},
                    timeout=10.0,
                )
                return response.status_code == 204
                
        except Exception as e:
            logger.error(f"Discord alert failed: {e}")
            return False


class AlertManager:
    """
    Central alert manager that dispatches to multiple channels.
    """
    
    def __init__(self):
        self.telegram = TelegramAlerts()
        self.discord = DiscordAlerts()
        self._handlers: list[Callable[[Alert], Any]] = []
        
    def add_handler(self, handler: Callable[[Alert], Any]):
        """Add custom alert handler"""
        self._handlers.append(handler)
        
    async def send(self, alert: Alert):
        """Send alert to all configured channels"""
        # Log locally
        log_method = getattr(logger, alert.level.value, logger.info)
        log_method(f"[ALERT] {alert.title}: {alert.message}")
        
        # Send to external channels
        tasks = []
        
        if self.telegram._enabled:
            tasks.append(self.telegram.send(alert))
            
        if self.discord._enabled:
            tasks.append(self.discord.send(alert))
            
        for handler in self._handlers:
            try:
                result = handler(alert)
                if asyncio.iscoroutine(result):
                    tasks.append(result)
            except Exception as e:
                logger.error(f"Alert handler error: {e}")
                
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    async def trade_opened(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        leverage: int = 1,
    ):
        """Send trade opened alert"""
        await self.send(Alert(
            level=AlertLevel.TRADE,
            title=f"Trade Opened: {symbol}",
            message=f"Opened {side.upper()} position",
            data={
                "Symbol": symbol,
                "Side": side.upper(),
                "Quantity": f"{quantity:.6f}",
                "Price": f"${price:,.2f}",
                "Leverage": f"{leverage}x",
            },
        ))
        
    async def trade_closed(
        self,
        symbol: str,
        side: str,
        pnl_usd: float,
        pnl_pct: float,
        reason: str = "",
    ):
        """Send trade closed alert"""
        level = AlertLevel.PROFIT if pnl_usd > 0 else AlertLevel.LOSS
        emoji = "✅" if pnl_usd > 0 else "❌"
        
        await self.send(Alert(
            level=level,
            title=f"{emoji} Trade Closed: {symbol}",
            message=f"Closed {side.upper()} with {pnl_pct:+.2f}% P&L",
            data={
                "Symbol": symbol,
                "P&L": f"${pnl_usd:+,.2f}",
                "Return": f"{pnl_pct:+.2f}%",
                "Reason": reason,
            },
        ))
        
    async def risk_warning(self, message: str, data: dict = None):
        """Send risk warning alert"""
        await self.send(Alert(
            level=AlertLevel.WARNING,
            title="⚠️ Risk Warning",
            message=message,
            data=data,
        ))
        
    async def system_error(self, error: str, details: str = ""):
        """Send system error alert"""
        await self.send(Alert(
            level=AlertLevel.ERROR,
            title="❌ System Error",
            message=error,
            data={"Details": details} if details else None,
        ))


# Global instances
alerts = AlertManager()


if __name__ == "__main__":
    # Test logging and alerts
    setup_logging(log_level="DEBUG")
    
    logger.info("Testing logging system")
    logger.warning("This is a warning")
    logger.error("This is an error")
    
    # Test trade log
    logger.bind(trade=True).info("BTC/USDT LONG opened @ 107000")
    
    # Test alerts (won't actually send without credentials)
    async def test_alerts():
        await alerts.trade_opened(
            symbol="BTC/USDT",
            side="long",
            quantity=0.1,
            price=107000,
            leverage=10,
        )
        
        await alerts.trade_closed(
            symbol="BTC/USDT",
            side="long",
            pnl_usd=500,
            pnl_pct=4.67,
            reason="take_profit",
        )
        
    asyncio.run(test_alerts())
    
    print("\n✅ Logging and alerts system configured")
