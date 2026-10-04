"""
RAG-based Market Memory
Stores market snapshots in vector database for historical precedent retrieval.

Query: "What happened when RSI was ~45 and Fear/Greed was ~27?"
Returns: Similar historical conditions with their outcomes.
"""
import json
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Optional
from loguru import logger

# Try to import Qdrant
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import VectorParams, Distance, PointStruct, Filter, FieldCondition, Range
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logger.warning("Qdrant not installed. Market memory will use JSON fallback.")


class MarketMemory:
    """
    RAG-based memory for historical market conditions.
    
    Stores market snapshots as vectors and retrieves similar historical
    conditions to inform trading decisions.
    """
    
    COLLECTION_NAME = "market_snapshots"
    VECTOR_DIM = 8  # Dimensions for market state vector
    PERSIST_PATH = Path(__file__).parent.parent.parent / "data" / "market_memory"
    FALLBACK_FILE = Path(__file__).parent.parent.parent / "data" / "market_memory.json"
    
    def __init__(self):
        self._client: Optional[QdrantClient] = None
        self._fallback_memory: list[dict] = []
        self._snapshot_count = 0
        self._init_storage()
    
    def _init_storage(self):
        """Initialize vector storage"""
        if QDRANT_AVAILABLE:
            try:
                # Use in-memory Qdrant to avoid lock conflicts when multiple processes run
                # JSON file (market_memory.json) is the true persistence layer
                # Qdrant is populated from JSON on startup for fast similarity search
                self._client = QdrantClient(":memory:")
                
                # Create collection
                self._client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self.VECTOR_DIM,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"📊 Created in-memory market memory collection: {self.COLLECTION_NAME}")
                    
            except Exception as e:
                logger.error(f"Failed to initialize Qdrant market memory: {e}")
                self._client = None
        
        # Load fallback memory
        self._load_fallback()
    
    def _load_fallback(self):
        """Load fallback JSON memory and migrate to in-memory Qdrant"""
        try:
            if self.FALLBACK_FILE.exists():
                with open(self.FALLBACK_FILE, "r") as f:
                    data = json.load(f)
                    self._fallback_memory = data.get("snapshots", [])
                    logger.info(f"📊 Loaded {len(self._fallback_memory)} snapshots from JSON")
                    
                    # Migrate to in-memory Qdrant for fast similarity search
                    if self._client and self._fallback_memory:
                        import hashlib
                        import uuid
                        migrated = 0
                        for snap in self._fallback_memory:
                            try:
                                vector = snap.get("vector")
                                if vector:
                                    # Create deterministic UUID from timestamp
                                    ts = snap.get("timestamp", "")
                                    hash_bytes = hashlib.md5(ts.encode()).digest()
                                    point_id = str(uuid.UUID(bytes=hash_bytes[:16]))
                                    
                                    self._client.upsert(
                                        collection_name=self.COLLECTION_NAME,
                                        points=[
                                            PointStruct(
                                                id=point_id,
                                                vector=vector,
                                                payload={k: v for k, v in snap.items() if k != "vector"},
                                            )
                                        ],
                                    )
                                    migrated += 1
                            except Exception:
                                pass
                        self._snapshot_count = migrated
                        if migrated:
                            logger.info(f"📊 Migrated {migrated} snapshots to in-memory Qdrant")
        except Exception as e:
            logger.warning(f"Failed to load fallback memory: {e}")
    
    def _save_fallback(self):
        """Save fallback JSON memory"""
        try:
            self.FALLBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.FALLBACK_FILE, "w") as f:
                json.dump({"snapshots": self._fallback_memory[-500:]}, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save fallback memory: {e}")
    
    def _create_vector(self, market_data: dict) -> list[float]:
        """
        Create a normalized vector from market data for similarity search.
        
        Vector dimensions:
        0: BTC price (normalized to 0-1 range, assuming 50k-150k range)
        1: RSI (0-100 normalized to 0-1)
        2: Fear & Greed (0-100 normalized to 0-1)
        3: Trend encoding (0=DOWN, 0.5=RANGE, 1=UP)
        4: EMA 20 distance (% from price)
        5: EMA 50 distance (% from price)
        6: Hour of day (0-1)
        7: Day of week (0-1)
        """
        btc = market_data.get("BTC", {})
        price = btc.get("price", 90000)
        rsi = btc.get("rsi_14", 50)
        fear_greed = market_data.get("fear_greed", {}).get("value", 50)
        trend = btc.get("trend", "RANGING")
        ema_20 = btc.get("ema_20", price)
        ema_50 = btc.get("ema_50", price)
        
        # Normalize values
        price_norm = max(0, min(1, (price - 50000) / 100000))  # 50k-150k range
        rsi_norm = rsi / 100.0
        fear_greed_norm = fear_greed / 100.0
        
        # Trend encoding
        trend_encoding = {
            "DOWNTREND": 0.0,
            "RANGING": 0.5,
            "UPTREND": 1.0,
        }.get(trend, 0.5)
        
        # EMA distances (% from price)
        ema_20_dist = ((price - ema_20) / price) * 10 + 0.5  # Scale to ~0-1
        ema_50_dist = ((price - ema_50) / price) * 10 + 0.5
        
        # Time features
        now = datetime.now()
        hour_norm = now.hour / 24.0
        day_norm = now.weekday() / 7.0
        
        return [
            price_norm,
            rsi_norm,
            fear_greed_norm,
            trend_encoding,
            max(0, min(1, ema_20_dist)),
            max(0, min(1, ema_50_dist)),
            hour_norm,
            day_norm,
        ]
    
    def store_snapshot(
        self,
        market_data: dict,
        decision: str,
        position_open: bool = False,
        agent_analyses: dict = None,
    ) -> str:
        """
        Store a market snapshot for future similarity search.
        
        Args:
            market_data: Current market state
            decision: What was decided (BUY, SELL, HOLD)
            position_open: Whether a position is currently open
            agent_analyses: Optional summary of agent analyses
            
        Returns:
            Snapshot ID (timestamp)
        """
        timestamp = datetime.now().isoformat()
        btc = market_data.get("BTC", {})
        
        snapshot = {
            "timestamp": timestamp,
            "btc_price": btc.get("price"),
            "rsi_14": btc.get("rsi_14"),
            "fear_greed": market_data.get("fear_greed", {}).get("value"),
            "trend": btc.get("trend"),
            "ema_20": btc.get("ema_20"),
            "ema_50": btc.get("ema_50"),
            "decision": decision,
            "position_open": position_open,
            "agent_summary": agent_analyses or {},
            "outcome_24h": None,  # To be filled later
            "outcome_pnl": None,
        }
        
        vector = self._create_vector(market_data)
        
        # Store in Qdrant
        if self._client:
            try:
                import hashlib
                import uuid
                # Create deterministic UUID from timestamp
                hash_bytes = hashlib.md5(timestamp.encode()).digest()
                point_id = str(uuid.UUID(bytes=hash_bytes[:16]))
                
                self._client.upsert(
                    collection_name=self.COLLECTION_NAME,
                    points=[
                        PointStruct(
                            id=point_id,
                            vector=vector,
                            payload=snapshot,
                        )
                    ],
                )
                self._snapshot_count += 1
                logger.debug(f"📊 Stored market snapshot #{self._snapshot_count}")
            except Exception as e:
                logger.error(f"Failed to store snapshot in Qdrant: {e}")
        
        # Also store in fallback
        snapshot["vector"] = vector
        self._fallback_memory.append(snapshot)
        self._save_fallback()
        
        return timestamp
    
    def query_similar(
        self,
        market_data: dict,
        limit: int = 5,
        min_age_hours: int = 1,
    ) -> list[dict]:
        """
        Find similar historical market conditions.
        
        Args:
            market_data: Current market state
            limit: Number of precedents to return
            min_age_hours: Minimum age of snapshots (to avoid too recent)
            
        Returns:
            List of similar historical snapshots with outcomes
        """
        vector = self._create_vector(market_data)
        results = []
        
        # Try Qdrant first
        if self._client and self._snapshot_count > 0:
            try:
                # Query for similar vectors using query_points (Qdrant v1.10+)
                search_result = self._client.query_points(
                    collection_name=self.COLLECTION_NAME,
                    query=vector,
                    limit=limit + 5,  # Get extra to filter
                )
                
                cutoff = datetime.now().timestamp() - (min_age_hours * 3600)
                
                # query_points returns QueryResponse with .points attribute
                points = search_result.points if hasattr(search_result, 'points') else search_result
                for hit in points:
                    payload = hit.payload
                    try:
                        ts = datetime.fromisoformat(payload.get("timestamp", "")).timestamp()
                        if ts < cutoff:
                            results.append({
                                **payload,
                                "similarity": hit.score,
                            })
                    except:
                        pass
                    
                    if len(results) >= limit:
                        break
                        
            except Exception as e:
                logger.warning(f"Qdrant query failed, using fallback: {e}")
        
        # Fallback to JSON-based search
        if not results and self._fallback_memory:
            # Simple cosine similarity
            def cosine_sim(v1, v2):
                v1, v2 = np.array(v1), np.array(v2)
                return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8)
            
            cutoff = datetime.now().timestamp() - (min_age_hours * 3600)
            scored = []
            
            for snap in self._fallback_memory:
                try:
                    ts = datetime.fromisoformat(snap.get("timestamp", "")).timestamp()
                    if ts < cutoff and snap.get("vector"):
                        sim = cosine_sim(vector, snap["vector"])
                        scored.append((sim, snap))
                except:
                    continue
            
            scored.sort(reverse=True, key=lambda x: x[0])
            for sim, snap in scored[:limit]:
                snap_copy = {k: v for k, v in snap.items() if k != "vector"}
                snap_copy["similarity"] = float(sim)
                results.append(snap_copy)
        
        return results
    
    def update_outcome(
        self,
        timestamp: str,
        pnl_percent: float,
        direction: str,
    ):
        """
        Update a snapshot with the outcome of the decision.
        
        Args:
            timestamp: Snapshot timestamp to update
            pnl_percent: PnL percentage from position
            direction: LONG or SHORT
        """
        outcome = {
            "pnl_percent": pnl_percent,
            "direction": direction,
            "profitable": pnl_percent > 0,
        }
        
        # Update fallback memory
        for snap in self._fallback_memory:
            if snap.get("timestamp") == timestamp:
                snap["outcome_pnl"] = pnl_percent
                snap["outcome_24h"] = "PROFIT" if pnl_percent > 0 else "LOSS"
                break
        
        self._save_fallback()
        
        # Note: Qdrant updates would require point ID lookup
        logger.debug(f"📊 Updated snapshot outcome: {pnl_percent:+.2f}%")
    
    def format_precedents(self, precedents: list[dict]) -> str:
        """Format precedents as context for agent prompts"""
        if not precedents:
            return ""
        
        lines = [
            "",
            "═" * 70,
            "📊 HISTORICAL PRECEDENTS (Similar Market Conditions)",
            "═" * 70,
        ]
        
        for i, p in enumerate(precedents[:5], 1):
            try:
                ts = datetime.fromisoformat(p.get("timestamp", ""))
                age = datetime.now() - ts
                if age.days > 0:
                    age_str = f"{age.days}d ago"
                else:
                    age_str = f"{age.seconds // 3600}h ago"
            except:
                age_str = "Unknown"
            
            sim = p.get("similarity", 0) * 100
            price = p.get("btc_price", 0)
            rsi = p.get("rsi_14", 0)
            fg = p.get("fear_greed", 0)
            trend = p.get("trend", "?")
            decision = p.get("decision", "?")
            outcome = p.get("outcome_pnl")
            
            outcome_str = f"{outcome:+.1f}%" if outcome else "Pending"
            emoji = "✅" if outcome and outcome > 0 else "❌" if outcome else "⏳"
            
            lines.append(f"""
{emoji} Precedent #{i} ({age_str}, {sim:.0f}% similar):
   BTC: ${price:,.0f} | RSI: {rsi:.0f} | Fear: {fg} | {trend}
   Decision: {decision} → Outcome: {outcome_str}
""")
        
        lines.append("═" * 70)
        lines.append("""
⚠️ USE HISTORICAL PRECEDENTS: Learn from similar past conditions.
   If similar conditions led to losses, consider alternative strategies.
""")
        lines.append("═" * 70)
        
        return "\n".join(lines)
    
    def reconcile_snapshots(self, current_btc_price: float) -> int:
        """
        Look-Back Loop: Tag old predictions with actual outcomes.
        
        Runs periodically to:
        1. Find snapshots > 24h old with no outcome
        2. Compare prediction vs actual price movement
        3. Tag as CORRECT/INCORRECT for RAG learning
        
        Args:
            current_btc_price: Current BTC price for comparison
            
        Returns:
            Number of snapshots reconciled
        """
        from datetime import timedelta
        
        if not current_btc_price or current_btc_price <= 0:
            return 0
            
        reconciled = 0
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        for snap in self._fallback_memory:
            # Skip if already reconciled or too recent
            if snap.get("reconciled"):
                continue
            if snap.get("outcome_24h") and snap.get("outcome_pnl") is not None:
                continue
                
            try:
                snap_time = datetime.fromisoformat(snap.get("timestamp", ""))
            except:
                continue
                
            if snap_time > cutoff_time:
                continue  # Too recent, wait for 24h
            
            # Calculate actual price change since snapshot
            snap_price = snap.get("btc_price", 0)
            if not snap_price or snap_price <= 0:
                continue
                
            price_change_pct = ((current_btc_price - snap_price) / snap_price) * 100
            
            # Evaluate prediction correctness
            # Note: PM decisions use OPEN/CLOSE/HOLD/MODIFY, not BUY/SELL
            decision = snap.get("decision", "HOLD").upper()
            
            # Map OPEN -> bullish (like BUY), CLOSE -> bearish (like SELL)
            if decision in ["BUY", "OPEN"]:
                # OPEN/BUY was correct if price went up >1%
                correct = price_change_pct > 1.0
            elif decision in ["SELL", "CLOSE"]:
                # CLOSE/SELL was correct if price went down >1%
                correct = price_change_pct < -1.0
            else:  # HOLD, MODIFY, or unknown
                # HOLD was correct if price stayed sideways (<3% move)
                correct = abs(price_change_pct) < 3.0
            
            # Tag the snapshot with outcome
            snap["outcome_24h"] = "CORRECT" if correct else "INCORRECT"
            snap["outcome_pnl"] = round(price_change_pct, 2)
            snap["reconciled"] = True
            snap["reconciled_at"] = datetime.now().isoformat()
            reconciled += 1
        
        if reconciled > 0:
            self._save_fallback()
            logger.info(f"📊 Look-Back: Reconciled {reconciled} snapshots with outcomes")
        
        return reconciled
    
    def get_stats(self) -> dict:
        """Get memory statistics"""
        # Count reconciled snapshots
        reconciled_count = sum(1 for s in self._fallback_memory if s.get("reconciled"))
        correct_count = sum(1 for s in self._fallback_memory if s.get("outcome_24h") == "CORRECT")
        
        return {
            "total_snapshots": self._snapshot_count + len(self._fallback_memory),
            "qdrant_count": self._snapshot_count,
            "fallback_count": len(self._fallback_memory),
            "qdrant_available": self._client is not None,
            "reconciled_count": reconciled_count,
            "correct_predictions": correct_count,
            "accuracy_pct": (correct_count / reconciled_count * 100) if reconciled_count > 0 else 0,
        }
    
    def prune_snapshots_quality(self, max_snapshots: int = 500) -> dict:
        """
        Quality-based pruning for market snapshots.
        
        Prioritizes keeping:
        1. Reconciled snapshots (have outcome data)
        2. Correct predictions (higher value for learning)
        3. Recent snapshots (more relevant)
        
        Args:
            max_snapshots: Maximum snapshots to keep
            
        Returns:
            Dict with pruning results
        """
        if len(self._fallback_memory) <= max_snapshots:
            return {"pruned": 0, "kept": len(self._fallback_memory)}
        
        # Score each snapshot
        scored = []
        for i, snap in enumerate(self._fallback_memory):
            score = 0
            
            # Reconciled = more valuable (has outcome data)
            if snap.get("reconciled"):
                score += 10
            
            # Correct predictions = higher value
            if snap.get("outcome_24h") == "CORRECT":
                score += 20
            elif snap.get("outcome_24h") == "INCORRECT":
                score += 5  # Still valuable for learning what NOT to do
            
            # Recent = slightly more relevant (recency bias)
            score += (i / len(self._fallback_memory)) * 5
            
            scored.append((score, i, snap))
        
        # Sort by score descending, keep top max_snapshots
        scored.sort(key=lambda x: x[0], reverse=True)
        kept_snapshots = [item[2] for item in scored[:max_snapshots]]
        
        # Preserve chronological order
        kept_snapshots.sort(key=lambda x: x.get("timestamp", ""))
        
        original_count = len(self._fallback_memory)
        self._fallback_memory = kept_snapshots
        self._save_fallback()
        
        pruned = original_count - len(self._fallback_memory)
        if pruned > 0:
            logger.info(f"📊 Market Memory: Pruned {pruned} low-value snapshots, kept {len(self._fallback_memory)}")
        
        return {"pruned": pruned, "kept": len(self._fallback_memory)}


# Singleton instance
_memory_instance = None

def get_market_memory() -> MarketMemory:
    """Get or create the market memory singleton"""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = MarketMemory()
    return _memory_instance
