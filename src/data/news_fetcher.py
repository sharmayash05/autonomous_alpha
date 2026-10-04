"""
News Data Fetcher
The Autonomous Alpha - Real-time News Integration

Fetches financial news for RAG-based trading decisions:
- CryptoPanic API (crypto news aggregator)
- Alpha Vantage News API (free tier)
- RSS feeds from major outlets
"""

import asyncio
import os
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Any
import xml.etree.ElementTree as ET

import httpx
from loguru import logger


@dataclass
class NewsArticle:
    """Single news article"""
    title: str
    source: str
    url: str
    published_at: datetime
    summary: str | None = None
    sentiment: str | None = None  # positive, negative, neutral
    symbols: list[str] | None = None
    importance: str = "medium"  # low, medium, high


class CryptoPanicFetcher:
    """
    Fetch news from CryptoPanic API.
    Free tier: 5 requests/minute
    """
    
    API_URL = "https://cryptopanic.com/api/v1/posts/"
    
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("CRYPTOPANIC_API_KEY")
        
    async def fetch(
        self,
        currencies: list[str] | None = None,
        filter_type: str = "hot",  # hot, rising, bullish, bearish, important
        limit: int = 100,  # Increased for comprehensive news coverage
    ) -> list[NewsArticle]:
        """Fetch latest crypto news"""
        if not self.api_key:
            logger.warning("CryptoPanic API key not configured")
            return []
            
        params = {
            "auth_token": self.api_key,
            "filter": filter_type,
        }
        
        if currencies:
            params["currencies"] = ",".join(currencies)
            
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.API_URL,
                    params=params,
                    timeout=15.0,
                )
                response.raise_for_status()
                data = response.json()
                
                articles = []
                for item in data.get("results", [])[:limit]:
                    articles.append(NewsArticle(
                        title=item.get("title", ""),
                        source=item.get("source", {}).get("title", "Unknown"),
                        url=item.get("url", ""),
                        published_at=datetime.fromisoformat(
                            item.get("published_at", "").replace("Z", "+00:00")
                        ) if item.get("published_at") else datetime.now(),
                        summary=None,
                        sentiment=item.get("votes", {}).get("sentiment"),
                        symbols=[c["code"] for c in item.get("currencies", [])],
                        importance="high" if item.get("kind") == "news" else "medium",
                    ))
                    
                return articles
                
        except Exception as e:
            logger.error(f"CryptoPanic fetch failed: {e}")
            return []


class AlphaVantageNewsFetcher:
    """
    Fetch news from Alpha Vantage API.
    Free tier: 25 requests/day
    """
    
    API_URL = "https://www.alphavantage.co/query"
    
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ALPHAVANTAGE_API_KEY")
        
    async def fetch(
        self,
        tickers: list[str] | None = None,
        topics: list[str] | None = None,
        limit: int = 200,  # Increased for comprehensive coverage
    ) -> list[NewsArticle]:
        """
        Fetch news articles.
        
        Args:
            tickers: Stock/crypto tickers (e.g., ["CRYPTO:BTC", "FOREX:EUR"])
            topics: Topics like "blockchain", "economy", "technology"
        """
        if not self.api_key:
            logger.warning("Alpha Vantage API key not configured")
            return []
            
        params = {
            "function": "NEWS_SENTIMENT",
            "apikey": self.api_key,
            "limit": limit,
        }
        
        if tickers:
            params["tickers"] = ",".join(tickers)
        if topics:
            params["topics"] = ",".join(topics)
            
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.API_URL,
                    params=params,
                    timeout=15.0,
                )
                response.raise_for_status()
                data = response.json()
                
                articles = []
                for item in data.get("feed", []):
                    # Determine sentiment from score
                    score = float(item.get("overall_sentiment_score", 0))
                    if score > 0.25:
                        sentiment = "positive"
                    elif score < -0.25:
                        sentiment = "negative"
                    else:
                        sentiment = "neutral"
                        
                    articles.append(NewsArticle(
                        title=item.get("title", ""),
                        source=item.get("source", "Unknown"),
                        url=item.get("url", ""),
                        published_at=datetime.strptime(
                            item.get("time_published", "")[:14],
                            "%Y%m%dT%H%M%S"
                        ) if item.get("time_published") else datetime.now(),
                        summary=item.get("summary"),
                        sentiment=sentiment,
                        symbols=[t["ticker"] for t in item.get("ticker_sentiment", [])],
                        importance="high" if abs(score) > 0.5 else "medium",
                    ))
                    
                return articles
                
        except Exception as e:
            logger.error(f"Alpha Vantage fetch failed: {e}")
            return []


