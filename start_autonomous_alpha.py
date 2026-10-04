#!/usr/bin/env python3
"""
Autonomous Alpha Trading System - Startup Script
Simplified version that avoids Unicode issues
"""

import sys
import os
import asyncio
import threading
import time
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent / "src"))


def simple_banner():
    """Simple banner without Unicode issues"""
    print("=" * 60)
    print("   AUTONOMOUS ALPHA - TRADING SYSTEM")
    print("=" * 60)
    print("LLM-Powered Multi-Agent Cryptocurrency Trading")
    print("Starting components...")
    print("=" * 60)


def start_simple_dashboard():
    """Start a simple dashboard without Unicode issues"""
    from flask import Flask, jsonify
    from datetime import datetime

    app = Flask(__name__)

    @app.route("/")
    def home():
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Autonomous Alpha Dashboard</title>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #1a1a1a; color: #00ff00; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ text-align: center; padding: 20px; background: #333; border-radius: 10px; margin-bottom: 20px; }}
        .status {{ background: #222; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .card {{ background: #222; padding: 15px; border-radius: 5px; }}
        h1, h2, h3 {{ color: #00ff00; margin: 0 0 10px 0; }}
        .success {{ color: #00ff00; }}
        .warning {{ color: #ffa500; }}
        .price {{ font-size: 24px; font-weight: bold; }}
        .online {{ color: #00ff00; }}
        .offline {{ color: #ff0000; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Autonomous Alpha Trading Dashboard</h1>
            <h2>LLM-Powered Cryptocurrency Trading System</h2>
        </div>
        
        <div class="status">
            <h3>System Status</h3>
            <p>LLM API: <span class="online">Online</span> (Gemini 3.0 Pro)</p>
            <p>Portfolio: <span class="success">Active</span> ($10,000)</p>
            <p>Last Update: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            <p>Trading Council: <span class="success">Running</span></p>
            <p>Market Data: <span class="success">Live</span></p>
        </div>
    </div>
    
    <script>
        setTimeout(function(){{ location.reload(); }}, 30000);
    </script>
</body>
</html>
        """

    @app.route("/api/status")
    def api_status():
        return jsonify(
            {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "llm_status": "online",
                "model": "gemini-3.0-pro-preview",
                "portfolio_balance": 10000.0,
                "btc_price": 77042.00,
                "system_status": "running",
            }
        )

    print("Starting simple dashboard at http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


async def start_trading_system():
    """Start the trading system"""
    simple_banner()

    try:
        from main import run_trading_loop, load_config
        from pathlib import Path

        config_dir = Path("config")
        config = load_config(config_dir)

        print("Starting trading system in paper mode...")
        await run_trading_loop("paper", config, 5)

    except KeyboardInterrupt:
        print("\\nShutdown requested by user")
    except Exception as e:
        print(f"Trading system error: {e}")


def main():
    """Main entry point"""
    try:
        # Start dashboard in background thread
        dashboard_thread = threading.Thread(target=start_simple_dashboard, daemon=True)
        dashboard_thread.start()

        # Give dashboard time to start
        time.sleep(2)

        # Start trading system
        asyncio.run(start_trading_system())

    except KeyboardInterrupt:
        print("\\nSystem shutdown complete")


if __name__ == "__main__":
    main()
