"""
Sentiment Data Fetcher
The Autonomous Alpha - Social Sentiment Analysis

This module fetches and analyzes sentiment data from:
- Twitter/X API
- Reddit API
- Crypto Fear & Greed Index
- Funding rates and open interest
"""

import asyncio
import os
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger

try:
    import tweepy
    TWEEPY_AVAILABLE = True
except ImportError:
    TWEEPY_AVAILABLE = False

try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False


@dataclass
class SentimentData:
    """Aggregated sentiment data"""
    source: str
    symbol: str
    score: float  # -1.0 (bearish) to +1.0 (bullish)
    confidence: float  # 0.0 to 1.0
    volume: int  # Number of data points
    timestamp: datetime
    raw_data: dict | None = None


@dataclass
class FearGreedIndex:
    """Crypto Fear & Greed Index"""
    value: int  # 0-100
    classification: str  # "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
    timestamp: datetime


@dataclass
class FundingRate:
    """Perpetual futures funding rate"""
    symbol: str
    rate: float
    next_funding_time: datetime
    timestamp: datetime


class FearGreedFetcher:
    """
    Fetch Crypto Fear & Greed Index from Alternative.me API.
    Free, no API key required.
    """
    
    API_URL = "https://api.alternative.me/fng/"
    
    async def fetch(self, limit: int = 1) -> list[FearGreedIndex]:
        """Fetch Fear & Greed index"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.API_URL,
                    params={"limit": limit, "format": "json"},
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()
                
                results = []
                for item in data.get("data", []):
                    value = int(item["value"])
                    classification = item["value_classification"]
                    timestamp = datetime.fromtimestamp(int(item["timestamp"]))
                    
                    results.append(FearGreedIndex(
                        value=value,
                        classification=classification,
                        timestamp=timestamp,
                    ))
                    
                return results
                
        except Exception as e:
            logger.error(f"Failed to fetch Fear & Greed: {e}")
            return []
            
    def value_to_score(self, value: int) -> float:
        """Convert Fear & Greed value (0-100) to score (-1 to +1)"""
        # 0-25: Extreme Fear (-1 to -0.5)
        # 25-45: Fear (-0.5 to -0.1)
        # 45-55: Neutral (-0.1 to +0.1)
        # 55-75: Greed (+0.1 to +0.5)
        # 75-100: Extreme Greed (+0.5 to +1)
        return (value - 50) / 50


class BinanceFundingFetcher:
    """
    Fetch funding rates from Binance Futures API.
    Free, no API key required for public data.
    """
    
    API_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
    PREMIUM_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
    
    async def fetch_funding_rate(self, symbol: str = "BTCUSDT") -> FundingRate | None:
        """Fetch current funding rate"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.PREMIUM_URL,
                    params={"symbol": symbol},
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()
                
                return FundingRate(
                    symbol=symbol,
                    rate=float(data["lastFundingRate"]),
                    next_funding_time=datetime.fromtimestamp(
                        int(data["nextFundingTime"]) / 1000
                    ),
                    timestamp=datetime.now(),
                )
                
        except Exception as e:
            logger.error(f"Failed to fetch funding rate: {e}")
            return None
            
    async def fetch_open_interest(self, symbol: str = "BTCUSDT") -> dict | None:
        """Fetch open interest"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://fapi.binance.com/fapi/v1/openInterest",
                    params={"symbol": symbol},
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()
                
                return {
                    "symbol": symbol,
                    "open_interest": float(data["openInterest"]),
                    "timestamp": datetime.now(),
                }
                
        except Exception as e:
            logger.error(f"Failed to fetch open interest: {e}")
            return None
            
    def funding_to_sentiment(self, rate: float) -> float:
        """
        Convert funding rate to sentiment score.
        
        High positive funding = crowded long = potentially bearish
        High negative funding = crowded short = potentially bullish
        """
        # Typical funding range is -0.01% to +0.1%
        # We invert because crowded => contrarian signal
        return -rate * 100  # Scale and invert


class TwitterSentimentFetcher:
    """
    Fetch Twitter/X sentiment using the API.
    Requires API keys.
    """
    
    def __init__(
        self,
        bearer_token: str | None = None,
    ):
        self.bearer_token = bearer_token or os.getenv("TWITTER_BEARER_TOKEN")
        self._client = None
        
    def _init_client(self):
        """Initialize Twitter client"""
        if not TWEEPY_AVAILABLE:
            logger.warning("tweepy not installed")
            return
            
        if not self.bearer_token:
            logger.warning("Twitter bearer token not configured")
            return
            
        self._client = tweepy.Client(bearer_token=self.bearer_token)
        
    async def search_recent(
        self,
        query: str,
        max_results: int = 100,
    ) -> list[dict]:
        """Search recent tweets"""
        self._init_client()
        
        if not self._client:
            return []
            
        try:
            # Run in executor since tweepy is sync
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._client.search_recent_tweets(
                    query=query,
                    max_results=max_results,
                    tweet_fields=["created_at", "public_metrics", "author_id"],
                )
            )
            
            if not response.data:
                return []
                
            return [
                {
                    "text": tweet.text,
                    "created_at": tweet.created_at,
                    "metrics": tweet.public_metrics,
                }
                for tweet in response.data
            ]
            
        except Exception as e:
            logger.error(f"Twitter search failed: {e}")
            return []


class RedditSentimentFetcher:
    """
    Fetch Reddit sentiment from crypto subreddits.
    Requires API credentials.
    """
    
    SUBREDDITS = ["cryptocurrency", "bitcoin", "ethtrader", "CryptoMarkets"]
    
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ):
        self.client_id = client_id or os.getenv("REDDIT_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("REDDIT_CLIENT_SECRET")
        self._reddit = None
        
    def _init_client(self):
        """Initialize Reddit client"""
        if not PRAW_AVAILABLE:
            logger.warning("praw not installed")
            return
            
        if not self.client_id or not self.client_secret:
            logger.warning("Reddit credentials not configured")
            return
            
        self._reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent="AutonomousAlpha/1.0",
        )
        
    async def fetch_hot_posts(
        self,
        subreddit: str = "cryptocurrency",
        limit: int = 25,
    ) -> list[dict]:
        """Fetch hot posts from a subreddit"""
        self._init_client()
        
        if not self._reddit:
            return []
            
        try:
            loop = asyncio.get_event_loop()
            
            def get_posts():
                sub = self._reddit.subreddit(subreddit)
                return [
                    {
                        "title": post.title,
                        "score": post.score,
                        "num_comments": post.num_comments,
                        "created_utc": datetime.fromtimestamp(post.created_utc),
                        "url": post.url,
                    }
                    for post in sub.hot(limit=limit)
                ]
                
            return await loop.run_in_executor(None, get_posts)
            
        except Exception as e:
            logger.error(f"Reddit fetch failed: {e}")
            return []


class LiquidationFetcher:
    """
    Fetch liquidation data from various sources.
    """
    
    # Coinglass API (free tier available)
    COINGLASS_URL = "https://open-api.coinglass.com/public/v2/liquidation_chart"
    
    async def fetch_liquidation_heatmap(
        self,
        symbol: str = "BTC",
        interval: str = "h1",
    ) -> dict | None:
        """
        Fetch liquidation clusters/heatmap.
        Note: Coinglass API requires registration for full access.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.COINGLASS_URL,
                    params={
                        "symbol": symbol,
                        "interval": interval,
                    },
                    timeout=10.0,
                )
                
                if response.status_code == 200:
                    return response.json()
                    
        except Exception as e:
            logger.error(f"Liquidation fetch failed: {e}")
            
        return None


