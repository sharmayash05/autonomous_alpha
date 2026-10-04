"""
Historical Data Fetcher
The Autonomous Alpha - OHLCV Data Retrieval

Fetches historical candlestick data for backtesting:
- Binance public API
- Local CSV cache
- Multiple timeframes
"""

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import pandas as pd
import httpx
from loguru import logger


TimeFrame = Literal["1m", "5m", "15m", "1h", "4h", "1d", "1w"]


class BinanceHistoricalFetcher:
    """
    Fetch historical OHLCV data from Binance public API.
    No API key required for public endpoints.
    """
    
    API_URL = "https://api.binance.com/api/v3/klines"
    
    # Binance timeframe mapping
    TIMEFRAME_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
        "1w": "1w",
    }
    
    # Max klines per request
    MAX_LIMIT = 1000
    
    def __init__(self, cache_dir: Path | str | None = None):
        self.cache_dir = Path(cache_dir) if cache_dir else Path("data/historical")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
    async def fetch(
        self,
        symbol: str,
        timeframe: TimeFrame = "1h",
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data.
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            timeframe: Candle timeframe
            start_time: Start datetime
            end_time: End datetime
            limit: Max number of candles
            
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        symbol = symbol.upper().replace("/", "")
        interval = self.TIMEFRAME_MAP.get(timeframe, timeframe)
        
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, self.MAX_LIMIT),
        }
        
        if start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["endTime"] = int(end_time.timestamp() * 1000)
            
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.API_URL,
                    params=params,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                
            return self._parse_klines(data, symbol)
            
        except Exception as e:
            logger.error(f"Failed to fetch historical data: {e}")
            return pd.DataFrame()
            
    async def fetch_range(
        self,
        symbol: str,
        timeframe: TimeFrame,
        start_time: datetime,
        end_time: datetime,
    ) -> pd.DataFrame:
        """
        Fetch historical data for a date range (handles pagination).
        """
        all_data = []
        current_start = start_time
        
        while current_start < end_time:
            df = await self.fetch(
                symbol=symbol,
                timeframe=timeframe,
                start_time=current_start,
                end_time=end_time,
                limit=1000,
            )
            
            if df.empty:
                break
                
            all_data.append(df)
            
            # Move to next batch
            last_timestamp = df.index[-1]
            current_start = last_timestamp + timedelta(minutes=1)
            
            # Rate limiting
            await asyncio.sleep(0.1)
            
        if not all_data:
            return pd.DataFrame()
            
        combined = pd.concat(all_data)
        return combined[~combined.index.duplicated(keep='first')]
        
    def _parse_klines(self, data: list, symbol: str) -> pd.DataFrame:
        """Parse Binance kline response"""
        if not data:
            return pd.DataFrame()
            
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        
        # Convert types
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
            
        # Set index and select columns
        df.set_index('timestamp', inplace=True)
        df = df[['open', 'high', 'low', 'close', 'volume']]
        df['symbol'] = symbol
        
        return df
        
    def save_to_cache(self, df: pd.DataFrame, symbol: str, timeframe: str):
        """Save data to local cache"""
        filename = f"{symbol}_{timeframe}.csv"
        path = self.cache_dir / filename
        df.to_csv(path)
        logger.info(f"Saved {len(df)} candles to {path}")
        
    def load_from_cache(
        self,
        symbol: str,
        timeframe: str,
    ) -> pd.DataFrame | None:
        """Load data from local cache"""
        filename = f"{symbol}_{timeframe}.csv"
        path = self.cache_dir / filename
        
        if path.exists():
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            logger.info(f"Loaded {len(df)} candles from {path}")
            return df
            
        return None
        
    async def get_with_cache(
        self,
        symbol: str,
        timeframe: TimeFrame,
        start_time: datetime,
        end_time: datetime,
        refresh: bool = False,
    ) -> pd.DataFrame:
        """Get data with caching"""
        symbol = symbol.upper().replace("/", "")
        
        # Try cache first
        if not refresh:
            cached = self.load_from_cache(symbol, timeframe)
            if cached is not None:
                # Filter to requested range
                mask = (cached.index >= start_time) & (cached.index <= end_time)
                filtered = cached[mask]
                if len(filtered) > 0:
                    return filtered
                    
        # Fetch fresh data
        df = await self.fetch_range(symbol, timeframe, start_time, end_time)
        
        if not df.empty:
            self.save_to_cache(df, symbol, timeframe)
            
        return df