class RSSFeedFetcher:
    """
    Fetch news from RSS feeds.
    No API key required.
    """
    
    DEFAULT_FEEDS = {
        "cointelegraph": "https://cointelegraph.com/rss",
        "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss",
        "decrypt": "https://decrypt.co/feed",
        "bitcoinist": "https://bitcoinist.com/feed/",
    }
    
    def __init__(self, feeds: dict[str, str] | None = None):
        self.feeds = feeds or self.DEFAULT_FEEDS
        
    async def fetch(self, feed_name: str | None = None, limit: int = 100) -> list[NewsArticle]:
        """Fetch news from RSS feeds"""
        feeds_to_check = (
            {feed_name: self.feeds[feed_name]}
            if feed_name and feed_name in self.feeds
            else self.feeds
        )
        
        all_articles = []
        
        async with httpx.AsyncClient() as client:
            for name, url in feeds_to_check.items():
                try:
                    response = await client.get(url, timeout=10.0)
                    response.raise_for_status()
                    
                    articles = self._parse_rss(response.text, name)
                    all_articles.extend(articles[:limit // len(feeds_to_check)])
                    
                except Exception as e:
                    logger.warning(f"RSS fetch failed for {name}: {e}")
                    
        # Sort by date
        all_articles.sort(key=lambda x: x.published_at, reverse=True)
        return all_articles[:limit]
        
    def _parse_rss(self, xml_content: str, source: str) -> list[NewsArticle]:
        """Parse RSS XML content"""
        articles = []
        
        try:
            root = ET.fromstring(xml_content)
            
            # Handle both RSS and Atom formats
            items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            
            for item in items:
                title = item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or ""
                link = item.findtext("link") or ""
                if not link:
                    link_elem = item.find("{http://www.w3.org/2005/Atom}link")
                    if link_elem is not None:
                        link = link_elem.get("href", "")
                        
                pub_date = item.findtext("pubDate") or item.findtext("{http://www.w3.org/2005/Atom}published")
                description = item.findtext("description") or item.findtext("{http://www.w3.org/2005/Atom}summary")
                
                # Parse date
                try:
                    if pub_date:
                        # Try common formats
                        for fmt in [
                            "%a, %d %b %Y %H:%M:%S %z",
                            "%a, %d %b %Y %H:%M:%S %Z",
                            "%Y-%m-%dT%H:%M:%S%z",
                        ]:
                            try:
                                published_at = datetime.strptime(pub_date.strip(), fmt)
                                break
                            except ValueError:
                                continue
                        else:
                            published_at = datetime.now()
                    else:
                        published_at = datetime.now()
                except Exception:
                    published_at = datetime.now()
                    
                articles.append(NewsArticle(
                    title=title.strip(),
                    source=source,
                    url=link.strip(),
                    published_at=published_at,
                    summary=description[:500] if description else None,
                    importance="medium",
                ))
                
        except ET.ParseError as e:
            logger.error(f"RSS parse error: {e}")
            
        return articles


class NewsAggregator:
    """
    Aggregates news from multiple sources for LLM analysis.
    """
    
    def __init__(self):
        self.cryptopanic = CryptoPanicFetcher()
        self.alphavantage = AlphaVantageNewsFetcher()
        self.rss = RSSFeedFetcher()
        
    async def fetch_all(
        self,
        symbols: list[str] | None = None,
        limit: int = 200,  # Increased for comprehensive news coverage
    ) -> list[NewsArticle]:
        """
        Fetch news from all sources.
        
        Args:
            symbols: Crypto symbols to filter by (e.g., ["BTC", "ETH"])
            limit: Max total articles
        """
        # Gather from all sources
        tasks = [
            self.rss.fetch(limit=limit // 2),  # RSS is free, get more
        ]
        
        # Add paid APIs if configured
        if self.cryptopanic.api_key:
            tasks.append(
                self.cryptopanic.fetch(currencies=symbols, limit=limit // 4)
            )
        if self.alphavantage.api_key:
            tickers = [f"CRYPTO:{s}" for s in (symbols or ["BTC"])]
            tasks.append(
                self.alphavantage.fetch(tickers=tickers, limit=limit // 4)
            )
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results
        all_articles = []
        for result in results:
            if isinstance(result, list):
                all_articles.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"News fetch error: {result}")
                
        # Deduplicate by title similarity
        seen_titles = set()
        unique_articles = []
        for article in all_articles:
            title_key = article.title.lower()[:50]
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_articles.append(article)
                
        # Sort by importance and date
        unique_articles.sort(
            key=lambda x: (
                0 if x.importance == "high" else 1,
                -x.published_at.timestamp()
            )
        )
        
        return unique_articles[:limit]
        
    def format_for_llm(self, articles: list[NewsArticle], max_chars: int = 100000) -> str:
        """Format news articles for LLM context - NO TRUNCATION with unlimited tokens"""
        if not articles:
            return "No recent news available."
            
        lines = ["RECENT NEWS:"]
        chars_used = len(lines[0])
        
        for article in articles:
            line = f"\n- [{article.source}] {article.title}"
            if article.sentiment:
                line += f" ({article.sentiment})"
            if article.symbols:
                line += f" [{'|'.join(article.symbols[:3])}]"
                
            if chars_used + len(line) > max_chars:
                lines.append("\n... (more news available)")
                break
                
            lines.append(line)
            chars_used += len(line)
            
        return "".join(lines)


async def main():
    """Test news fetchers"""
    aggregator = NewsAggregator()
    
    logger.info("Fetching news from all sources...")
    articles = await aggregator.fetch_all(symbols=["BTC", "ETH"], limit=20)
    
    print("\n" + "="*60)
    print("NEWS AGGREGATOR")
    print("="*60)
    
    for article in articles[:10]:
        print(f"\n[{article.importance.upper()}] {article.source}")
        print(f"  {article.title[:70]}...")
        print(f"  {article.published_at.strftime('%Y-%m-%d %H:%M')}")
        if article.sentiment:
            print(f"  Sentiment: {article.sentiment}")
            
    print("\n" + "="*60)
    print("LLM FORMAT:")
    print("="*60)
    print(aggregator.format_for_llm(articles))


if __name__ == "__main__":
    asyncio.run(main())
