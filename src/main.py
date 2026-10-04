"""
The Autonomous Alpha - Main Entry Point
LLM-Centric Brutal Trading God

This is the main orchestrator that brings all components together:
- LLM Client for AI inference
- Trading Council for multi-agent decision making
- Reflexion Loop for self-improvement
- Exchange connections for execution
"""

import asyncio
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Configure logging
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)

# Portfolio persistence file
PORTFOLIO_FILE = Path(__file__).parent.parent / "data" / "portfolio_state.json"

# Import robust portfolio manager
from src.core.portfolio import PortfolioManager, PositionSide as PortfolioPositionSide


def save_portfolio_legacy(portfolio: dict) -> None:
    """DEPRECATED: Legacy save function for backwards compatibility with dashboard."""
    try:
        legacy_file = Path(__file__).parent.parent / "data" / "portfolio.json"
        legacy_file.parent.mkdir(parents=True, exist_ok=True)
        with open(legacy_file, "w") as f:
            json.dump(portfolio, f, indent=2, default=str)
    except Exception as e:
        logger.debug(f"Legacy portfolio save failed: {e}")


def convert_portfolio_for_dashboard(pm: PortfolioManager) -> dict:
    """Convert PortfolioManager state to legacy dict format for dashboard compatibility."""
    positions_list = []
    for symbol, pos in pm.state.positions.items():
        positions_list.append(
            {
                "symbol": symbol,
                "direction": "LONG"
                if pos.side == PortfolioPositionSide.LONG
                else "SHORT",
                "entry_price": pos.entry_price,
                "size_usd": pos.margin,
                "leverage": pos.leverage,
                "notional_usd": pos.notional_value,
                "stop_loss": pos.stop_loss,
                "take_profit": pos.take_profit,
                "opened_at": pos.entry_time.isoformat(),
                "unrealized_pnl_pct": pos.unrealized_pnl_percent,
                "market_context": {},
            }
        )

    return {
        "initial_balance": pm.state.initial_balance,
        "balance": pm.state.cash_balance,
        "positions": positions_list,
        "total_pnl": pm.state.realized_pnl,
        "trade_history": [
            {
                "trade_id": t.trade_id,
                "symbol": t.symbol,
                "direction": t.side.value.upper(),
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl_percent": t.pnl_percent,
                "pnl_usd": t.pnl_usd,
                "leverage": t.leverage,
                "closed_at": t.exit_time.isoformat(),
            }
            for t in pm.state.closed_trades
        ],
    }


logger.add(
    "logs/trading_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="DEBUG",
)

console = Console()


def capture_market_context(market_data: dict, symbol: str = "BTC") -> dict:
    """Capture minimal market context for reflexion learning."""
    asset = market_data.get(symbol, {})
    return {
        "price": asset.get("price"),
        "rsi_14": asset.get("rsi_14"),
        "trend": asset.get("trend"),
        "ema_20": asset.get("ema_20"),
        "ema_50": asset.get("ema_50"),
        "fear_greed": market_data.get("fear_greed", {}).get("value"),
        "timestamp": datetime.now().isoformat(),
    }


def load_config(config_dir: Path) -> dict:
    """Load all configuration files"""
    config = {}

    config_files = ["agents.yaml", "exchanges.yaml", "risk_params.yaml"]

    for filename in config_files:
        filepath = config_dir / filename
        if filepath.exists():
            with open(filepath) as f:
                config[filename.replace(".yaml", "")] = yaml.safe_load(f)
        else:
            logger.warning(f"Config file not found: {filepath}")

    return config


def print_simple_banner():
    """Simple banner without Unicode issues"""
    print("=" * 60)
    print("   AUTONOMOUS ALPHA - TRADING SYSTEM")
    print("=" * 60)
    print("LLM-Powered Multi-Agent Cryptocurrency Trading")
    print("Starting components...")
    print("=" * 60)