class YahooFinanceFetcher:
    """
    Fetch historical data from Yahoo Finance (for forex/stocks).
    Uses yfinance library if available.
    """
    
    def __init__(self):
        try:
            import yfinance as yf
            self._yf = yf
            self._available = True
        except ImportError:
            self._available = False
            logger.warning("yfinance not installed. Yahoo Finance fetcher disabled.")
            
    async def fetch(
        self,
        symbol: str,
        timeframe: str = "1h",
        period: str = "1mo",
    ) -> pd.DataFrame:
        """
        Fetch historical data from Yahoo Finance.
        
        Args:
            symbol: Ticker symbol (e.g., "EURUSD=X" for forex)
            timeframe: Interval (1m, 5m, 15m, 1h, 1d, 1wk)
            period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max)
        """
        if not self._available:
            return pd.DataFrame()
            
        try:
            loop = asyncio.get_event_loop()
            
            def _fetch():
                ticker = self._yf.Ticker(symbol)
                return ticker.history(period=period, interval=timeframe)
                
            df = await loop.run_in_executor(None, _fetch)
            
            # Standardize columns
            df = df.rename(columns={
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume',
            })
            
            df['symbol'] = symbol
            return df[['open', 'high', 'low', 'close', 'volume', 'symbol']]
            
        except Exception as e:
            logger.error(f"Yahoo Finance fetch failed: {e}")
            return pd.DataFrame()


class DataAggregator:
    """
    Unified interface for fetching historical data from multiple sources.
    """
    
    def __init__(self, cache_dir: Path | str | None = None):
        self.binance = BinanceHistoricalFetcher(cache_dir)
        self.yahoo = YahooFinanceFetcher()
        
    async def fetch(
        self,
        symbol: str,
        timeframe: TimeFrame = "1h",
        days: int = 30,
        source: str = "auto",
    ) -> pd.DataFrame:
        """
        Fetch historical data from appropriate source.
        
        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            days: Number of days of history
            source: "binance", "yahoo", or "auto"
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        # Auto-detect source
        if source == "auto":
            symbol_upper = symbol.upper()
            if "USDT" in symbol_upper or "BTC" in symbol_upper or "ETH" in symbol_upper:
                source = "binance"
            else:
                source = "yahoo"
                
        if source == "binance":
            return await self.binance.get_with_cache(
                symbol, timeframe, start_time, end_time
            )
        elif source == "yahoo":
            # Map timeframe
            period_map = {7: "1wk", 30: "1mo", 90: "3mo", 365: "1y"}
            period = "1mo"
            for d, p in period_map.items():
                if days <= d:
                    period = p
                    break
            return await self.yahoo.fetch(symbol, timeframe, period)
        else:
            raise ValueError(f"Unknown source: {source}")


async def main():
    """Test data fetcher"""
    aggregator = DataAggregator()
    
    logger.info("Fetching BTC/USDT 1h data (30 days)...")
    df = await aggregator.fetch("BTCUSDT", "1h", days=30)
    
    if not df.empty:
        print(f"\n{'='*60}")
        print("HISTORICAL DATA")
        print("="*60)
        print(f"Symbol: {df['symbol'].iloc[0]}")
        print(f"Range: {df.index[0]} to {df.index[-1]}")
        print(f"Candles: {len(df)}")
        print(f"\nSample:")
        print(df.tail())
    else:
        print("No data fetched")


if __name__ == "__main__":
    asyncio.run(main())
