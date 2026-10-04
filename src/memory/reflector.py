"""
Reflexion Memory System
The Autonomous Alpha - Self-Correcting Learning Loop

This module implements the Reflexion pattern:
- Trade post-mortem analysis
- Lesson extraction and embedding
- Vector database storage (Qdrant)
- Similar experience retrieval
"""

import asyncio
import json
import hashlib
from datetime import datetime
from typing import Any
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger
from pydantic import BaseModel

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import VectorParams, Distance, PointStruct
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logger.warning("Qdrant not installed. Using in-memory fallback for lessons.")

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logger.warning("sentence-transformers not installed. RAG features disabled.")


@dataclass
class TradeRecord:
    """Record of a completed trade"""
    trade_id: str
    symbol: str
    direction: str  # LONG or SHORT
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    pnl_dollars: float
    pnl_percent: float
    original_thesis: str
    market_context_entry: dict
    market_context_exit: dict
    leverage: int = 1
    stop_loss: float | None = None
    take_profit: float | None = None


class TradeReflection(BaseModel):
    """Reflection on a completed trade"""
    trade_id: str
    trade_grade: str  # A, B, C, D, F
    thesis_flaw: str | None
    missed_signals: list[str]
    lesson_learned: str
    embedding_text: str
    timestamp: str
    pnl_percent: float


