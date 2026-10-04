"""
Real-Time Market Data Aggregator
The Autonomous Alpha - Live Data for Trading Decisions

Aggregates data from multiple sources:
- Binance REST API for prices, volume, funding rates
- Sentiment data (Fear & Greed, social signals)
- Technical indicators calculated from price data
- News headlines
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Any

import httpx
from loguru import logger


class RealTimeDataFetcher:
    """
    Fetches real-time market data from multiple sources.
    """
    
    # Binance public endpoints (no API key required)
    BINANCE_BASE = "https://api.binance.com"
    BINANCE_FUTURES = "https://fapi.binance.com"
    
    # Fear & Greed Index
    FEAR_GREED_URL = "https://api.alternative.me/fng/"
    
    # CoinGecko for market data
    COINGECKO_URL = "https://api.coingecko.com/api/v3"
    
    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        
    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=30.0)
        return self
        
    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
            
    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
        
    async def get_btc_price(self) -> dict:
        """Get BTC/USDT current price and 24h stats"""
        try:
            response = await self.client.get(
                f"{self.BINANCE_BASE}/api/v3/ticker/24hr",
                params={"symbol": "BTCUSDT"}
            )
            data = response.json()
            
            return {
                "price": float(data["lastPrice"]),
                "price_change_24h": float(data["priceChangePercent"]),
                "high_24h": float(data["highPrice"]),
                "low_24h": float(data["lowPrice"]),
                "volume_24h": float(data["volume"]),
                "volume_usdt_24h": float(data["quoteVolume"]),
            }
        except Exception as e:
            logger.error(f"Failed to fetch BTC price: {e}")
            return {}
            
    async def get_eth_price(self) -> dict:
        """Get ETH/USDT current price and 24h stats"""
        try:
            response = await self.client.get(
                f"{self.BINANCE_BASE}/api/v3/ticker/24hr",
                params={"symbol": "ETHUSDT"}
            )
            data = response.json()
            
            return {
                "price": float(data["lastPrice"]),
                "price_change_24h": float(data["priceChangePercent"]),
                "high_24h": float(data["highPrice"]),
                "low_24h": float(data["lowPrice"]),
                "volume_24h": float(data["volume"]),
            }
        except Exception as e:
            logger.error(f"Failed to fetch ETH price: {e}")
            return {}
            
    async def get_funding_rate(self, symbol: str = "BTCUSDT") -> dict:
        """Get current funding rate from Binance Futures"""
        try:
            response = await self.client.get(
                f"{self.BINANCE_FUTURES}/fapi/v1/fundingRate",
                params={"symbol": symbol, "limit": 1}
            )
            data = response.json()
            
            if data:
                rate = float(data[0]["fundingRate"])
                return {
                    "funding_rate": rate,
                    "funding_rate_pct": rate * 100,
                    "next_funding_time": data[0]["fundingTime"],
                    "signal": "CROWDED_LONG" if rate > 0.0001 else "CROWDED_SHORT" if rate < -0.0001 else "NEUTRAL"
                }
        except Exception as e:
            logger.error(f"Failed to fetch funding rate: {e}")
        return {}
        
    async def get_open_interest(self, symbol: str = "BTCUSDT") -> dict:
        """Get open interest from Binance Futures"""
        try:
            response = await self.client.get(
                f"{self.BINANCE_FUTURES}/fapi/v1/openInterest",
                params={"symbol": symbol}
            )
            data = response.json()
            
            return {
                "open_interest": float(data["openInterest"]),
                "symbol": symbol,
            }
        except Exception as e:
            logger.error(f"Failed to fetch open interest: {e}")
        return {}
    
    async def get_long_short_ratio(self, symbol: str = "BTCUSDT") -> dict:
        """Get global long/short account ratio from Binance Futures - KEY SENTIMENT INDICATOR"""
        try:
            response = await self.client.get(
                f"{self.BINANCE_FUTURES}/futures/data/globalLongShortAccountRatio",
                params={"symbol": symbol, "period": "1h", "limit": 1}
            )
            data = response.json()
            
            if data:
                ratio = float(data[0]["longShortRatio"])
                long_pct = float(data[0]["longAccount"]) * 100
                short_pct = float(data[0]["shortAccount"]) * 100
                
                # Interpret the signal
                if ratio > 2.0:
                    signal = "EXTREME_LONG"  # Very crowded long
                elif ratio > 1.3:
                    signal = "CROWDED_LONG"
                elif ratio < 0.5:
                    signal = "EXTREME_SHORT"  # Very crowded short
                elif ratio < 0.77:
                    signal = "CROWDED_SHORT"
                else:
                    signal = "BALANCED"
                
                return {
                    "long_short_ratio": ratio,
                    "long_account_pct": round(long_pct, 1),
                    "short_account_pct": round(short_pct, 1),
                    "signal": signal,
                    "contrarian_hint": "Fade longs" if signal in ["EXTREME_LONG", "CROWDED_LONG"] else "Fade shorts" if signal in ["EXTREME_SHORT", "CROWDED_SHORT"] else "No edge"
                }
        except Exception as e:
            logger.debug(f"Long/Short ratio fetch failed: {e}")
        return {}
    
    async def get_top_trader_positions(self, symbol: str = "BTCUSDT") -> dict:
        """Get top trader long/short position ratio - SMART MONEY INDICATOR"""
        try:
            response = await self.client.get(
                f"{self.BINANCE_FUTURES}/futures/data/topLongShortPositionRatio",
                params={"symbol": symbol, "period": "1h", "limit": 1}
            )
            data = response.json()
            
            if data:
                ratio = float(data[0]["longShortRatio"])
                long_pct = float(data[0]["longAccount"]) * 100
                short_pct = float(data[0]["shortAccount"]) * 100
                
                return {
                    "top_trader_ls_ratio": ratio,
                    "top_long_pct": round(long_pct, 1),
                    "top_short_pct": round(short_pct, 1),
                    "smart_money_bias": "LONG" if ratio > 1.2 else "SHORT" if ratio < 0.83 else "NEUTRAL"
                }
        except Exception as e:
            logger.debug(f"Top trader positions fetch failed: {e}")
        return {}
    
    async def get_recent_liquidations(self, symbol: str = "BTCUSDT") -> dict:
        """Estimate recent liquidations from force orders - CASCADE RISK INDICATOR"""
        try:
            # Get recent trades to estimate liquidation activity
            response = await self.client.get(
                f"{self.BINANCE_FUTURES}/fapi/v1/forceOrders",
                params={"symbol": symbol, "limit": 50}
            )
            data = response.json()
            
            if data:
                total_liq_usd = sum(float(order["price"]) * float(order["origQty"]) for order in data)
                long_liqs = sum(1 for order in data if order["side"] == "SELL")  # Long liquidations sell
                short_liqs = sum(1 for order in data if order["side"] == "BUY")  # Short liquidations buy
                
                return {
                    "recent_liquidations_count": len(data),
                    "estimated_liq_usd": round(total_liq_usd, 0),
                    "long_liquidations": long_liqs,
                    "short_liquidations": short_liqs,
                    "cascade_risk": "HIGH" if len(data) > 30 else "MEDIUM" if len(data) > 10 else "LOW"
                }
        except Exception as e:
            logger.debug(f"Liquidation data fetch failed (may need auth): {e}")
        return {}
    
    async def get_multi_timeframe_trend(self, symbol: str = "BTCUSDT") -> dict:
        """Fetch 4H and 1D timeframe trends for multi-timeframe confluence"""
        try:
            from src.utils.indicators import TechnicalAnalyzer
            import numpy as np
            
            # Fetch 4H data
            klines_4h = await self.get_klines(symbol, "4h", 100)
            # Fetch 1D data
            klines_1d = await self.get_klines(symbol, "1d", 100)
            
            result = {}
            
            if klines_4h:
                closes_4h = [k["close"] for k in klines_4h]
                highs_4h = [k["high"] for k in klines_4h]
                lows_4h = [k["low"] for k in klines_4h]
                volumes_4h = [k["volume"] for k in klines_4h]
                
                analyzer_4h = TechnicalAnalyzer(closes_4h, highs_4h, lows_4h, volumes_4h)
                indicators_4h = analyzer_4h.get_all()
                
                ema_20_4h = indicators_4h.get("ema_20")
                ema_50_4h = indicators_4h.get("ema_50")
                rsi_14_4h = indicators_4h.get("rsi_14")
                current_4h = closes_4h[-1]
                
                trend_4h = self._determine_trend(current_4h, ema_20_4h, ema_50_4h)
                
                result["timeframe_4h"] = {
                    "trend": trend_4h,
                    "rsi_14": round(rsi_14_4h, 1) if rsi_14_4h and not np.isnan(rsi_14_4h) else 50,
                    "ema_20": round(ema_20_4h, 2) if ema_20_4h and not np.isnan(ema_20_4h) else current_4h,
                    "ema_50": round(ema_50_4h, 2) if ema_50_4h and not np.isnan(ema_50_4h) else current_4h,
                }
            
            if klines_1d:
                closes_1d = [k["close"] for k in klines_1d]
                highs_1d = [k["high"] for k in klines_1d]
                lows_1d = [k["low"] for k in klines_1d]
                volumes_1d = [k["volume"] for k in klines_1d]
                
                analyzer_1d = TechnicalAnalyzer(closes_1d, highs_1d, lows_1d, volumes_1d)
                indicators_1d = analyzer_1d.get_all()
                
                ema_20_1d = indicators_1d.get("ema_20")
                ema_50_1d = indicators_1d.get("ema_50")
                rsi_14_1d = indicators_1d.get("rsi_14")
                current_1d = closes_1d[-1]
                
                trend_1d = self._determine_trend(current_1d, ema_20_1d, ema_50_1d)
                
                result["timeframe_1d"] = {
                    "trend": trend_1d,
                    "rsi_14": round(rsi_14_1d, 1) if rsi_14_1d and not np.isnan(rsi_14_1d) else 50,
                    "ema_20": round(ema_20_1d, 2) if ema_20_1d and not np.isnan(ema_20_1d) else current_1d,
                    "ema_50": round(ema_50_1d, 2) if ema_50_1d and not np.isnan(ema_50_1d) else current_1d,
                }
            
            # Determine multi-timeframe confluence
            trends = [result.get("timeframe_4h", {}).get("trend"), result.get("timeframe_1d", {}).get("trend")]
            if all(t == "UPTREND" for t in trends if t):
                result["mtf_confluence"] = "STRONG_BULLISH"
            elif all(t == "DOWNTREND" for t in trends if t):
                result["mtf_confluence"] = "STRONG_BEARISH"
            elif "UPTREND" in trends and "DOWNTREND" in trends:
                result["mtf_confluence"] = "CONFLICTING"
            else:
                result["mtf_confluence"] = "MIXED"
                
            return result
        except Exception as e:
            logger.debug(f"Multi-timeframe analysis failed: {e}")
        return {}

        
    async def get_fear_greed_index(self) -> dict:
        """Get Fear & Greed Index"""
        try:
            response = await self.client.get(self.FEAR_GREED_URL)
            data = response.json()
            
            if data.get("data"):
                fng = data["data"][0]
                value = int(fng["value"])
                
                return {
                    "value": value,
                    "classification": fng["value_classification"],
                    "timestamp": fng["timestamp"],
                    "signal": "EXTREME_FEAR" if value < 25 else "FEAR" if value < 45 else "NEUTRAL" if value < 55 else "GREED" if value < 75 else "EXTREME_GREED"
                }
        except Exception as e:
            logger.error(f"Failed to fetch Fear & Greed: {e}")
        return {}
        
    async def get_nvt_ratio(self, symbol: str = "BTCUSDT") -> dict:
        """
        Calculate NVT Ratio (Network Value to Transactions)
        Similar to P/E ratio for stocks - measures if price is justified by usage.
        
        NVT = Market Cap / Daily Transaction Volume (USD)
        - Low NVT (<20) = Undervalued
        - Medium NVT (20-50) = Fair value
        - High NVT (>50) = Overvalued / speculative
        """
        try:
            # Get 24h volume from ticker
            price_data = await self.get_btc_price() if symbol == "BTCUSDT" else await self.get_eth_price()
            
            if not price_data:
                return {}
            
            current_price = price_data.get("price", 0)
            volume_24h_usd = price_data.get("volume_24h", 0)
            
            # Approximate market cap (for simplicity, using volume as proxy for network value)
            # In production, would use actual circulating supply data
            # For BTC: ~19.6M circulating, for ETH: ~120M circulating
            circulating_supply = 19600000 if symbol == "BTCUSDT" else 120000000
            market_cap = current_price * circulating_supply
            
            # Calculate NVT
            if volume_24h_usd > 0:
                nvt = market_cap / volume_24h_usd
                
                # Classify valuation
                if nvt < 20:
                    signal = "UNDERVALUED"
                elif nvt < 50:
                    signal = "FAIR_VALUE"
                else:
                    signal = "OVERVALUED"
                
                return {
                    "nvt_ratio": round(nvt, 2),
                    "market_cap": market_cap,
                    "transaction_volume_24h": volume_24h_usd,
                    "valuation_signal": signal,
                    "interpretation": f"NVT {nvt:.1f}: Network value is {signal.lower().replace('_', ' ')} relative to usage"
                }
            
        except Exception as e:
            logger.error(f"Failed to calculate NVT ratio: {e}")
        
        return {}
    
    async def get_social_sentiment(self) -> dict:
        """
        Get basic social sentiment from free sources:
        - Google Trends (search interest)
        - Fear & Greed Index (already fetched)
        
        In Phase 2b, would add Reddit/Twitter APIs
        """
        try:
            # Use pytrends for Google Trends data
            from pytrends.request import TrendReq
            
            pytrends = TrendReq(hl='en-US', tz=360, timeout=(10,25))
            
            # Get interest over time for "bitcoin"
            pytrends.build_payload(['bitcoin'], cat=0, timeframe='now 7-d', geo='', gprop='')
            trends_data = pytrends.interest_over_time()
            
            if trends_data is not None and not trends_data.empty:
                # Get latest value and trend
                latest_interest = int(trends_data['bitcoin'].iloc[-1])
                avg_interest = trends_data['bitcoin'].mean()
                trend = "RISING" if latest_interest > avg_interest * 1.1 else "FALLING" if latest_interest < avg_interest * 0.9 else "STABLE"
                
                # Combine with Fear & Greed for overall sentiment score
                fg_data = await self.get_fear_greed_index()
                fg_value = fg_data.get("value", 50)
                
                # Normalize Google Trends (0-100) and F&G (0-100) to sentiment score (-1 to +1)
                google_score = (latest_interest - 50) / 50  # -1 to +1
                fg_score = (fg_value - 50) / 50  # -1 to +1
                
                # Average the two
                sentiment_score = (google_score + fg_score) / 2
                
                return {
                    "google_trends_index": latest_interest,
                    "google_trends_trend": trend,
                    "fear_greed_value": fg_value,
                    "combined_sentiment_score": round(sentiment_score, 3),  # -1 to +1
                    "sentiment_signal": "BULLISH" if sentiment_score > 0.2 else "BEARISH" if sentiment_score < -0.2 else "NEUTRAL",
                    "interpretation": f"Social sentiment: {sentiment_score:.2f} ({'bullish' if sentiment_score > 0 else 'bearish' if sentiment_score < 0 else 'neutral'})"
                }
            
        except ImportError:
            logger.warning("pytrends not installed - run: pip install pytrends")
        except Exception as e:
            logger.debug(f"Social sentiment unavailable: {e}")
        
        # Fallback: just use Fear & Greed
        fg_data = await self.get_fear_greed_index()
        fg_value = fg_data.get("value", 50)
        fg_score = (fg_value - 50) / 50
        
        return {
            "fear_greed_value": fg_value,
            "combined_sentiment_score": round(fg_score, 3),
            "sentiment_signal": "BULLISH" if fg_score > 0.2 else "BEARISH" if fg_score < -0.2 else "NEUTRAL",
            "source": "fear_greed_only"
        }
        
        
    async def get_klines(self, symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 500) -> list:
        """Get candlestick data for technical analysis - increased for comprehensive analysis"""
        try:
            response = await self.client.get(
                f"{self.BINANCE_BASE}/api/v3/klines",
                params={"symbol": symbol, "interval": interval, "limit": limit}
            )
            data = response.json()
            
            return [
                {
                    "timestamp": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                }
                for k in data
            ]
        except Exception as e:
            logger.error(f"Failed to fetch klines: {e}")
        return []
        
    def _determine_trend(self, current_price: float, ema_20: float | None, ema_50: float | None) -> str:
        """Determine market trend from EMAs"""
        if ema_20 is None or ema_50 is None:
            return "UNKNOWN"
        if current_price > ema_20 > ema_50:
            return "UPTREND"
        elif current_price < ema_20 < ema_50:
            return "DOWNTREND"
        else:
            return "RANGING"
        
    async def get_technical_indicators(self, symbol: str = "BTCUSDT") -> dict:
        """Calculate technical indicators using the unified indicators library"""
        from src.utils.indicators import TechnicalAnalyzer
        import numpy as np
        
        klines = await self.get_klines(symbol, "1h", 100)
        
        if not klines:
            return {}
        
        closes = [k["close"] for k in klines]
        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]
        volumes = [k["volume"] for k in klines]
        
        # Use the robust TechnicalAnalyzer from indicators.py
        analyzer = TechnicalAnalyzer(closes, highs, lows, volumes)
        indicators = analyzer.get_all()
        signal = analyzer.get_signal()
        
        current_price = closes[-1]
        
        # Extract MACD values (properly calculated with 9-period EMA signal)
        macd_data = indicators.get("macd")
        macd_line = macd_data.macd_line if macd_data and not np.isnan(macd_data.macd_line) else 0
        macd_signal = macd_data.signal_line if macd_data and not np.isnan(macd_data.signal_line) else 0
        macd_histogram = macd_data.histogram if macd_data and not np.isnan(macd_data.histogram) else 0
        
        # Extract other indicators
        rsi_7 = indicators.get("rsi_7")
        rsi_14 = indicators.get("rsi_14")
        ema_20 = indicators.get("ema_20")
        ema_50 = indicators.get("ema_50")
        atr_14 = indicators.get("atr_14")
        
        # Handle NaN values
        rsi_7 = round(rsi_7, 2) if rsi_7 and not np.isnan(rsi_7) else 50.0
        rsi_14 = round(rsi_14, 2) if rsi_14 and not np.isnan(rsi_14) else 50.0
        ema_20 = round(ema_20, 2) if ema_20 and not np.isnan(ema_20) else current_price
        ema_50 = round(ema_50, 2) if ema_50 and not np.isnan(ema_50) else current_price
        atr_14 = round(atr_14, 2) if atr_14 and not np.isnan(atr_14) else 0
        
        trend = self._determine_trend(current_price, ema_20, ema_50)
        
        # Extract Bollinger, OBV, CMF, Stochastic from indicators
        bollinger_data = indicators.get("bollinger")
        stochastic_data = indicators.get("stochastic")
        obv_val = indicators.get("obv")
        cmf_val = indicators.get("cmf")
        
        # Handle Bollinger Bands (namedtuple)
        bollinger_upper = bollinger_data.upper if bollinger_data and not np.isnan(bollinger_data.upper) else None
        bollinger_middle = bollinger_data.middle if bollinger_data and not np.isnan(bollinger_data.middle) else None
        bollinger_lower = bollinger_data.lower if bollinger_data and not np.isnan(bollinger_data.lower) else None
        bollinger_bandwidth = bollinger_data.bandwidth if bollinger_data and not np.isnan(bollinger_data.bandwidth) else None
        
        # Handle Stochastic (namedtuple)
        stoch_k = stochastic_data.k if stochastic_data and not np.isnan(stochastic_data.k) else 50.0
        stoch_d = stochastic_data.d if stochastic_data and not np.isnan(stochastic_data.d) else 50.0
        
        # Handle OBV and CMF
        obv_value = round(obv_val, 0) if obv_val and not np.isnan(obv_val) else 0
        cmf_value = round(cmf_val, 4) if cmf_val and not np.isnan(cmf_val) else 0.0
            
        return {
            "current_price": current_price,
            "rsi_7": rsi_7,
            "rsi_14": rsi_14,
            "ema_20": ema_20,
            "ema_50": ema_50,
            "macd": round(macd_line, 2),
            "macd_signal": round(macd_signal, 2),
            "macd_histogram": round(macd_histogram, 2),
            "atr_14": atr_14,
            "trend": trend,
            "technical_signal": signal,
            # NEW: Priority 1 Indicators - now actually returned!
            "bollinger": bollinger_data,  # Full namedtuple for realtime_fetcher.py to extract
            "bollinger_upper": round(bollinger_upper, 2) if bollinger_upper else None,
            "bollinger_middle": round(bollinger_middle, 2) if bollinger_middle else None,
            "bollinger_lower": round(bollinger_lower, 2) if bollinger_lower else None,
            "bollinger_bandwidth": round(bollinger_bandwidth, 4) if bollinger_bandwidth else None,
            "stochastic": stochastic_data,  # Full namedtuple
            "stochastic_k": round(stoch_k, 2),
            "stochastic_d": round(stoch_d, 2),
            "obv": obv_value,
            "cmf": cmf_value,
        }
        
    async def fetch_all(self, symbols: list[str] = ["BTC", "ETH"]) -> dict:
        """Fetch all market data for trading decision"""
        logger.info("📡 Fetching real-time market data...")
        
        # Fetch all data concurrently - including NEW data sources
        tasks = {
            "btc_price": self.get_btc_price(),
            "eth_price": self.get_eth_price(),
            "btc_funding": self.get_funding_rate("BTCUSDT"),
            "btc_oi": self.get_open_interest("BTCUSDT"),
            "fear_greed": self.get_fear_greed_index(),
            "btc_technicals": self.get_technical_indicators("BTCUSDT"),
            "eth_technicals": self.get_technical_indicators("ETHUSDT"),
            # NEW: Enhanced data sources for better agent analysis
            "long_short_ratio": self.get_long_short_ratio("BTCUSDT"),
            "top_traders": self.get_top_trader_positions("BTCUSDT"),
            "liquidations": self.get_recent_liquidations("BTCUSDT"),
            "mtf_btc": self.get_multi_timeframe_trend("BTCUSDT"),
            # PHASE 2a: Valuation & Sentiment
            "nvt_btc": self.get_nvt_ratio("BTCUSDT"),
            "social_sentiment": self.get_social_sentiment(),
        }
        
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        data = dict(zip(tasks.keys(), results))
        
        # Handle exceptions
        for key, value in data.items():
            if isinstance(value, Exception):
                logger.debug(f"Optional data {key} unavailable: {value}")
                data[key] = {}
                
        # Build structured market data
        btc_price = data.get("btc_price", {})
        eth_price = data.get("eth_price", {})
        btc_tech = data.get("btc_technicals", {})
        eth_tech = data.get("eth_technicals", {})
        mtf_data = data.get("mtf_btc", {})
        
        market_data = {
            "timestamp": datetime.now().isoformat(),
            "data_source": "binance_live",
            
            "BTC": {
                "price": btc_price.get("price", btc_tech.get("current_price", 0)),
                "price_change_24h": btc_price.get("price_change_24h", 0),
                "high_24h": btc_price.get("high_24h", 0),
                "low_24h": btc_price.get("low_24h", 0),
                "volume_24h": btc_price.get("volume_24h", 0),
                "rsi_7": btc_tech.get("rsi_7", 50),
                "rsi_14": btc_tech.get("rsi_14", 50),
                "ema_20": btc_tech.get("ema_20", 0),
                "ema_50": btc_tech.get("ema_50", 0),
                "macd": btc_tech.get("macd", 0),
                "trend": btc_tech.get("trend", "UNKNOWN"),
                "technical_signal": btc_tech.get("technical_signal", "NEUTRAL"),
                # NEW: Priority 1 Indicators for Professional Trading
                "bollinger_upper": btc_tech.get("bollinger").upper if btc_tech.get("bollinger") else None,
                "bollinger_middle": btc_tech.get("bollinger").middle if btc_tech.get("bollinger") else None,
                "bollinger_lower": btc_tech.get("bollinger").lower if btc_tech.get("bollinger") else None,
                "bollinger_bandwidth": btc_tech.get("bollinger").bandwidth if btc_tech.get("bollinger") else None,
                "obv": btc_tech.get("obv", 0),
                "cmf": btc_tech.get("cmf", 0),
                "stochastic_k": btc_tech.get("stochastic").k if btc_tech.get("stochastic") else 50,
                "stochastic_d": btc_tech.get("stochastic").d if btc_tech.get("stochastic") else 50,
                # Multi-timeframe data
                "trend_4h": mtf_data.get("timeframe_4h", {}).get("trend", "UNKNOWN"),
                "rsi_4h": mtf_data.get("timeframe_4h", {}).get("rsi_14", 50),
                "trend_1d": mtf_data.get("timeframe_1d", {}).get("trend", "UNKNOWN"),
                "rsi_1d": mtf_data.get("timeframe_1d", {}).get("rsi_14", 50),
                "mtf_confluence": mtf_data.get("mtf_confluence", "UNKNOWN"),
            },
            
            "ETH": {
                "price": eth_price.get("price", eth_tech.get("current_price", 0)),
                "price_change_24h": eth_price.get("price_change_24h", 0),
                "volume_24h": eth_price.get("volume_24h", 0),
                "rsi_7": eth_tech.get("rsi_7", 50),
                "rsi_14": eth_tech.get("rsi_14", 50),
                "trend": eth_tech.get("trend", "UNKNOWN"),
                "technical_signal": eth_tech.get("technical_signal", "NEUTRAL"),
            },
            
            "funding": data.get("btc_funding", {}),
            "open_interest": data.get("btc_oi", {}),
            "fear_greed": data.get("fear_greed", {}),
            
            # NEW: Enhanced sentiment/positioning data
            "long_short_ratio": data.get("long_short_ratio", {}),
            "top_traders": data.get("top_traders", {}),
            "liquidations": data.get("liquidations", {}),
            
            # PHASE 2a: Valuation & Social Sentiment
            "nvt_ratio": data.get("nvt_btc", {}),
            "social_sentiment": data.get("social_sentiment", {}),
        }
        
        # Enhanced logging
        ls_ratio = data.get("long_short_ratio", {})
        ls_signal = ls_ratio.get("signal", "N/A") if ls_ratio else "N/A"
        mtf_conf = mtf_data.get("mtf_confluence", "N/A")
        
        logger.info(f"📊 BTC: ${market_data['BTC']['price']:,.2f} | RSI: {market_data['BTC']['rsi_14']} | {market_data['BTC']['trend']} | L/S: {ls_signal} | MTF: {mtf_conf}")
        
        return market_data


async def main():
    """Test the real-time data fetcher"""
    async with RealTimeDataFetcher() as fetcher:
        data = await fetcher.fetch_all()
        
        print("\n" + "="*60)
        print("REAL-TIME MARKET DATA")
        print("="*60)
        
        print(f"\nBTC/USDT:")
        print(f"  Price: ${data['BTC']['price']:,.2f}")
        print(f"  Change 24h: {data['BTC']['price_change_24h']:+.2f}%")
        print(f"  RSI(14): {data['BTC']['rsi_14']}")
        print(f"  Trend: {data['BTC']['trend']}")
        print(f"  Signal: {data['BTC']['technical_signal']}")
        
        print(f"\nETH/USDT:")
        print(f"  Price: ${data['ETH']['price']:,.2f}")
        print(f"  RSI(14): {data['ETH']['rsi_14']}")
        
        print(f"\nSentiment:")
        print(f"  Fear & Greed: {data['fear_greed'].get('value', 'N/A')} ({data['fear_greed'].get('classification', 'N/A')})")
        print(f"  Funding Rate: {data['funding'].get('funding_rate_pct', 0):.4f}%")
        

if __name__ == "__main__":
    asyncio.run(main())
