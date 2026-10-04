"""
Domain-Specific Memory for Specialist Agents
The Autonomous Alpha - Pattern Memory for Experts

Provides lane-specific RAG so each specialist can learn from
similar patterns in their domain:
- Technical: RSI patterns, chart formations, EMA relationships
- Sentiment: Fear/Greed patterns, social sentiment correlations
- Fundamental: News events, whale movements, macro correlations

This solves the "Goldfish Expert" problem where specialists
analyze data without knowing how similar conditions played out.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import numpy as np

from loguru import logger

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import VectorParams, Distance, PointStruct
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False


class DomainMemory:
    """
    Domain-specific pattern memory for specialist agents.
    Each domain has its own Qdrant collection for targeted retrieval.
    """
    
    DOMAINS = ["technical", "sentiment", "fundamental"]
    PERSIST_PATH = Path(__file__).parent.parent.parent / "data" / "domain_memory"
    FALLBACK_FILE = Path(__file__).parent.parent.parent / "data" / "domain_patterns.json"
    VECTOR_DIM = 384  # MiniLM embedding dimension
    
    def __init__(self):
        self._client: Optional[QdrantClient] = None
        self._embedder: Optional[SentenceTransformer] = None
        self._fallback: dict = {d: [] for d in self.DOMAINS}
        self._init_storage()
        self._load_fallback()
    
    def _init_storage(self):
        """Initialize vector storage for each domain"""
        if QDRANT_AVAILABLE:
            try:
                # Use in-memory Qdrant to avoid lock conflicts
                # JSON file (domain_patterns.json) is the true source of persistence
                self._client = QdrantClient(":memory:")
                
                # Create collection for each domain
                collections = self._client.get_collections().collections
                existing = {c.name for c in collections}
                
                for domain in self.DOMAINS:
                    collection_name = f"patterns_{domain}"
                    if collection_name not in existing:
                        self._client.create_collection(
                            collection_name=collection_name,
                            vectors_config=VectorParams(
                                size=self.VECTOR_DIM,
                                distance=Distance.COSINE,
                            ),
                        )
                        logger.info(f"🧠 Created domain memory: {collection_name}")
                    else:
                        info = self._client.get_collection(collection_name)
                        logger.info(f"🧠 Loaded {collection_name}: {info.points_count} patterns")
                        
            except Exception as e:
                logger.error(f"Failed to initialize domain memory: {e}")
                self._client = None
        
        # Initialize embedder
        if EMBEDDINGS_AVAILABLE:
            try:
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("🧠 Domain memory embedder ready")
            except Exception as e:
                logger.warning(f"Failed to load embedder: {e}")
    
    def _load_fallback(self):
        """Load fallback JSON patterns"""
        try:
            if self.FALLBACK_FILE.exists():
                with open(self.FALLBACK_FILE, "r") as f:
                    self._fallback = json.load(f)
                    for domain in self.DOMAINS:
                        count = len(self._fallback.get(domain, []))
                        if count > 0:
                            logger.info(f"📂 Loaded {count} fallback patterns for {domain}")
        except Exception as e:
            logger.warning(f"Failed to load fallback patterns: {e}")
    
    def _save_fallback(self):
        """Save fallback JSON patterns"""
        try:
            self.FALLBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
            # Keep last 100 patterns per domain
            trimmed = {d: self._fallback[d][-100:] for d in self.DOMAINS}
            with open(self.FALLBACK_FILE, "w") as f:
                json.dump(trimmed, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save fallback patterns: {e}")
    
    def _get_embedding(self, text: str) -> list[float]:
        """Get embedding for text"""
        if self._embedder:
            return self._embedder.encode(text, convert_to_numpy=True).tolist()
        # Fallback: simple hash-based pseudo-embedding
        import hashlib
        hash_bytes = hashlib.sha384(text.encode()).digest()
        return [float(b) / 255.0 for b in hash_bytes]
    
    def store_pattern(
        self,
        domain: str,
        pattern_description: str,
        market_context: dict,
        outcome: dict,
    ) -> str:
        """
        Store a pattern in the appropriate domain lane.
        
        Args:
            domain: "technical", "sentiment", or "fundamental"
            pattern_description: Human-readable pattern description
            market_context: Market conditions when pattern occurred
            outcome: What happened (pnl_percent, price action, etc.)
            
        Returns:
            Pattern ID
        """
        if domain not in self.DOMAINS:
            logger.warning(f"Unknown domain: {domain}")
            return ""
        
        timestamp = datetime.now().isoformat()
        pattern_id = f"{domain}_{timestamp}"
        
        # Create searchable text
        search_text = self._create_search_text(domain, pattern_description, market_context)
        embedding = self._get_embedding(search_text)
        
        payload = {
            "pattern_id": pattern_id,
            "domain": domain,
            "description": pattern_description,
            "market_context": market_context,
            "outcome": outcome,
            "timestamp": timestamp,
            "search_text": search_text,
        }
        
        # Store in Qdrant
        if self._client:
            try:
                import hashlib
                import uuid
                hash_bytes = hashlib.md5(pattern_id.encode()).digest()
                point_id = str(uuid.UUID(bytes=hash_bytes[:16]))
                
                self._client.upsert(
                    collection_name=f"patterns_{domain}",
                    points=[
                        PointStruct(
                            id=point_id,
                            vector=embedding,
                            payload=payload,
                        )
                    ],
                )
                logger.debug(f"🧠 Stored {domain} pattern: {pattern_description[:50]}...")
            except Exception as e:
                logger.error(f"Failed to store pattern in Qdrant: {e}")
        
        # Store in fallback
        payload["embedding"] = embedding
        self._fallback[domain].append(payload)
        self._save_fallback()
        
        return pattern_id
    
    def _create_search_text(self, domain: str, description: str, context: dict) -> str:
        """Create searchable text from pattern data"""
        parts = [description]
        
        if domain == "technical":
            rsi = context.get("rsi", "")
            trend = context.get("trend", "")
            pattern = context.get("pattern", "")
            ema_position = context.get("ema_position", "")
            parts.extend([f"RSI {rsi}", trend, pattern, ema_position])
            
        elif domain == "sentiment":
            fear_greed = context.get("fear_greed", "")
            social = context.get("social_sentiment", "")
            news = context.get("news_tone", "")
            parts.extend([f"Fear/Greed {fear_greed}", social, news])
            
        elif domain == "fundamental":
            event = context.get("event", "")
            actor = context.get("actor", "")  # e.g., "MicroStrategy"
            event_type = context.get("event_type", "")  # e.g., "purchase"
            parts.extend([event, actor, event_type])
        
        return " | ".join(filter(None, parts))
    
    def recall_similar_patterns(
        self,
        domain: str,
        current_context: dict,
        limit: int = 5,
        min_score: float = 0.3,
    ) -> list[dict]:
        """
        Recall similar patterns from the specified domain.
        
        Args:
            domain: "technical", "sentiment", or "fundamental"
            current_context: Current market conditions to match against
            limit: Number of patterns to return
            min_score: Minimum similarity score
            
        Returns:
            List of similar historical patterns with outcomes
        """
        if domain not in self.DOMAINS:
            return []
        
        # Create search query from current context
        query_text = self._create_search_text(domain, "", current_context)
        if not query_text.strip(" |"):
            return []
            
        embedding = self._get_embedding(query_text)
        results = []
        
        # Try Qdrant first
        if self._client:
            try:
                search_result = self._client.query_points(
                    collection_name=f"patterns_{domain}",
                    query=embedding,
                    limit=limit + 5,
                    score_threshold=min_score,
                )
                
                points = search_result.points if hasattr(search_result, 'points') else search_result
                for hit in points:
                    results.append({
                        "score": hit.score,
                        **hit.payload,
                    })
                    if len(results) >= limit:
                        break
                        
            except Exception as e:
                logger.warning(f"Qdrant query failed for {domain}: {e}")
        
        # Fallback to JSON search
        if not results and self._fallback.get(domain):
            def cosine_sim(a, b):
                a, b = np.array(a), np.array(b)
                return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
            
            scored = []
            for pattern in self._fallback[domain]:
                if pattern.get("embedding"):
                    sim = cosine_sim(embedding, pattern["embedding"])
                    if sim >= min_score:
                        scored.append((sim, pattern))
            
            scored.sort(reverse=True, key=lambda x: x[0])
            for sim, pattern in scored[:limit]:
                pattern_copy = {k: v for k, v in pattern.items() if k != "embedding"}
                pattern_copy["score"] = sim
                results.append(pattern_copy)
        
        return results
    
    def format_patterns_for_prompt(self, patterns: list[dict], domain: str) -> str:
        """Format patterns as context for agent prompts"""
        if not patterns:
            return ""
        
        domain_emoji = {"technical": "📈", "sentiment": "💭", "fundamental": "📰"}
        emoji = domain_emoji.get(domain, "🧠")
        
        lines = [
            "",
            "═" * 70,
            f"{emoji} HISTORICAL PATTERNS (Similar {domain.upper()} Conditions)",
            "═" * 70,
        ]
        
        for i, p in enumerate(patterns[:5], 1):
            score = p.get("score", 0) * 100
            desc = p.get("description", "Unknown pattern")[:60]
            outcome = p.get("outcome", {})
            pnl = outcome.get("pnl_percent", 0)
            result = outcome.get("result", "Unknown")
            
            emoji_result = "✅" if pnl > 0 else "❌" if pnl < 0 else "➖"
            
            lines.append(f"{emoji_result} Pattern #{i} ({score:.0f}% similar):")
            lines.append(f"   {desc}")
            lines.append(f"   Outcome: {result} ({pnl:+.1f}%)")
            lines.append("")
        
        lines.extend([
            "═" * 70,
            f"⚠️ LEARN FROM HISTORY: Consider how similar patterns played out.",
            "═" * 70,
        ])
        
        return "\n".join(lines)
    
    def update_recent_pattern_outcomes(self, domain: str, pnl_percent: float, symbol: str = None) -> int:
        """
        Update recent pending patterns with actual outcome.
        
        Finds patterns in the last hour with pending outcomes and updates them.
        Called when a trade closes to link pattern predictions to actual results.
        
        Args:
            domain: Domain to update ("technical", "sentiment", "fundamental")
            pnl_percent: Actual PnL percent from closed trade
            symbol: Optional symbol to filter by
            
        Returns:
            Number of patterns updated
        """
        from datetime import timedelta
        
        if domain not in self.DOMAINS:
            return 0
            
        updated = 0
        cutoff_time = datetime.now() - timedelta(hours=1)
        
        for pattern in self._fallback.get(domain, []):
            # Skip if already has outcome
            outcome = pattern.get("outcome", {})
            if isinstance(outcome, dict) and not outcome.get("pending"):
                continue
                
            # Check recency
            try:
                pattern_time = datetime.fromisoformat(pattern.get("timestamp", ""))
                if pattern_time < cutoff_time:
                    continue
            except:
                continue
            
            # Update outcome
            pattern["outcome"] = {
                "pnl_percent": pnl_percent,
                "result": "PROFIT" if pnl_percent > 0 else "LOSS",
                "pending": False,
                "updated_at": datetime.now().isoformat(),
            }
            updated += 1
        
        if updated > 0:
            self._save_fallback()
            logger.debug(f"🧠 Updated {updated} {domain} pattern outcomes with {pnl_percent:+.1f}%")
        
        return updated
    
    def get_stats(self) -> dict:
        """Get memory statistics - uses fallback file which persists across restarts"""
        stats = {}
        for domain in self.DOMAINS:
            # Always use fallback counts - Qdrant is in-memory only and resets on restart
            # The _fallback dict is loaded from domain_patterns.json at startup
            count = len(self._fallback.get(domain, []))
            stats[domain] = count
        return stats
    
    async def prune_patterns_intelligent(self, llm_client, max_per_domain: int = 100) -> dict:
        """
        Intelligently prune domain patterns using LLM quality scoring.
        
        Uses LLM to evaluate pattern usefulness and removes:
        - Low-quality or vague patterns
        - Patterns with poor predictive value
        - Duplicate or redundant patterns
        
        Args:
            llm_client: LLM client for quality scoring
            max_per_domain: Maximum patterns per domain
            
        Returns:
            Dict with pruning results per domain
        """
        results = {}
        
        for domain in self.DOMAINS:
            patterns = self._fallback.get(domain, [])
            
            if len(patterns) <= max_per_domain:
                results[domain] = {"pruned": 0, "kept": len(patterns)}
                continue
            
            # Build pattern summary for LLM
            pattern_summaries = []
            for i, p in enumerate(patterns[:150]):  # Limit for context window
                desc = p.get("description", "")[:80]
                outcome = p.get("outcome", {})
                pnl = outcome.get("pnl_percent", 0) if isinstance(outcome, dict) else 0
                pattern_summaries.append(f"{i+1}. {desc} | PnL: {pnl:+.1f}%")
            
            prompt = f"""You are the Pattern Quality Analyst for a trading system.