class SentimentAggregator:
    """
    Aggregates sentiment from multiple sources into a unified score.
    """
    
    def __init__(self):
        self.fear_greed = FearGreedFetcher()
        self.funding = BinanceFundingFetcher()
        self.twitter = TwitterSentimentFetcher()
        self.reddit = RedditSentimentFetcher()
        self.liquidations = LiquidationFetcher()
        
    async def get_aggregated_sentiment(
        self,
        symbol: str = "BTC",
    ) -> dict:
        """
        Get aggregated sentiment from all sources.
        """
        results = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "sources": {},
            "aggregate_score": 0.0,
            "aggregate_confidence": 0.0,
        }
        
        # Gather data from all sources concurrently
        fear_greed_task = self.fear_greed.fetch(limit=1)
        funding_task = self.funding.fetch_funding_rate(f"{symbol}USDT")
        oi_task = self.funding.fetch_open_interest(f"{symbol}USDT")
        
        fear_greed_data, funding_data, oi_data = await asyncio.gather(
            fear_greed_task,
            funding_task,
            oi_task,
            return_exceptions=True,
        )
        
        scores = []
        weights = []
        
        # Process Fear & Greed
        if fear_greed_data and not isinstance(fear_greed_data, Exception):
            if fear_greed_data:
                fg = fear_greed_data[0]
                score = self.fear_greed.value_to_score(fg.value)
                results["sources"]["fear_greed"] = {
                    "value": fg.value,
                    "classification": fg.classification,
                    "score": score,
                }
                scores.append(score)
                weights.append(0.3)  # 30% weight
                
        # Process Funding Rate
        if funding_data and not isinstance(funding_data, Exception):
            score = self.funding.funding_to_sentiment(funding_data.rate)
            results["sources"]["funding_rate"] = {
                "rate": funding_data.rate,
                "rate_percent": funding_data.rate * 100,
                "score": score,
                "interpretation": "crowded_long" if funding_data.rate > 0.0001 else "crowded_short" if funding_data.rate < -0.0001 else "neutral",
            }
            scores.append(score)
            weights.append(0.4)  # 40% weight - funding is very important
            
        # Process Open Interest
        if oi_data and not isinstance(oi_data, Exception):
            results["sources"]["open_interest"] = oi_data
            
        # Calculate weighted average
        if scores and weights:
            total_weight = sum(weights)
            results["aggregate_score"] = sum(
                s * w for s, w in zip(scores, weights)
            ) / total_weight
            results["aggregate_confidence"] = min(total_weight, 1.0)
            
        # Determine overall sentiment
        agg = results["aggregate_score"]
        if agg > 0.3:
            results["overall_sentiment"] = "BULLISH"
        elif agg > 0.1:
            results["overall_sentiment"] = "SLIGHTLY_BULLISH"
        elif agg < -0.3:
            results["overall_sentiment"] = "BEARISH"
        elif agg < -0.1:
            results["overall_sentiment"] = "SLIGHTLY_BEARISH"
        else:
            results["overall_sentiment"] = "NEUTRAL"
            
        return results


async def main():
    """Test sentiment fetchers"""
    aggregator = SentimentAggregator()
    
    logger.info("Fetching aggregated sentiment...")
    sentiment = await aggregator.get_aggregated_sentiment("BTC")
    
    print("\n" + "="*60)
    print("SENTIMENT ANALYSIS")
    print("="*60)
    
    for source, data in sentiment.get("sources", {}).items():
        print(f"\n{source.upper()}:")
        for key, value in data.items():
            print(f"  {key}: {value}")
            
    print(f"\n{'='*60}")
    print(f"AGGREGATE SCORE: {sentiment['aggregate_score']:.3f}")
    print(f"CONFIDENCE: {sentiment['aggregate_confidence']:.1%}")
    print(f"OVERALL: {sentiment.get('overall_sentiment', 'UNKNOWN')}")


if __name__ == "__main__":
    asyncio.run(main())