class ReflectorAgent:
    """
    Agent that conducts post-mortem analysis on trades.
    Extracts lessons learned for future retrieval.
    """
    
    REFLECTION_PROMPT = """
You are the REFLECTOR AGENT - an elite trade analyst conducting comprehensive post-mortem analysis.
Your role is to extract every possible learning from completed trades to improve future performance.

═══════════════════════════════════════════════════════════════════════════════
TRADE DATA
═══════════════════════════════════════════════════════════════════════════════
- Trade ID: {trade_id}
- Symbol: {symbol}
- Direction: {direction}
- Entry: ${entry_price} at {entry_time}
- Exit: ${exit_price} at {exit_time}
- P&L: ${pnl_dollars} ({pnl_percent}%)
- Leverage: {leverage}x
- Stop Loss: {stop_loss}
- Take Profit: {take_profit}

═══════════════════════════════════════════════════════════════════════════════
ORIGINAL THESIS
═══════════════════════════════════════════════════════════════════════════════
{original_thesis}

═══════════════════════════════════════════════════════════════════════════════
MARKET CONDITIONS AT ENTRY
═══════════════════════════════════════════════════════════════════════════════
{market_context_entry}

═══════════════════════════════════════════════════════════════════════════════
MARKET CONDITIONS AT EXIT
═══════════════════════════════════════════════════════════════════════════════
{market_context_exit}

═══════════════════════════════════════════════════════════════════════════════
COMPREHENSIVE ANALYSIS FRAMEWORK
═══════════════════════════════════════════════════════════════════════════════

### 1. THESIS EVALUATION
- Was the original thesis correct or flawed from the start?
- Did the thesis correctly identify the market regime?
- Were the key assumptions validated or invalidated?
- Was the thesis-to-execution translation accurate?

### 2. TIMING ANALYSIS
- Was entry timing optimal, early, or late?
- Did we enter at a good price relative to key levels?
- Was exit timing optimal, early, or late?
- Did we leave money on the table or exit at a good point?
- How did our timing compare to ideal execution?

### 3. SIGNAL ANALYSIS
- What signals supported the trade that we correctly identified?
- What signals did we miss that would have improved the trade?
- What signals did we misinterpret?
- Were there warning signs of failure we ignored?
- What confluence of signals was present or missing?

### 4. RISK MANAGEMENT EVALUATION
- Was position sizing appropriate for the setup quality?
- Was stop loss placement optimal (too tight, too loose)?
- Was take profit realistic and based on key levels?
- Did we manage risk-reward ratio correctly?
- Did leverage amplify or hurt the outcome?

### 5. MARKET REGIME ANALYSIS
- What was the actual market regime during the trade?
- Did our strategy fit the regime?
- How did macro factors affect the outcome?
- Were there external events that impacted the trade?

### 6. EXECUTION QUALITY
- Did slippage affect the outcome?
- Did we adhere to our trading plan?
- Were there emotional deviations from the plan?
- Was the execution mechanically sound?

### 7. COUNTERFACTUAL ANALYSIS
- What would have happened with different entry timing?
- What would have happened with different stop placement?
- What would have happened with different position sizing?
- What was the optimal execution in hindsight?

### 8. PATTERN RECOGNITION
- Does this trade fit patterns we've seen before?
- What similar setups have we traded?
- What distinguishes winning vs losing instances of this setup?
- Is this a repeatable edge or one-off situation?

═══════════════════════════════════════════════════════════════════════════════
OUTPUT FORMAT (JSON)
═══════════════════════════════════════════════════════════════════════════════

{{
  "trade_grade": "A|B|C|D|F",
  "grade_breakdown": {{
    "thesis_quality": "A|B|C|D|F",
    "timing_quality": "A|B|C|D|F", 
    "risk_management": "A|B|C|D|F",
    "execution_quality": "A|B|C|D|F"
  }},
  "thesis_evaluation": {{
    "thesis_was_correct": true|false,
    "thesis_flaw": "Description of what was wrong (null if thesis was correct)",
    "key_assumption_validated": true|false,
    "assumption_details": "Which assumptions held or failed"
  }},
  "timing_analysis": {{
    "entry_timing": "optimal|early|late",
    "entry_timing_cost": "+/-X% vs optimal",
    "exit_timing": "optimal|early|late",
    "exit_timing_cost": "+/-X% vs optimal"
  }},
  "signals": {{
    "correctly_identified": ["signal1", "signal2"],
    "missed_signals": ["signal1", "signal2"],
    "misinterpreted_signals": ["signal1", "signal2"],
    "ignored_warnings": ["warning1", "warning2"]
  }},
  "risk_management_assessment": {{
    "position_size": "appropriate|too_large|too_small",
    "stop_loss": "appropriate|too_tight|too_loose",
    "take_profit": "appropriate|too_aggressive|too_conservative",
    "risk_reward_achieved": "X:1"
  }},
  "lessons": {{
    "primary_lesson": "The most important actionable insight from this trade",
    "secondary_lessons": ["Additional insight 1", "Additional insight 2"],
    "what_to_repeat": "What we did right that should be repeated",
    "what_to_avoid": "What we did wrong that should be avoided"
  }},
  "counterfactual": {{
    "optimal_entry": 0.0,
    "optimal_exit": 0.0,
    "optimal_pnl_pct": "+/-X%",
    "improvement_opportunity": "+/-X%"
  }},
  "pattern_match": {{
    "setup_type": "Description of the setup pattern",
    "historical_win_rate": "If known",
    "distinguishing_factors": "What made this instance win/lose"
  }},
  "embedding_text": "A comprehensive, searchable description of this trade setup, market conditions, outcome, and lessons for future RAG retrieval. Include key indicators, market regime, entry/exit quality, and the primary lesson learned.",
  "actionable_improvements": [
    "Specific actionable improvement for future trades"
  ],
  "confidence_in_analysis": 0.0-1.0
}}

═══════════════════════════════════════════════════════════════════════════════
GRADING RUBRIC
═══════════════════════════════════════════════════════════════════════════════

A = Excellent execution of a sound thesis. Would repeat exactly.
B = Good trade with minor improvements possible. Solid risk-adjusted return.
C = Acceptable trade. Some mistakes but not fundamentally flawed.
D = Poor trade. Multiple errors in thesis, timing, or execution.
F = Failed trade. Fundamental mistakes or rule violations. Must learn from this.

REMEMBER: Every trade, win or lose, contains information. Extract all of it.
"""
    
    def __init__(self, llm_client):
        self.llm = llm_client
        
    async def reflect(self, trade: TradeRecord) -> TradeReflection:
        """
        Conduct post-mortem analysis on a trade.
        
        Args:
            trade: The completed trade record
            
        Returns:
            TradeReflection with lessons learned
        """
        prompt = self.REFLECTION_PROMPT.format(
            trade_id=trade.trade_id,
            symbol=trade.symbol,
            direction=trade.direction,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            entry_time=trade.entry_time.isoformat(),
            exit_time=trade.exit_time.isoformat(),
            pnl_dollars=trade.pnl_dollars,
            pnl_percent=f"{trade.pnl_percent:.2f}%",
            leverage=trade.leverage,
            stop_loss=trade.stop_loss or "Not set",
            take_profit=trade.take_profit or "Not set",
            original_thesis=trade.original_thesis,
            market_context_entry=json.dumps(trade.market_context_entry, indent=2),
            market_context_exit=json.dumps(trade.market_context_exit, indent=2),
        )
        
        response = await self.llm.generate(
            prompt=prompt,
            temperature=0.3,
            max_tokens=16384,  # Unlimited for deep analysis
            json_mode=True,  # ROOT FIX: Force JSON output
        )
        
        # DEBUG: Log what we actually received
        logger.info(f"🔍 Reflection LLM response length: {len(response.content)} chars")
        if len(response.content) < 50:
            logger.warning(f"⚠️ Very short reflection response: '{response.content}'")
        
        try:
            # Extract JSON from potential markdown code blocks
            content = response.content.strip()
            if content.startswith("```"):
                # Remove markdown code block wrapper
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]  # Remove opening ```json or ```
                if lines[-1].strip() == "```":
                    lines = lines[:-1]  # Remove closing ```
                content = "\n".join(lines)
            
            data = json.loads(content)
            
            # Handle nested lesson structure from detailed reflections
            lessons = data.get("lessons", {})
            lesson_learned = lessons.get("primary_lesson") if isinstance(lessons, dict) else data.get("lesson_learned", "No lesson extracted")
            
            return TradeReflection(
                trade_id=trade.trade_id,
                trade_grade=data.get("trade_grade", "C"),
                thesis_flaw=data.get("thesis_evaluation", {}).get("thesis_flaw") or data.get("thesis_flaw"),
                missed_signals=data.get("signals", {}).get("missed_signals", []) or data.get("missed_signals", []),
                lesson_learned=lesson_learned,
                embedding_text=data.get("embedding_text", ""),
                timestamp=datetime.now().isoformat(),
                pnl_percent=trade.pnl_percent,
            )
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed, extracting lesson from text: {e}")
            # Try to extract meaningful lesson from non-JSON response
            content = response.content if hasattr(response, 'content') else str(response)
            
            # Generate a smart fallback lesson based on trade outcome
            if trade.pnl_percent > 0:
                outcome = "profitable"
                emoji = "✅"
            else:
                outcome = "losing"
                emoji = "❌"
            
            # Extract any useful text from response (first 200 chars)
            lesson_text = content[:200].replace('\n', ' ').strip() if content else ""
            
            # Create a meaningful lesson based on trade data
            if trade.pnl_percent > 5:
                lesson = f"Strong {trade.direction} on {trade.symbol}: +{trade.pnl_percent:.1f}%. Entry thesis was validated."
            elif trade.pnl_percent > 0:
                lesson = f"Modest win on {trade.direction} {trade.symbol}: +{trade.pnl_percent:.1f}%. Consider larger position sizing."
            elif trade.pnl_percent > -3:
                lesson = f"Small loss on {trade.direction} {trade.symbol}: {trade.pnl_percent:.1f}%. Stop loss worked as intended."
            else:
                lesson = f"Significant loss on {trade.direction} {trade.symbol}: {trade.pnl_percent:.1f}%. Review entry thesis and timing."
            
            return TradeReflection(
                trade_id=trade.trade_id,
                trade_grade="B" if trade.pnl_percent > 0 else "C",
                thesis_flaw=f"LLM analysis unavailable. Trade was {outcome}.",
                missed_signals=[lesson_text[:100]] if lesson_text else [],
                lesson_learned=lesson,
                embedding_text=f"{trade.symbol} {trade.direction} trade with {trade.pnl_percent:.2f}% result",
                timestamp=datetime.now().isoformat(),
                pnl_percent=trade.pnl_percent,
            )