def print_banner():
    """Print the startup banner"""
    banner = """
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║   ████████╗██╗  ██╗███████╗     █████╗ ██╗     ██████╗ ██╗  ██╗   ║
║   ╚══██╔══╝██║  ██║██╔════╝    ██╔══██╗██║     ██╔══██╗██║  ██║   ║
║      ██║   ███████║█████╗      ███████║██║     ██████╔╝███████║   ║
║      ██║   ██╔══██║██╔══╝      ██╔══██║██║     ██╔═══╝ ██╔══██║   ║
║      ██║   ██║  ██║███████╗    ██║  ██║███████╗██║     ██║  ██║   ║
║      ╚═╝   ╚═╝  ╚═╝╚══════╝    ╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝  ╚═╝   ║
║                                                                   ║
║               A U T O N O M O U S   A L P H A                     ║
║                  The Brutal Trading God                           ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold cyan")


async def health_check(llm_client) -> bool:
    """Check if all systems are operational"""
    console.print("\n[bold yellow]Running System Health Check...[/bold yellow]\n")

    table = Table(title="System Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Details", style="dim")

    all_healthy = True

    # Check LLM
    try:
        health = await llm_client.health_check()
        if health.get("api_available"):
            model = health.get("model", "unknown")
            table.add_row("LLM API", "✅ Online", f"Model: {model}")
        else:
            table.add_row(
                "LLM API", "❌ Offline", f"URL: {health.get('base_url', 'unknown')}"
            )
            all_healthy = False
    except Exception as e:
        table.add_row("LLM API", "❌ Error", str(e)[:40])
        all_healthy = False

    # Check config
    config_dir = Path(__file__).parent.parent / "config"
    if (config_dir / "agents.yaml").exists():
        table.add_row("Config", "✅ Loaded", "agents.yaml found")
    else:
        table.add_row("Config", "⚠️ Missing", "Using defaults")

    # Check memory
    try:
        from src.memory.reflector import TradingMemory

        memory = TradingMemory()
        stats = memory.get_stats()
        table.add_row(
            "Memory",
            "✅ Ready",
            f"{stats['total_lessons']} lessons ({stats['backend']})",
        )
    except ImportError:
        table.add_row("Memory", "⚠️ Limited", "Qdrant not installed")

    console.print(table)
    console.print()

    return all_healthy


async def run_trading_loop(
    mode: str,
    config: dict,
    interval_minutes: int = 5,
):
    """
    Main trading loop.

    Args:
        mode: 'paper' or 'live'
        config: Configuration dict
        interval_minutes: How often to run the council
    """
    from src.core.llm_client import LLMClient
    from src.core.council import TradingCouncil
    from src.memory.reflector import ReflexionLoop, TradingMemory, TradeRecord
    from src.data.realtime_fetcher import RealTimeDataFetcher
    from src.data.news_fetcher import NewsAggregator
    from src.evolution.strategy_evolver import StrategyEvolver

    console.print(
        f"\n[bold green]Starting Trading Loop (Mode: {mode.upper()})[/bold green]\n"
    )

    if mode == "live":
        console.print(
            Panel(
                "[bold red]⚠️ LIVE TRADING MODE ⚠️\n\n"
                "Real money is at risk!\n"
                "Make sure you understand the risks.\n"
                "Press Ctrl+C to stop at any time.[/bold red]",
                border_style="red",
            )
        )

    async with LLMClient() as llm_client:
        # Initialize components
        council = TradingCouncil(llm_client, config.get("agents", {}))
        journal = council.journal  # Get journal reference for tracking
        memory = TradingMemory()
        reflexion = ReflexionLoop(llm_client, memory)
        evolver = StrategyEvolver(llm_client, memory)  # Self-evolution engine
        data_fetcher = RealTimeDataFetcher()
        news_fetcher = NewsAggregator()  # Add news fetcher

        # Start dashboard server on port 5000
        try:
            from src.dashboard import start_dashboard_thread, update_dashboard

            dashboard_thread = start_dashboard_thread(port=5000)
            logger.info("🌐 Dashboard running at http://localhost:5000")
        except Exception as e:
            logger.warning(f"Dashboard failed to start: {e}")
            update_dashboard = lambda x: None  # No-op if dashboard fails

        # Initialize PortfolioManager (robust accounting with fees, drawdown tracking, etc.)
        if PORTFOLIO_FILE.exists():
            try:
                portfolio_manager = PortfolioManager.load(PORTFOLIO_FILE)
                logger.info(
                    f"📂 Loaded portfolio: {len(portfolio_manager.state.positions)} positions, ${portfolio_manager.state.realized_pnl:+.2f} realized PnL"
                )
            except Exception as e:
                logger.warning(f"Failed to load portfolio, starting fresh: {e}")
                portfolio_manager = PortfolioManager(
                    initial_balance=10000.0, persist_path=PORTFOLIO_FILE
                )
        else:
            portfolio_manager = PortfolioManager(
                initial_balance=10000.0, persist_path=PORTFOLIO_FILE
            )
            logger.info("📂 Created new portfolio with $10,000 balance")

        # Register self-evolution callback when trades close
        def on_trade_closed_callback(closed_trade):
            """Trigger reflexion learning when a trade closes."""
            try:
                trade_record = TradeRecord(
                    trade_id=closed_trade.trade_id,
                    symbol=closed_trade.symbol,
                    direction=closed_trade.side.value.upper(),
                    entry_price=closed_trade.entry_price,
                    exit_price=closed_trade.exit_price,
                    entry_time=closed_trade.entry_time,
                    exit_time=closed_trade.exit_time,
                    pnl_dollars=closed_trade.pnl_usd,
                    pnl_percent=closed_trade.pnl_percent,
                    original_thesis=closed_trade.exit_reason,
                    market_context_entry=closed_trade.market_context_entry or {},
                    market_context_exit=closed_trade.market_context_exit or {},
                    leverage=closed_trade.leverage,
                )
                asyncio.create_task(reflexion.process_completed_trade(trade_record))
                logger.info(
                    f"🧠 LEARNING: Reflecting on {closed_trade.symbol} trade..."
                )

                # Update market memory snapshot with actual trade outcome
                if closed_trade.snapshot_timestamp:
                    try:
                        from src.memory.market_memory import get_market_memory

                        mm = get_market_memory()
                        mm.update_outcome(
                            timestamp=closed_trade.snapshot_timestamp,
                            pnl_percent=closed_trade.pnl_percent,
                            direction=closed_trade.side.value.upper(),
                        )
                    except Exception as e:
                        logger.debug(f"Market memory update failed: {e}")

                # Update domain patterns with actual trade outcome
                try:
                    from src.memory.domain_memory import get_domain_memory

                    dm = get_domain_memory()
                    for domain in ["technical", "sentiment", "fundamental"]:
                        dm.update_recent_pattern_outcomes(
                            domain, closed_trade.pnl_percent
                        )
                except Exception as e:
                    logger.debug(f"Domain pattern update failed: {e}")

            except Exception as e:
                logger.error(f"Reflexion callback failed: {e}")

        portfolio_manager.on_trade_closed = on_trade_closed_callback

        # Trade history for evolution analysis
        trade_history: list[dict] = [
            {
                "symbol": t.symbol,
                "direction": t.side.value.upper(),
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl_percent": t.pnl_percent,
                "pnl_usd": t.pnl_usd,
                "leverage": t.leverage,
                "closed_at": t.exit_time.isoformat(),
            }
            for t in portfolio_manager.state.closed_trades
        ]

        invocation_count = 0
        start_time = datetime.now()

        async with data_fetcher:
            while True:
                try:
                    invocation_count += 1
                    journal.increment_invocation()  # Track invocation in journal

                    # Log portfolio snapshot for agent context
                    journal.log_portfolio_snapshot(
                        {
                            "equity": portfolio_manager.state.total_equity,
                            "cash_balance": portfolio_manager.state.cash_balance,
                            "unrealized_pnl": portfolio_manager.state.unrealized_pnl,
                            "realized_pnl": portfolio_manager.state.realized_pnl,
                            "exposure_percent": portfolio_manager.state.exposure_percent,
                            "positions": [
                                {
                                    "symbol": symbol,
                                    "side": pos.side.value.upper(),
                                    "pnl_percent": pos.unrealized_pnl_percent,
                                    "entry_price": pos.entry_price,
                                    "current_price": pos.current_price,
                                }
                                for symbol, pos in portfolio_manager.state.positions.items()
                            ],
                        }
                    )

                    elapsed = (datetime.now() - start_time).total_seconds() / 60

                    logger.info(
                        f"📊 Invocation #{invocation_count} | Elapsed: {elapsed:.1f}min"
                    )

                    # Fetch REAL market data from Binance and other sources
                    market_data = await data_fetcher.fetch_all(symbols=["BTC", "ETH"])

                    # Fetch news headlines
                    try:
                        news_articles = await news_fetcher.fetch_all(
                            symbols=["BTC", "ETH"], limit=100
                        )
                        market_data["news"] = news_fetcher.format_for_llm(
                            news_articles, max_chars=50000
                        )
                        logger.info(f"📰 Fetched {len(news_articles)} news articles")
                    except Exception as e:
                        logger.warning(f"News fetch failed: {e}")
                        market_data["news"] = "No news available"

                    # ========== CRITICAL: Update position prices BEFORE capturing account data ==========
                    # This ensures PM sees current unrealized PnL, not stale data from previous invocation
                    current_btc_price = market_data.get("BTC", {}).get("price", 0)
                    current_eth_price = market_data.get("ETH", {}).get("price", 0)
                    portfolio_manager.update_price("BTC", current_btc_price)
                    portfolio_manager.update_price("ETH", current_eth_price)

                    # Add portfolio and trading context (using PortfolioManager state with FRESH prices)
                    market_data["invocation"] = invocation_count
                    market_data["mode"] = mode
                    pm_state = portfolio_manager.state
                    market_data["account"] = {
                        "balance": pm_state.total_equity,  # Use total_equity for balance
                        "cash_balance": pm_state.cash_balance,
                        "initial_balance": pm_state.initial_balance,
                        "positions": [
                            {
                                "symbol": p.symbol,
                                "direction": p.side.value.upper(),
                                "entry_price": p.entry_price,
                                "size_usd": p.margin,  # Use margin as size_usd
                                "leverage": p.leverage,
                                "stop_loss": p.stop_loss,
                                "take_profit": p.take_profit,
                                "unrealized_pnl_pct": p.unrealized_pnl_percent,  # Correct attribute name
                            }
                            for p in pm_state.positions.values()
                        ],
                        "total_pnl": pm_state.total_pnl_usd,  # Use property
                        "pnl_pct": pm_state.total_pnl_percent,  # Use property
                    }

                    # Get relevant past lessons from memory
                    btc_price = market_data.get("BTC", {}).get("price", 0)
                    btc_rsi = market_data.get("BTC", {}).get("rsi_14", 50)
                    lessons = reflexion.get_relevant_lessons(
                        f"BTC at ${btc_price:,.0f} with RSI {btc_rsi:.1f} and {market_data.get('BTC', {}).get('trend', 'unknown')} trend"
                    )
                    market_data["past_lessons"] = lessons

                    # Log lessons for visibility
                    if (
                        lessons
                        and lessons[0].get("lesson_learned")
                        != "No relevant lessons found."
                    ):
                        logger.info(f"\n{'=' * 60}")
                        logger.info(f"📚 PAST LESSONS ({len(lessons)} retrieved)")
                        logger.info(f"{'=' * 60}")
                        for i, lesson in enumerate(lessons[:5], 1):  # Show top 5
                            grade = lesson.get("trade_grade", "?")
                            pnl = lesson.get("pnl_percent", 0)
                            text = lesson.get("lesson_learned", "No lesson")[:100]
                            emoji = "✅" if pnl > 0 else "❌"
                            logger.info(f"{emoji} [{grade}] {pnl:+.1f}%: {text}")
                        logger.info(f"{'=' * 60}\n")

                    # ========== PHASE 2-3: Check SL/TP (prices already updated above) ==========
                    # Note: current_btc_price and current_eth_price already defined above

                    # Check stop-loss and take-profit for all positions
                    for symbol, pos in list(portfolio_manager.state.positions.items()):
                        current_price = (
                            current_btc_price if "BTC" in symbol else current_eth_price
                        )

                        # Check liquidation (100% margin loss)
                        if pos.unrealized_pnl_percent <= -100:
                            logger.warning(
                                f"⚠️ LIQUIDATED: {symbol} {pos.side.value.upper()} position wiped out!"
                            )
                            closed_trade = portfolio_manager.close_position(
                                symbol,
                                current_price,
                                exit_reason="liquidation",
                                market_context_exit=capture_market_context(
                                    market_data, symbol
                                ),
                                snapshot_timestamp=datetime.now().isoformat(),
                            )
                            if closed_trade:
                                trade_history.append(
                                    {
                                        "symbol": symbol,
                                        "direction": closed_trade.side.value.upper(),
                                        "entry_price": closed_trade.entry_price,
                                        "exit_price": closed_trade.exit_price,
                                        "pnl_percent": closed_trade.pnl_percent,
                                        "pnl_usd": closed_trade.pnl_usd,
                                        "leverage": closed_trade.leverage,
                                        "closed_at": datetime.now().isoformat(),
                                        "exit_reason": "liquidation",
                                    }
                                )
                                journal.clear_position_thesis(symbol, "liquidation")
                            continue

                        # Check stop-loss
                        if pos.stop_loss:
                            if (
                                pos.side == PortfolioPositionSide.LONG
                                and current_price <= pos.stop_loss
                            ) or (
                                pos.side == PortfolioPositionSide.SHORT
                                and current_price >= pos.stop_loss
                            ):
                                logger.info(
                                    f"🛑 STOP-LOSS HIT: {symbol} @ ${current_price:,.2f}"
                                )
                                closed_trade = portfolio_manager.close_position(
                                    symbol,
                                    pos.stop_loss,
                                    exit_reason="stop_loss",
                                    market_context_exit=capture_market_context(
                                        market_data, symbol
                                    ),
                                    snapshot_timestamp=datetime.now().isoformat(),
                                )
                                if closed_trade:
                                    trade_history.append(
                                        {
                                            "symbol": symbol,
                                            "direction": closed_trade.side.value.upper(),
                                            "entry_price": closed_trade.entry_price,
                                            "exit_price": closed_trade.exit_price,
                                            "pnl_percent": closed_trade.pnl_percent,
                                            "pnl_usd": closed_trade.pnl_usd,
                                            "leverage": closed_trade.leverage,
                                            "closed_at": datetime.now().isoformat(),
                                            "exit_reason": "stop_loss",
                                        }
                                    )
                                    journal.clear_position_thesis(symbol, "stop_loss")
                                continue

                        # Check take-profit
                        if pos.take_profit:
                            if (
                                pos.side == PortfolioPositionSide.LONG
                                and current_price >= pos.take_profit
                            ) or (
                                pos.side == PortfolioPositionSide.SHORT
                                and current_price <= pos.take_profit
                            ):
                                logger.info(
                                    f"🎯 TAKE-PROFIT HIT: {symbol} @ ${current_price:,.2f}"
                                )
                                closed_trade = portfolio_manager.close_position(
                                    symbol,
                                    pos.take_profit,
                                    exit_reason="take_profit",
                                    market_context_exit=capture_market_context(
                                        market_data, symbol
                                    ),
                                    snapshot_timestamp=datetime.now().isoformat(),
                                )
                                if closed_trade:
                                    trade_history.append(
                                        {
                                            "symbol": symbol,
                                            "direction": closed_trade.side.value.upper(),
                                            "entry_price": closed_trade.entry_price,
                                            "exit_price": closed_trade.exit_price,
                                            "pnl_percent": closed_trade.pnl_percent,
                                            "pnl_usd": closed_trade.pnl_usd,
                                            "leverage": closed_trade.leverage,
                                            "closed_at": datetime.now().isoformat(),
                                            "exit_reason": "take_profit",
                                        }
                                    )
                                    journal.clear_position_thesis(symbol, "take_profit")
                                continue

                        # ========== TRAILING STOP - Lock in profits programmatically ==========
                        # Config values (from config_loader.py)
                        TRAILING_ACTIVATION_PCT = (
                            1.0  # Activate trailing after 1% profit on margin
                        )
                        TRAILING_DISTANCE_PCT = 0.5  # Trail at 0.5% below current price

                        if pos.unrealized_pnl_percent > TRAILING_ACTIVATION_PCT:
                            if pos.side == PortfolioPositionSide.LONG:
                                # For LONG, trail stop below current price
                                new_trail_stop = current_price * (
                                    1 - TRAILING_DISTANCE_PCT / 100
                                )
                                # Only move up, never down (lock in gains)
                                if (
                                    pos.stop_loss is None
                                    or new_trail_stop > pos.stop_loss
                                ):
                                    old_sl = pos.stop_loss
                                    pos.stop_loss = new_trail_stop
                                    if old_sl:
                                        logger.info(
                                            f"📈 TRAILING: {symbol} SL ${old_sl:,.0f} → ${new_trail_stop:,.0f} (lock {pos.unrealized_pnl_percent:.1f}% gain)"
                                        )
                                    else:
                                        logger.info(
                                            f"📈 TRAILING: {symbol} SL activated at ${new_trail_stop:,.0f}"
                                        )
                            else:
                                # For SHORT, trail stop above current price
                                new_trail_stop = current_price * (
                                    1 + TRAILING_DISTANCE_PCT / 100
                                )
                                # Only move down, never up (lock in gains)
                                if (
                                    pos.stop_loss is None
                                    or new_trail_stop < pos.stop_loss
                                ):
                                    old_sl = pos.stop_loss
                                    pos.stop_loss = new_trail_stop
                                    if old_sl:
                                        logger.info(
                                            f"📉 TRAILING: {symbol} SL ${old_sl:,.0f} → ${new_trail_stop:,.0f} (lock {pos.unrealized_pnl_percent:.1f}% gain)"
                                        )
                                    else:
                                        logger.info(
                                            f"📉 TRAILING: {symbol} SL activated at ${new_trail_stop:,.0f}"
                                        )

                        # ========== TIME-BASED EXIT - Close stale positions ==========
                        MAX_HOLD_HOURS = 48  # Max time to hold a position
                        position_age_hours = (
                            datetime.now() - pos.entry_time
                        ).total_seconds() / 3600

                        if position_age_hours > MAX_HOLD_HOURS:
                            # Only close if not trending strongly in our favor (less than 5% on margin)
                            if abs(pos.unrealized_pnl_percent) < 5.0:
                                logger.warning(
                                    f"⏰ STALE: {symbol} held {position_age_hours:.0f}h with {pos.unrealized_pnl_percent:+.1f}% - closing"
                                )
                                closed_trade = portfolio_manager.close_position(
                                    symbol,
                                    current_price,
                                    exit_reason="stale_position",
                                    market_context_exit=capture_market_context(
                                        market_data, symbol
                                    ),
                                    snapshot_timestamp=datetime.now().isoformat(),
                                )
                                if closed_trade:
                                    trade_history.append(
                                        {
                                            "symbol": symbol,
                                            "direction": closed_trade.side.value.upper(),
                                            "entry_price": closed_trade.entry_price,
                                            "exit_price": closed_trade.exit_price,
                                            "pnl_percent": closed_trade.pnl_percent,
                                            "pnl_usd": closed_trade.pnl_usd,
                                            "leverage": closed_trade.leverage,
                                            "closed_at": datetime.now().isoformat(),
                                            "exit_reason": "stale_position",
                                        }
                                    )
                                    journal.clear_position_thesis(
                                        symbol, "stale_position"
                                    )
                                continue

                    # Save portfolio state and update legacy format for dashboard
                    portfolio_manager.save()
                    portfolio = convert_portfolio_for_dashboard(portfolio_manager)
                    save_portfolio_legacy(portfolio)

                    # Run council analysis
                    result = await council.analyze(market_data)

                    # ========== Process council decisions ==========
                    decision = result.get("decision", {})

                    # Update PM strategy in journal (market regime, thesis, etc.)
                    if decision.get("analysis") or decision.get("market_regime"):
                        journal.update_pm_strategy(
                            market_regime=decision.get("market_regime"),
                            thesis=decision.get("analysis", "")[:200]
                            if decision.get("analysis")
                            else None,
                        )

                    if decision.get("decisions"):
                        for d in decision["decisions"]:
                            action = d.get("action", "").upper()
                            symbol = d.get("symbol", "BTC")
                            current_price = (
                                current_btc_price
                                if symbol == "BTC"
                                else current_eth_price
                            )

                            if action == "OPEN":
                                # Use PortfolioManager to open position (proper balance/margin checks)
                                leverage = d.get("leverage", 10)
                                size_usd = d.get("size_usd", 500)  # This is margin
                                entry_price = d.get("entry_price", current_price)
                                quantity = (
                                    size_usd / entry_price * leverage
                                )  # Convert margin to quantity
                                direction = d.get("direction", "LONG")

                                position = portfolio_manager.open_position(
                                    symbol=symbol,
                                    side=PortfolioPositionSide.LONG
                                    if direction == "LONG"
                                    else PortfolioPositionSide.SHORT,
                                    quantity=quantity,
                                    price=entry_price,
                                    leverage=leverage,
                                    stop_loss=d.get("stop_loss"),
                                    take_profit=d.get("take_profit"),
                                    market_context_entry=capture_market_context(
                                        market_data, symbol
                                    ),
                                )

                                if position:
                                    # Track for evolution
                                    trade_history.append(
                                        {
                                            "action": "OPEN",
                                            "symbol": symbol,
                                            "direction": direction,
                                            "entry_price": entry_price,
                                            "leverage": leverage,
                                            "margin": size_usd,
                                            "opened_at": datetime.now().isoformat(),
                                        }
                                    )
                                    portfolio_manager.save()

                            elif action == "CLOSE":
                                if symbol in portfolio_manager.state.positions:
                                    exit_price = d.get("exit_price", current_price)
                                    close_percent = float(
                                        d.get("close_percent", 100)
                                    )  # Default: full close
                                    closed_trade = portfolio_manager.close_position(
                                        symbol=symbol,
                                        price=exit_price,
                                        exit_reason=d.get("reasoning", "signal")[:50],
                                        market_context_exit=capture_market_context(
                                            market_data, symbol
                                        ),
                                        close_percent=close_percent,
                                        snapshot_timestamp=datetime.now().isoformat(),  # Link to market memory
                                    )

                                    if closed_trade:
                                        # Track for evolution
                                        trade_history.append(
                                            {
                                                "symbol": symbol,
                                                "direction": closed_trade.side.value.upper(),
                                                "entry_price": closed_trade.entry_price,
                                                "exit_price": closed_trade.exit_price,
                                                "pnl_percent": closed_trade.pnl_percent,
                                                "pnl_usd": closed_trade.pnl_usd,
                                                "leverage": closed_trade.leverage,
                                                "closed_at": datetime.now().isoformat(),
                                            }
                                        )

                                        # Check if evolution should be triggered
                                        try:
                                            if await evolver.should_evolve(
                                                trade_history
                                            ):
                                                pm_rules = council.portfolio_manager.prompt_template
                                                evolution_result = await evolver.evolve(
                                                    trade_history, pm_rules
                                                )
                                                if evolution_result.get(
                                                    "evolved_rules"
                                                ):
                                                    logger.info(
                                                        f"🧬 EVOLVED: Added {len(evolution_result['evolved_rules'])} new rules!"
                                                    )
                                        except Exception as e:
                                            logger.error(f"Evolution failed: {e}")

                                        portfolio_manager.save()
                                        journal.clear_position_thesis(symbol, "signal")
                                else:
                                    logger.warning(
                                        f"⚠️ No position to close for {symbol}"
                                    )

                            elif action == "MODIFY":
                                if symbol in portfolio_manager.state.positions:
                                    pos = portfolio_manager.state.positions[symbol]
                                    if d.get("stop_loss"):
                                        pos.stop_loss = d["stop_loss"]
                                    if d.get("take_profit"):
                                        pos.take_profit = d["take_profit"]
                                    logger.info(
                                        f"🔄 MODIFIED: {symbol} | SL: ${pos.stop_loss or 0:,.2f} TP: ${pos.take_profit or 0:,.2f}"
                                    )
                                    portfolio_manager.save()

                            elif action == "HOLD":
                                logger.info(
                                    f"⏸️ HOLD: {symbol} {d.get('reasoning', '')[:50]}..."
                                )

                            # Log PM decision to journal for history tracking
                            journal.log_pm_decision(d)

                    elif decision.get("vetoed"):
                        veto_reason = decision.get("veto_reason", "Unknown")
                        logger.warning(f"⛔ Vetoed: {veto_reason}")
                        # Log mistake to journal for future learning
                        journal.log_mistake(
                            mistake=f"Trade vetoed by Risk Guardian",
                            lesson=f"Veto reason: {veto_reason[:100]}",
                        )
                    else:
                        logger.info("🔄 No action taken")

                    # ========== Log portfolio status ==========
                    stats = portfolio_manager.get_stats()
                    logger.info(
                        f"💰 Portfolio: ${stats['total_equity']:,.2f} | "
                        f"Positions: {stats['open_positions']} | "
                        f"Unrealized: ${stats['unrealized_pnl']:+.2f} | "
                        f"Realized: ${stats['realized_pnl']:+.2f} | "
                        f"Max DD: {stats['max_drawdown_percent']:.1f}%"
                    )

                    # Log each position's status
                    for symbol, pos in portfolio_manager.state.positions.items():
                        logger.info(
                            f"   📊 {symbol} {pos.side.value.upper()} @ ${pos.entry_price:,.2f} → "
                            f"${pos.current_price or 0:,.2f} ({pos.unrealized_pnl_percent:+.2f}%)"
                        )

                    # Update dashboard-compatible portfolio
                    portfolio = convert_portfolio_for_dashboard(portfolio_manager)
                    save_portfolio_legacy(portfolio)

                    # Broadcast to dashboard
                    try:
                        analyses = result.get("analyses", {})

                        # Get journal stats for dashboard
                        journal_stats = {}
                        try:
                            journal_data = journal.get_full_journal()
                            journal_stats = {
                                "invocation_count": journal_data.get(
                                    "invocation_count", 0
                                ),
                                "agents": {
                                    name: {
                                        "analyses_count": len(data.get("analyses", [])),
                                        "has_thesis": bool(data.get("active_thesis")),
                                        "thesis": data.get("active_thesis", {}).get(
                                            "thesis", "None"
                                        )[:100]
                                        if data.get("active_thesis")
                                        else None,
                                    }
                                    for name, data in journal_data.get(
                                        "agents", {}
                                    ).items()
                                },
                            }
                        except:
                            pass

                        # Get evolved rules for dashboard
                        evolved_rules_data = {}
                        try:
                            evolved_rules_data = {
                                "version": evolver.current_version,
                                "rules_count": len(evolver.evolved_rules),
                                "rules": evolver.evolved_rules[:5],  # Top 5 rules
                            }
                        except:
                            pass

                        # Get memory stats for dashboard
                        memory_stats = {}
                        try:
                            from src.memory.market_memory import get_market_memory

                            mm = get_market_memory()
                            memory_stats["market_memory"] = mm.get_stats()
                        except:
                            pass

                        # Add domain memory stats
                        try:
                            from src.memory.domain_memory import get_domain_memory

                            dm = get_domain_memory()
                            if dm:
                                domain_stats = dm.get_stats()
                                logger.debug(f"Domain stats: {domain_stats}")
                                memory_stats["domain_memory"] = {
                                    "technical_patterns": domain_stats.get(
                                        "technical", 0
                                    ),
                                    "sentiment_patterns": domain_stats.get(
                                        "sentiment", 0
                                    ),
                                    "fundamental_patterns": domain_stats.get(
                                        "fundamental", 0
                                    ),
                                    "total_patterns": sum(domain_stats.values())
                                    if domain_stats
                                    else 0,
                                }
                        except Exception as e:
                            logger.warning(f"Domain memory stats failed: {e}")

                        update_dashboard(
                            {
                                "portfolio": portfolio,
                                "market_data": market_data,
                                "agents": {
                                    "bull": analyses.get("bull"),
                                    "bear": analyses.get("bear"),
                                    "technical": analyses.get("technical"),
                                    "sentiment": analyses.get("sentiment"),
                                },
                                "pm_decision": decision,
                                "risk_assessment": result.get("risk_assessment"),
                                "lessons": lessons,
                                "invocation": invocation_count,
                                # NEW: Additional data for complete dashboard visibility
                                "journal": journal_stats,
                                "evolved_rules": evolved_rules_data,
                                "memory_stats": memory_stats,
                                "trade_history": portfolio.get(
                                    "trade_history", []
                                ),  # All trades from portfolio
                            }
                        )
                        logger.debug(
                            f"📊 Dashboard updated with invocation #{invocation_count}"
                        )
                    except Exception as e:
                        logger.warning(f"Dashboard update failed: {e}")

                    # Store market snapshot for RAG memory (historical precedents)
                    try:
                        from src.memory.market_memory import get_market_memory

                        mm = get_market_memory()
                        decision_action = "HOLD"
                        if decision.get("decisions"):
                            d = decision["decisions"][0]
                            decision_action = d.get("action", "HOLD")
                        mm.store_snapshot(
                            market_data,
                            decision=decision_action,
                            position_open=len(portfolio.get("positions", [])) > 0,
                        )
                        logger.debug(f"📊 Stored market snapshot for RAG memory")

                        # Look-Back Loop: Reconcile old predictions with actual outcomes
                        btc_price = market_data.get("BTC", {}).get("price", 0)
                        mm.reconcile_snapshots(btc_price)
                    except Exception as e:
                        pass  # Memory storage is non-critical

                    # INTELLIGENT MEMORY PRUNING: Run periodically to prevent prompt flooding
                    if (
                        invocation_count % 10 == 0
                    ):  # Every 10 invocations (~50 min at 5-min intervals)
                        try:
                            logger.info("🧹 Running periodic memory pruning...")

                            # Prune trading lessons
                            prune_result = await memory.prune_lessons(
                                llm_client, max_lessons=50
                            )
                            if prune_result.get("pruned", 0) > 0:
                                logger.info(
                                    f"📚 Lessons: Pruned {prune_result['pruned']}, kept {prune_result['kept']}"
                                )

                            # Prune domain patterns (age/outcome based)
                            from src.memory.domain_memory import get_domain_memory

                            dm = get_domain_memory()
                            domain_result = dm.prune_stale_patterns(
                                max_age_days=30, max_per_domain=100
                            )
                            for domain, stats in domain_result.items():
                                if stats.get("pruned", 0) > 0:
                                    logger.info(
                                        f"🧠 {domain}: Pruned {stats['pruned']} stale, kept {stats['kept']}"
                                    )

                            # LLM-based intelligent domain pattern pruning (quality scoring)
                            smart_result = await dm.prune_patterns_intelligent(
                                llm_client, max_per_domain=100
                            )
                            for domain, stats in smart_result.items():
                                if stats.get("pruned", 0) > 0:
                                    logger.info(
                                        f"🎯 {domain}: Pruned {stats['pruned']} low-quality, kept {stats['kept']}"
                                    )

                            # Quality-based market memory pruning (prioritize reconciled/correct)
                            from src.memory.market_memory import get_market_memory

                            mm = get_market_memory()
                            mm_result = mm.prune_snapshots_quality(max_snapshots=500)
                            if mm_result.get("pruned", 0) > 0:
                                logger.info(
                                    f"📊 Market: Pruned {mm_result['pruned']}, kept {mm_result['kept']}"
                                )

                            # Prune evolved strategy rules (remove stale/contradictory rules)
                            if evolver.evolved_rules:
                                recent_lessons = memory.recall_similar(
                                    "trading lessons patterns", top_k=10
                                )
                                performance_metrics = {
                                    "win_rate": len(
                                        [
                                            t
                                            for t in trade_history
                                            if t.get("pnl_percent", 0) > 0
                                        ]
                                    )
                                    / max(len(trade_history), 1),
                                    "profit_factor": 1.0,  # Simplified
                                    "total_trades": len(trade_history),
                                }
                                rules_result = await evolver.prune_rules(
                                    recent_lessons, performance_metrics
                                )
                                if rules_result.get("rules_to_prune"):
                                    logger.info(
                                        f"🧬 Rules: Pruned {len(rules_result.get('rules_to_prune', []))} stale/contradictory rules"
                                    )

                        except Exception as e:
                            logger.debug(f"Memory pruning failed: {e}")  # Non-critical

                    # Wait for next interval
                    logger.info(
                        f"💤 Sleeping {interval_minutes} minutes until next invocation..."
                    )
                    await asyncio.sleep(interval_minutes * 60)

                except KeyboardInterrupt:
                    logger.info("🛑 Received shutdown signal")
                    break
                except Exception as e:
                    logger.exception(f"Error in trading loop: {e}")
                    await asyncio.sleep(60)  # Wait a minute before retrying


async def run_backtest(
    start_date: str,
    end_date: str,
    config: dict,
):
    """
    Run backtesting on historical data.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        config: Configuration dict
    """
    console.print(f"\n[bold blue]Backtesting: {start_date} → {end_date}[/bold blue]\n")

    # TODO: Implement backtesting
    console.print("[yellow]Backtesting not yet implemented. Coming soon![/yellow]")
    console.print(
        "Use Freqtrade's backtesting engine with the Autonomous Alpha strategy."
    )


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="The Autonomous Alpha - LLM-Centric Trading Agent"
    )
    parser.add_argument(
        "--mode",
        choices=["paper", "live", "backtest", "health"],
        default="health",
        help="Operating mode",
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Backtest start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="Backtest end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Trading interval in minutes",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config",
        help="Path to config directory",
    )

    args = parser.parse_args()

    # Print banner (fixed for Windows)
    print_simple_banner()

    # Load config
    config_dir = Path(args.config)
    if not config_dir.is_absolute():
        config_dir = Path(__file__).parent.parent / config_dir
    config = load_config(config_dir)

    async def async_main():
        from src.core.llm_client import LLMClient

        if args.mode == "health":
            async with LLMClient() as client:
                healthy = await health_check(client)
                if healthy:
                    console.print(
                        "[bold green]All systems operational! ✅[/bold green]"
                    )
                else:
                    console.print("[bold red]Some systems need attention ⚠️[/bold red]")

        elif args.mode in ["paper", "live"]:
            await run_trading_loop(
                mode=args.mode,
                config=config,
                interval_minutes=args.interval,
            )

        elif args.mode == "backtest":
            if not args.start or not args.end:
                console.print("[red]Backtest requires --start and --end dates[/red]")
                return
            await run_backtest(
                start_date=args.start,
                end_date=args.end,
                config=config,
            )

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down gracefully...[/yellow]")


if __name__ == "__main__":
    main()