DOMAIN: {domain.upper()}
PATTERNS ({len(patterns)} total, max allowed: {max_per_domain}):
{chr(10).join(pattern_summaries)}

Score each pattern 1-10:
- 10: Highly specific, actionable with clear outcome correlation
- 7-9: Good predictive value
- 4-6: Marginal usefulness
- 1-3: Vague, redundant, or poor predictive value

Keep TOP {max_per_domain} highest-scoring patterns.

OUTPUT JSON:
{{
  "kept_indices": [1, 2, 5, ...],
  "reasoning": "Brief explanation"
}}"""

            try:
                response = await llm_client.generate(
                    prompt=prompt,
                    temperature=0.2,
                    max_tokens=4096,
                    json_mode=True,
                )
                
                import json
                result = json.loads(response.content)
                kept_indices = set((i - 1) for i in result.get("kept_indices", []))
                
                if not kept_indices:
                    kept_indices = set(range(len(patterns) - max_per_domain, len(patterns)))
                
                original_count = len(patterns)
                self._fallback[domain] = [p for i, p in enumerate(patterns) if i in kept_indices]
                pruned_count = original_count - len(self._fallback[domain])
                
                results[domain] = {"pruned": pruned_count, "kept": len(self._fallback[domain])}
                
                if pruned_count > 0:
                    logger.info(f"🧹 {domain}: Pruned {pruned_count} low-quality patterns, kept {len(self._fallback[domain])}")
                    
            except Exception as e:
                logger.debug(f"LLM pattern pruning failed for {domain}: {e}")
                # Fallback to FIFO
                if len(patterns) > max_per_domain:
                    self._fallback[domain] = patterns[-max_per_domain:]
                results[domain] = {"pruned": 0, "kept": len(self._fallback.get(domain, []))}
        
        self._save_fallback()
        return results
    
    def prune_stale_patterns(self, max_age_days: int = 30, max_per_domain: int = 100) -> dict:
        """
        Prune stale patterns to keep memory efficient.
        
        Removes:
        - Patterns older than max_age_days
        - Patterns with consistently negative outcomes
        - Excess patterns beyond max_per_domain (keeps most recent)
        
        Args:
            max_age_days: Maximum age for patterns (default 30)
            max_per_domain: Maximum patterns per domain (default 100)
            
        Returns:
            Dict with pruning results per domain
        """
        from datetime import timedelta
        
        cutoff_time = datetime.now() - timedelta(days=max_age_days)
        results = {}
        
        for domain in self.DOMAINS:
            original_count = len(self._fallback.get(domain, []))
            pruned_count = 0
            
            if original_count == 0:
                results[domain] = {"pruned": 0, "kept": 0}
                continue
            
            # Filter patterns
            kept_patterns = []
            pruned_ids = []
            
            for pattern in self._fallback.get(domain, []):
                try:
                    pattern_time = datetime.fromisoformat(pattern.get("timestamp", ""))
                except:
                    pattern_time = datetime.now()  # Keep if can't parse
                
                outcome = pattern.get("outcome", {})
                pnl = outcome.get("pnl_percent", 0) if isinstance(outcome, dict) else 0
                
                # Prune if: too old OR consistently bad AND has been reconciled
                is_old = pattern_time < cutoff_time
                is_reconciled = outcome.get("reconciled", False) if isinstance(outcome, dict) else False
                is_bad = pnl < -5 and is_reconciled  # Significantly negative and confirmed
                
                if is_old or is_bad:
                    pruned_ids.append(pattern.get("id", ""))
                    pruned_count += 1
                else:
                    kept_patterns.append(pattern)
            
            # Enforce max limit (keep most recent)
            if len(kept_patterns) > max_per_domain:
                excess = len(kept_patterns) - max_per_domain
                pruned_count += excess
                kept_patterns = kept_patterns[-max_per_domain:]
            
            # Update fallback memory
            self._fallback[domain] = kept_patterns
            
            # Prune from Qdrant if available
            if self._client and pruned_ids:
                try:
                    collection_name = f"patterns_{domain}"
                    valid_ids = [pid for pid in pruned_ids if pid]
                    if valid_ids:
                        self._client.delete(
                            collection_name=collection_name,
                            points_selector=valid_ids,
                        )
                except Exception as e:
                    logger.debug(f"Failed to prune {domain} from Qdrant: {e}")
            
            results[domain] = {"pruned": pruned_count, "kept": len(kept_patterns)}
            
            if pruned_count > 0:
                logger.info(f"🧹 {domain}: Pruned {pruned_count} stale patterns, kept {len(kept_patterns)}")
        
        # Save updated fallback
        self._save_fallback()
        
        return results


# Singleton instance
_domain_memory_instance = None

def get_domain_memory() -> DomainMemory:
    """Get or create the domain memory singleton"""
    global _domain_memory_instance
    if _domain_memory_instance is None:
        _domain_memory_instance = DomainMemory()
    return _domain_memory_instance