class TradingMemory:
    """
    Vector database for storing and retrieving trade lessons.
    Uses Qdrant for efficient similarity search with JSON file fallback.
    """
    
    COLLECTION_NAME = "trade_lessons"
    LESSONS_FILE = Path(__file__).parent.parent.parent / "data" / "lessons.json"
    
    def __init__(
        self,
        persist_path: Path | None = None,
        embedding_model: str = "all-MiniLM-L6-v2",
    ):
        self.persist_path = persist_path
        self._embedder: Any = None
        self._client: Any = None
        self._fallback_memory: list[dict] = []  # Fallback if Qdrant unavailable
        
        # Load existing lessons from file
        self._load_lessons_from_file()
        
        if EMBEDDINGS_AVAILABLE:
            try:
                self._embedder = SentenceTransformer(embedding_model)
                logger.info(f"Loaded embedding model: {embedding_model}")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                
        self._init_db()
    
    def _load_lessons_from_file(self):
        """Load lessons from JSON file on startup"""
        try:
            if self.LESSONS_FILE.exists():
                with open(self.LESSONS_FILE, "r") as f:
                    data = json.load(f)
                    self._fallback_memory = data.get("lessons", [])
                    logger.info(f"📚 Loaded {len(self._fallback_memory)} lessons from file")
        except Exception as e:
            logger.error(f"Failed to load lessons file: {e}")
            self._fallback_memory = []
    
    def _save_lessons_to_file(self):
        """Persist lessons to JSON file"""
        try:
            self.LESSONS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.LESSONS_FILE, "w") as f:
                json.dump({"lessons": self._fallback_memory}, f, indent=2, default=str)
            logger.debug(f"💾 Saved {len(self._fallback_memory)} lessons to file")
        except Exception as e:
            logger.error(f"Failed to save lessons file: {e}")
        
    def _init_db(self):
        """Initialize or connect to vector database"""
        if not QDRANT_AVAILABLE:
            logger.warning("Using in-memory fallback for trade lessons")
            return
            
        try:
            # Use in-memory Qdrant to avoid lock conflicts
            # JSON file (lessons.json) is the true source of persistence
            # Qdrant is populated from JSON on startup for fast similarity search
            self._client = QdrantClient(":memory:")
                
            # Create collection if it doesn't exist
            collections = self._client.get_collections().collections
            if not any(c.name == self.COLLECTION_NAME for c in collections):
                self._client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=384 if self._embedder else 1536,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"Created collection: {self.COLLECTION_NAME}")
                
                # Load existing lessons from file into Qdrant
                if self._fallback_memory:
                    logger.info(f"📚 Migrating {len(self._fallback_memory)} lessons from file to Qdrant...")
                    for lesson in self._fallback_memory:
                        try:
                            embedding = lesson.get("embedding", [])
                            if not embedding and self._embedder:
                                text = lesson.get("payload", {}).get("embedding_text", "")
                                embedding = self._get_embedding(text)
                            
                            if embedding:
                                self._client.upsert(
                                    collection_name=self.COLLECTION_NAME,
                                    points=[
                                        PointStruct(
                                            id=lesson.get("id", str(hash(str(lesson)))),
                                            vector=embedding,
                                            payload=lesson.get("payload", {}),
                                        )
                                    ],
                                )
                        except Exception as e:
                            logger.debug(f"Failed to migrate lesson: {e}")
                    logger.info("✅ Migration complete")
            else:
                info = self._client.get_collection(self.COLLECTION_NAME)
                logger.info(f"📚 Loaded Qdrant lessons: {info.points_count} entries")
                
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant: {e}")
            self._client = None
            
    def _get_embedding(self, text: str) -> list[float]:
        """Get embedding for text"""
        if self._embedder:
            return self._embedder.encode(text).tolist()
        # Fallback: simple hash-based pseudo-embedding (not for production)
        import hashlib
        hash_bytes = hashlib.sha384(text.encode()).digest()
        return [b / 255.0 for b in hash_bytes]
        
    def store_lesson(self, reflection: TradeReflection) -> bool:
        """
        Store a trade reflection in the memory.
        
        Args:
            reflection: The reflection to store
            
        Returns:
            True if stored successfully
        """
        embedding = self._get_embedding(reflection.embedding_text)
        
        # ========== SEMANTIC DEDUPLICATION ==========
        # Check if a similar lesson already exists to avoid duplicates
        SIMILARITY_THRESHOLD = 0.80  # 80% word overlap = duplicate
        
        new_words = set(reflection.lesson_learned.lower().split())
        
        for existing in self._fallback_memory:
            existing_payload = existing.get("payload", {})
            existing_lesson = existing_payload.get("lesson_learned", "")
            old_words = set(existing_lesson.lower().split())
            
            if len(new_words) > 3 and len(old_words) > 3:  # Skip very short lessons
                overlap = len(new_words & old_words)
                max_len = max(len(new_words), len(old_words))
                similarity = overlap / max_len if max_len > 0 else 0
                
                if similarity > SIMILARITY_THRESHOLD:
                    # Check if new lesson has higher PnL impact (more painful = more memorable)
                    existing_pnl = abs(existing_payload.get("pnl_percent", 0))
                    new_pnl = abs(reflection.pnl_percent)
                    
                    if new_pnl > existing_pnl:
                        # New lesson is more impactful, update existing
                        existing_payload["lesson_learned"] = reflection.lesson_learned
                        existing_payload["pnl_percent"] = reflection.pnl_percent
                        existing_payload["trade_grade"] = reflection.trade_grade
                        existing_payload["timestamp"] = reflection.timestamp
                        self._save_lessons_to_file()
                        logger.info(f"🔄 Updated existing lesson with more impactful version ({similarity:.0%} similar, {new_pnl:.1f}% > {existing_pnl:.1f}%)")
                    else:
                        logger.info(f"🔄 Skipping duplicate lesson ({similarity:.0%} similar to existing)")
                    return True  # Don't store duplicate
        
        # Generate a valid UUID from hash
        import uuid
        hash_bytes = hashlib.md5(
            f"{reflection.trade_id}_{reflection.timestamp}".encode()
        ).digest()
        point_id = str(uuid.UUID(bytes=hash_bytes))
        
        payload = {
            "trade_id": reflection.trade_id,
            "trade_grade": reflection.trade_grade,
            "thesis_flaw": reflection.thesis_flaw,
            "missed_signals": reflection.missed_signals,
            "lesson_learned": reflection.lesson_learned,
            "embedding_text": reflection.embedding_text,
            "timestamp": reflection.timestamp,
            "pnl_percent": reflection.pnl_percent,
        }
        
        if self._client:
            try:
                self._client.upsert(
                    collection_name=self.COLLECTION_NAME,
                    points=[
                        PointStruct(
                            id=point_id,
                            vector=embedding,
                            payload=payload,
                        )
                    ],
                )
                logger.info(f"Stored lesson for trade {reflection.trade_id} in Qdrant")
            except Exception as e:
                logger.error(f"Failed to store lesson in Qdrant: {e}")
        
        # ALWAYS persist to in-memory + file (for dashboard and survival across restarts)
        self._fallback_memory.append({
            "id": point_id,
            "embedding": embedding.tolist() if hasattr(embedding, 'tolist') else embedding,
            "payload": payload,
        })
        
        # Always persist to file for dashboard display and survival across restarts
        self._save_lessons_to_file()
        logger.info(f"📚 Saved lesson for trade {reflection.trade_id} to JSON file")
        return True
        
    def recall_similar(
        self,
        query: str,
        top_k: int = 50,  # Maximum for unlimited budget
        min_score: float = 0.2,  # Lower threshold for more lessons
    ) -> list[dict]:
        """
        Retrieve similar past lessons.
        
        Args:
            query: Description of current setup/situation
            top_k: Number of results to return
            min_score: Minimum similarity score
            
        Returns:
            List of similar past lessons
        """
        embedding = self._get_embedding(query)
        
        if self._client:
            try:
                # Use query_points for newer qdrant-client versions
                results = self._client.query_points(
                    collection_name=self.COLLECTION_NAME,
                    query=embedding,
                    limit=top_k,
                    score_threshold=min_score,
                )
                return [
                    {
                        "score": r.score,
                        **r.payload,
                    }
                    for r in results.points
                ]
            except Exception as e:
                logger.error(f"Failed to search: {e}")
                
        # Fallback: simple cosine similarity
        def cosine_sim(a: list[float], b: list[float]) -> float:
            dot = sum(x*y for x, y in zip(a, b))
            norm_a = sum(x*x for x in a) ** 0.5
            norm_b = sum(x*x for x in b) ** 0.5
            return dot / (norm_a * norm_b) if norm_a and norm_b else 0
            
        scored = [
            (cosine_sim(embedding, m["embedding"]), m["payload"])
            for m in self._fallback_memory
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        
        return [
            {"score": score, **payload}
            for score, payload in scored[:top_k]
            if score >= min_score
        ]
        
    def get_stats(self) -> dict:
        """Get memory statistics"""
        if self._client:
            try:
                info = self._client.get_collection(self.COLLECTION_NAME)
                return {
                    "total_lessons": info.points_count,
                    "backend": "qdrant",
                }
            except:
                pass
                
        return {
            "total_lessons": len(self._fallback_memory),
            "backend": "in-memory",
        }
    
    async def prune_lessons(self, llm_client, max_lessons: int = 50) -> dict:
        """
        Intelligently prune low-quality lessons to keep the system efficient.
        
        Uses LLM to score lessons and removes:
        - Vague or unhelpful lessons ("Reflection failed", generic advice)
        - Contradictory lessons (keep the more recent one)
        - Duplicate lessons (keep highest quality)
        
        Args:
            llm_client: LLM client for quality scoring
            max_lessons: Maximum lessons to keep (default 50)
            
        Returns:
            Dict with pruning results
        """
        if len(self._fallback_memory) <= max_lessons:
            logger.debug(f"📚 No pruning needed: {len(self._fallback_memory)} <= {max_lessons}")
            return {"pruned": 0, "kept": len(self._fallback_memory)}
        
        # Get all lessons with their content
        lessons_text = []
        for i, lesson in enumerate(self._fallback_memory):
            payload = lesson.get("payload", {})
            lessons_text.append({
                "index": i,
                "id": lesson.get("id", ""),
                "lesson": payload.get("lesson_learned", ""),
                "grade": payload.get("trade_grade", "?"),
                "pnl": payload.get("pnl_percent", 0),
                "timestamp": payload.get("timestamp", ""),
            })
        
        prompt = f"""You are the Memory Curator for an autonomous trading system.

CURRENT LESSONS ({len(lessons_text)} total, max allowed: {max_lessons}):
{chr(10).join(f'{l["index"]+1}. [{l["grade"]}] {l["pnl"]:+.1f}%: {l["lesson"][:100]}' for l in lessons_text)}

YOUR TASK:
Score each lesson 1-10 for quality and usefulness:
- 10: Highly specific, actionable insight with clear market conditions
- 7-9: Good lesson with some actionable value  
- 4-6: Generic advice, somewhat useful
- 1-3: Vague, "Reflection failed", or contradicts other lessons

Keep the TOP {max_lessons} highest-scoring lessons. Prune the rest.

OUTPUT JSON:
{{
  "kept_indices": [1, 2, 5, ...],  // 1-indexed list of lessons to KEEP
  "pruned_indices": [3, 4, ...],   // 1-indexed list of lessons to PRUNE
  "reasoning": "Brief explanation of pruning decisions"
}}"""

        try:
            response = await llm_client.generate(
                prompt=prompt,
                temperature=0.2,
                max_tokens=4096,
                json_mode=True,
            )
            
            result = json.loads(response.content)
            
            # Get indices to keep (convert from 1-indexed to 0-indexed)
            kept_indices = set((i - 1) for i in result.get("kept_indices", []))
            
            # If LLM returned empty, keep most recent
            if not kept_indices:
                kept_indices = set(range(len(self._fallback_memory) - max_lessons, len(self._fallback_memory)))
            
            # Count how many we're pruning
            original_count = len(self._fallback_memory)
            
            # Keep only the selected lessons (in fallback memory)
            self._fallback_memory = [
                lesson for i, lesson in enumerate(self._fallback_memory) 
                if i in kept_indices
            ]
            
            # Save to file
            self._save_lessons_to_file()
            
            # Prune from Qdrant (if available)
            if self._client:
                try:
                    pruned_ids = [
                        lessons_text[i]["id"] 
                        for i in range(original_count) 
                        if i not in kept_indices and lessons_text[i]["id"]
                    ]
                    if pruned_ids:
                        self._client.delete(
                            collection_name=self.COLLECTION_NAME,
                            points_selector=pruned_ids,
                        )
                except Exception as e:
                    logger.warning(f"Failed to prune from Qdrant: {e}")
            
            pruned_count = original_count - len(self._fallback_memory)
            logger.info(f"🧹 Pruned {pruned_count} low-quality lessons, kept {len(self._fallback_memory)}")
            
            return {
                "pruned": pruned_count,
                "kept": len(self._fallback_memory),
                "reasoning": result.get("reasoning", ""),
            }
            
        except Exception as e:
            logger.error(f"Lesson pruning failed: {e}")
            # Fallback: keep most recent lessons
            if len(self._fallback_memory) > max_lessons:
                self._fallback_memory = self._fallback_memory[-max_lessons:]
                self._save_lessons_to_file()
            return {"pruned": 0, "kept": len(self._fallback_memory), "error": str(e)}
    
    def recall_domain_lessons(
        self,
        domain: str,
        context_query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Recall lessons filtered by domain for specialist agents.
        
        This enables specialists to self-correct by seeing their own past mistakes.
        
        Args:
            domain: "technical", "sentiment", or "fundamental"
            context_query: Current market context description
            top_k: Number of lessons to return
            
        Returns:
            List of domain-relevant lessons
        """
        # Domain-specific keywords to filter lessons
        domain_keywords = {
            "technical": [
                "rsi", "ema", "sma", "macd", "pattern", "double top", "double bottom",
                "support", "resistance", "breakout", "breakdown", "trend", "divergence",
                "overbought", "oversold", "momentum", "volume", "chart", "candle"
            ],
            "sentiment": [
                "fear", "greed", "sentiment", "social", "twitter", "reddit", "news",
                "fud", "fomo", "panic", "euphoria", "crowd", "retail", "whale"
            ],
            "fundamental": [
                "microstrategy", "etf", "institutional", "adoption", "regulation",
                "halving", "supply", "demand", "macro", "fed", "interest", "inflation",
                "accumulation", "distribution", "whale", "inflow", "outflow"
            ],
        }
        
        keywords = domain_keywords.get(domain, [])
        if not keywords:
            return []
        
        # Get all lessons first
        all_lessons = self.recall_similar(context_query, top_k=50, min_score=0.1)
        
        # Filter by domain keywords
        domain_lessons = []
        for lesson in all_lessons:
            lesson_text = str(lesson).lower()
            relevance_score = sum(1 for kw in keywords if kw in lesson_text)
            if relevance_score > 0:
                lesson["domain_relevance"] = relevance_score
                domain_lessons.append(lesson)
        
        # Sort by domain relevance, then by similarity score
        domain_lessons.sort(key=lambda x: (x.get("domain_relevance", 0), x.get("score", 0)), reverse=True)
        
        return domain_lessons[:top_k]
    
    def format_domain_lessons_for_prompt(self, lessons: list[dict], domain: str) -> str:
        """Format domain lessons for specialist agent prompts"""
        if not lessons:
            return ""
        
        emoji_map = {"technical": "📈", "sentiment": "💭", "fundamental": "📰"}
        emoji = emoji_map.get(domain, "📚")
        
        lines = [
            "",
            "═" * 70,
            f"{emoji} YOUR PAST {domain.upper()} LESSONS (Learn From Your Mistakes)",
            "═" * 70,
        ]
        
        for i, lesson in enumerate(lessons[:5], 1):
            text = lesson.get("lesson_learned", lesson.get("lessons", {}).get("primary_lesson", "N/A"))[:100]
            pnl = lesson.get("pnl_percent", 0)
            emoji_result = "✅" if pnl > 0 else "❌"
            lines.append(f"{emoji_result} Lesson #{i}: {text}")
            lines.append(f"   Outcome: {pnl:+.1f}%")
            lines.append("")
        
        lines.extend([
            "═" * 70,
            "⚠️ SELF-CORRECT: If you've made similar calls that failed, downgrade your signal!",
            "═" * 70,
        ])
        
        return "\n".join(lines)


class ReflexionLoop:
    """
    Complete Reflexion loop for self-improvement.
    
    1. Trade executes → Observe outcome
    2. Reflector Agent analyzes → Generates lesson
    3. Lesson stored in Memory → Vector embedding
    4. Before new trades → Retrieve relevant lessons
    5. Lessons influence decision → Better trades
    """
    
    def __init__(
        self,
        llm_client,
        memory: TradingMemory | None = None,
    ):
        self.reflector = ReflectorAgent(llm_client)
        self.memory = memory or TradingMemory()
        
    async def process_completed_trade(self, trade: TradeRecord) -> TradeReflection:
        """
        Process a completed trade through the Reflexion loop.
        
        Args:
            trade: The completed trade
            
        Returns:
            The reflection with lessons learned
        """
        logger.info(f"🔍 Reflecting on trade {trade.trade_id}...")
        
        # Generate reflection
        reflection = await self.reflector.reflect(trade)
        
        # Store in memory
        self.memory.store_lesson(reflection)
        
        # Log the lesson (full text, no truncation)
        emoji = "✅" if trade.pnl_percent > 0 else "❌"
        logger.info(
            f"{emoji} Trade {trade.trade_id}: {trade.pnl_percent:.2f}% | "
            f"Grade: {reflection.trade_grade} | "
            f"Lesson: {reflection.lesson_learned}"
        )
        
        return reflection
        
    def get_relevant_lessons(
        self,
        current_setup: str,
        top_k: int = 50,  # Maximum for unlimited budget
    ) -> list[dict]:
        """
        Retrieve relevant lessons for the current trading setup.
        
        Args:
            current_setup: Description of current market setup
            top_k: Number of lessons to retrieve
            
        Returns:
            List of relevant past lessons
        """
        lessons = self.memory.recall_similar(current_setup, top_k=top_k)
        
        if lessons:
            logger.info(f"📚 Retrieved {len(lessons)} relevant lessons")
            for i, lesson in enumerate(lessons, 1):
                logger.debug(
                    f"  {i}. [Score: {lesson['score']:.2f}] "
                    f"{lesson.get('lesson_learned', lesson.get('lessons', {}).get('primary_lesson', 'N/A'))}"
                )
                
        return lessons


# Singleton instance for global access
_reflexion_loop_instance = None

def get_reflexion_loop():
    """Get or create the ReflexionLoop singleton (without LLM for memory-only access)"""
    global _reflexion_loop_instance
    if _reflexion_loop_instance is None:
        # Create a minimal instance for memory access only
        _reflexion_loop_instance = ReflexionLoop.__new__(ReflexionLoop)
        _reflexion_loop_instance.reflector = None
        _reflexion_loop_instance.memory = TradingMemory()
    return _reflexion_loop_instance

def set_reflexion_loop(instance):
    """Set the global ReflexionLoop instance (called from main.py)"""
    global _reflexion_loop_instance
    _reflexion_loop_instance = instance


async def main():
    """Test the Reflexion system"""
    from .llm_client import LLMClient
    
    # Create a sample trade
    trade = TradeRecord(
        trade_id="TEST-001",
        symbol="BTC",
        direction="LONG",
        entry_price=105000.0,
        exit_price=103000.0,
        entry_time=datetime(2026, 1, 10, 10, 0),
        exit_time=datetime(2026, 1, 10, 14, 0),
        pnl_dollars=-200.0,
        pnl_percent=-1.9,
        leverage=10,
        stop_loss=102000.0,
        take_profit=110000.0,
        original_thesis="RSI oversold bounce with EMA support",
        market_context_entry={
            "rsi_7": 32.5,
            "ema_20": 104500.0,
            "volume": "above_average",
        },
        market_context_exit={
            "rsi_7": 28.0,
            "ema_20": 103800.0,
            "volume": "very_high",
        },
    )
    
    async with LLMClient() as client:
        loop = ReflexionLoop(client)
        
        # Process the trade
        reflection = await loop.process_completed_trade(trade)
        
        print("\n" + "="*60)
        print("TRADE REFLECTION")
        print("="*60)
        print(f"Grade: {reflection.trade_grade}")
        print(f"Thesis Flaw: {reflection.thesis_flaw}")
        print(f"Missed Signals: {reflection.missed_signals}")
        print(f"Lesson: {reflection.lesson_learned}")
        
        # Test retrieval
        print("\n" + "="*60)
        print("RETRIEVING SIMILAR LESSONS")
        print("="*60)
        lessons = loop.get_relevant_lessons(
            "BTC LONG with RSI oversold at EMA support"
        )
        for lesson in lessons:
            print(f"  - {lesson['lesson_learned']}")


if __name__ == "__main__":
    asyncio.run(main())
