"""
Agent Journal - Persistent Memory for Trading Agents
Solves the "Goldfish Memory" problem by maintaining context across invocations.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from loguru import logger


class AgentJournal:
    """
    Manages persistent memory for trading agents.
    
    Stores:
    - Recent analyses per agent (last 5)
    - Active theses with invalidation levels
    - PM's strategic trading plan
    - Pending actions and watchlist
    - Recent mistakes to avoid
    """
    
    JOURNAL_FILE = Path(__file__).parent.parent.parent / "data" / "agent_journal.json"
    MAX_HISTORY = 5  # Keep last 5 analyses per agent
    
    def __init__(self):
        self._journal = self._load_journal()
        
    def _load_journal(self) -> dict:
        """Load journal from file or create new"""
        try:
            if self.JOURNAL_FILE.exists():
                with open(self.JOURNAL_FILE, "r") as f:
                    data = json.load(f)
                    logger.info(f"📔 Loaded agent journal with {len(data.get('agents', {}))} agents")
                    return data
        except Exception as e:
            logger.warning(f"Failed to load journal: {e}")
        
        # Return fresh journal
        return {
            "created_at": datetime.now().isoformat(),
            "invocation_count": 0,
            "agents": {
                "bull": {"analyses": [], "active_thesis": None},
                "bear": {"analyses": [], "active_thesis": None},
                "technical": {"analyses": [], "active_thesis": None},
                "sentiment": {"analyses": [], "active_thesis": None},
            },
            "pm_strategy": {
                "active_plan": None,
                "pending_actions": [],
                "recent_decisions": [],
            },
            "portfolio_history": [],  # Last 5 portfolio snapshots per invocation
            "mistakes_log": [],
            "lessons_applied": [],
        }
    
    def _save_journal(self):
        """Persist journal to file"""
        try:
            self.JOURNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.JOURNAL_FILE, "w") as f:
                json.dump(self._journal, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save journal: {e}")
    
    def increment_invocation(self):
        """Track invocation count"""
        self._journal["invocation_count"] += 1
        self._save_journal()
        return self._journal["invocation_count"]
    
    def get_invocation_count(self) -> int:
        return self._journal.get("invocation_count", 0)
    
    def log_portfolio_snapshot(self, portfolio_data: dict):
        """
        Log portfolio state at each invocation for context.
        
        Args:
            portfolio_data: {
                "equity": float,
                "cash_balance": float,
                "unrealized_pnl": float,
                "realized_pnl": float,
                "positions": [{"symbol": str, "side": str, "pnl_percent": float, ...}],
                "exposure_percent": float,
            }
        """
        if "portfolio_history" not in self._journal:
            self._journal["portfolio_history"] = []
        
        snapshot = {
            "invocation": self._journal["invocation_count"],
            "timestamp": datetime.now().isoformat(),
            **portfolio_data
        }
        
        # Insert at front, keep only MAX_HISTORY (5)
        self._journal["portfolio_history"].insert(0, snapshot)
        self._journal["portfolio_history"] = self._journal["portfolio_history"][:self.MAX_HISTORY]
        
        self._save_journal()
        logger.debug(f"💰 Logged portfolio snapshot (equity: ${portfolio_data.get('equity', 0):,.0f})")
    
    def detect_repetition(self, agent_key: str) -> dict:
        """
        Detect if an agent is producing repetitive outputs.
        
        This prevents agents from getting stuck in state loops where they
        keep producing the same action/thesis without questioning it.
        
        Returns:
            dict with:
                - is_repetitive: bool
                - similarity: float (0-1)
                - consecutive_same_action: bool
                - message: str (warning to inject into prompt, or empty)
        """
        analyses = self._journal["agents"].get(agent_key, {}).get("analyses", [])
        
        if len(analyses) < 3:
            return {"is_repetitive": False, "similarity": 0, "message": ""}
        
        # Extract action keywords from recent analyses
        recent_actions = []
        thesis_texts = []
        
        for a in analyses[:5]:
            summary = a.get("summary", {})
            thesis = str(summary.get("thesis", "")).lower()
            thesis_texts.append(thesis)
            
            # Extract action type from thesis
            action = "hold"
            if "modify" in thesis: action = "modify"
            elif "open" in thesis: action = "open"
            elif "close" in thesis: action = "close"
            elif "trending" in thesis and "modify" in thesis: action = "modify"
            elif "trending" in thesis and "hold" in thesis: action = "hold"
            recent_actions.append(action)
        
        # Calculate action similarity (all same action = high similarity)
        unique_actions = set(recent_actions)
        action_similarity = 1.0 - (len(unique_actions) / max(len(recent_actions), 1))
        
        # Calculate thesis text similarity using word overlap
        text_similarity = 0.0
        if len(thesis_texts) >= 2 and thesis_texts[0] and thesis_texts[1]:
            words_first = set(thesis_texts[0].split())
            words_second = set(thesis_texts[1].split())
            if words_first and words_second:
                overlap = len(words_first & words_second) / max(len(words_first | words_second), 1)
                text_similarity = overlap
        
        # Overall similarity is max of action and text similarity
        similarity_score = max(action_similarity, text_similarity)
        
        # Detect if repetitive: >70% similar for 3+ consecutive analyses
        is_repetitive = similarity_score > 0.7 and len(recent_actions) >= 3
        consecutive_same_action = len(unique_actions) == 1 and len(recent_actions) >= 3
        
        message = ""
        if is_repetitive:
            message = f"""
═══════════════════════════════════════════════════════════════════════════════
🔁 PATTERN DETECTED: POTENTIAL STATE LOOP
═══════════════════════════════════════════════════════════════════════════════

Your last {len(recent_actions)} analyses have produced similar outputs:
  Actions: {recent_actions}
  Similarity: {similarity_score:.0%}

⚠️ CRITICAL SELF-CHECK (You are NOT forced to change, but MUST acknowledge):

1. Have market conditions ACTUALLY remained identical?
   - Check if price, RSI, sentiment have meaningfully changed
   
2. Are you considering alternative interpretations?
   - What would a contrarian view say?
   - What are you potentially missing?
   
3. Is there new information you haven't fully processed?
   - Recent news, volume changes, correlation shifts?
   
4. What SPECIFIC condition would make you change your view?
   - State this clearly in your invalidation field

📌 If conditions genuinely warrant the same action, state WHY explicitly.
📌 If you've been on autopilot, this is your chance to reconsider.

═══════════════════════════════════════════════════════════════════════════════
"""
        
        return {
            "is_repetitive": is_repetitive,
            "similarity": similarity_score,
            "consecutive_same_action": consecutive_same_action,
            "recent_actions": recent_actions,
            "message": message,
        }

    
    def get_portfolio_context(self) -> str:
        """Generate portfolio history context for agent prompts."""
        history = self._journal.get("portfolio_history", [])
        
        if not history:
            return ""
        
        lines = [
            "",
            "═" * 70,
            "💰 PORTFOLIO EVOLUTION (Last 5 Invocations)",
            "═" * 70,
        ]
        
        for snap in history[:5]:
            inv = snap.get("invocation", "?")
            equity = snap.get("equity", 0)
            pnl = snap.get("unrealized_pnl", 0)
            exposure = snap.get("exposure_percent", 0)
            positions = snap.get("positions", [])
            
            # Format positions string
            if positions:
                pos_parts = []
                for p in positions:
                    pos_parts.append(f"{p.get('symbol', '?')} {p.get('side', '?')} ({p.get('pnl_percent', 0):+.1f}%)")
                pos_str = ", ".join(pos_parts)
            else:
                pos_str = "No positions"
            
            pnl_sign = "+" if pnl >= 0 else ""
            lines.append(f"  #{inv}: Equity ${equity:,.0f} | Unrealized {pnl_sign}${pnl:.0f} | Exposure {exposure:.0f}%")
            lines.append(f"        Positions: {pos_str}")
        
        lines.append("═" * 70)
        lines.append("⚠️ Track portfolio changes to see impact of your recommendations.")
        lines.append("═" * 70)
        return "\n".join(lines)

    def log_analysis(self, agent_name: str, analysis: str, summary: dict = None):
        """
        Store an agent's analysis for future context.
        
        Args:
            agent_name: bull, bear, technical, sentiment (or full name like "Bull Researcher")
            analysis: The full analysis text
            summary: Optional structured summary (thesis, confidence, etc.)
        """
        # Normalize agent name to journal key
        name_map = {
            "bull researcher": "bull",
            "bear researcher": "bear",
            "technical analyst": "technical",
            "sentiment analyst": "sentiment",
            "risk guardian": "risk",
            "portfolio manager": "pm",
        }
        agent_key = name_map.get(agent_name.lower(), agent_name.lower().split()[0])
        
        if agent_key not in self._journal["agents"]:
            self._journal["agents"][agent_key] = {"analyses": [], "active_thesis": None}
        
        entry = {
            "invocation": self._journal["invocation_count"],
            "timestamp": datetime.now().isoformat(),
            "analysis": analysis[:2000] if analysis else "",  # Truncate for storage
            "summary": summary or {},
        }
        
        # Add to front, keep only MAX_HISTORY
        self._journal["agents"][agent_key]["analyses"].insert(0, entry)
        self._journal["agents"][agent_key]["analyses"] = \
            self._journal["agents"][agent_key]["analyses"][:self.MAX_HISTORY]
        
        # Update active thesis if provided
        if summary and summary.get("thesis"):
            self._journal["agents"][agent_key]["active_thesis"] = {
                "thesis": summary["thesis"],
                "confidence": summary.get("confidence", 0.5),
                "invalidation": summary.get("invalidation"),
                "updated_at": datetime.now().isoformat(),
            }
        
        self._save_journal()
        logger.debug(f"📔 Logged {agent_name} analysis (#{self._journal['invocation_count']})")
    
    def get_agent_context(self, agent_name: str) -> str:
        """
        Generate a context string for an agent with their recent history.
        This is injected into the agent's prompt.
        """
        # Normalize agent name to journal key (same as log_analysis)
        name_map = {
            "bull researcher": "bull",
            "bear researcher": "bear",
            "technical analyst": "technical",
            "sentiment analyst": "sentiment",
            "risk guardian": "risk",
            "portfolio manager": "pm",
        }
        agent_key = name_map.get(agent_name.lower(), agent_name.lower().split()[0])
        
        agent_data = self._journal["agents"].get(agent_key, {})
        analyses = agent_data.get("analyses", [])
        active_thesis = agent_data.get("active_thesis")
        
        if not analyses and not active_thesis:
            return ""
        
        context_parts = [
            "",
            "═" * 70,
            "📔 YOUR MEMORY - RECENT ANALYSES (Maintain consistency unless market changed)",
            "═" * 70,
        ]
        
        # Add active thesis first (with confidence decay)
        if active_thesis:
            # Calculate confidence decay (2% per hour)
            original_confidence = active_thesis.get('confidence', 0.5)
            try:
                thesis_time = datetime.fromisoformat(active_thesis.get('updated_at', datetime.now().isoformat()))
                hours_old = (datetime.now() - thesis_time).total_seconds() / 3600
                decay_factor = max(0.5, 1 - (hours_old * 0.02))  # 2% decay/hour, min 50%
                adjusted_confidence = round(original_confidence * decay_factor, 2)
                confidence_str = f"{adjusted_confidence} (was {original_confidence}, decayed over {hours_old:.1f}h)"
            except:
                adjusted_confidence = original_confidence
                confidence_str = str(original_confidence)
            
            context_parts.append(f"""
🎯 YOUR ACTIVE THESIS:
   View: {active_thesis.get('thesis', 'None')}
   Confidence: {confidence_str}
   Invalidation: {active_thesis.get('invalidation', 'Not set')}
   Last Updated: {active_thesis.get('updated_at', 'Unknown')}
   ⚠️ NOTE: Confidence decays over time. Update your thesis to refresh it.
""")
        
        # Add recent analyses
        for i, entry in enumerate(analyses[:3]):  # Show last 3
            invocation = entry.get("invocation", "?")
            timestamp = entry.get("timestamp", "Unknown")
            analysis_snippet = entry.get("analysis", "")[:500]
            
            # Calculate how long ago
            try:
                dt = datetime.fromisoformat(timestamp)
                mins_ago = int((datetime.now() - dt).total_seconds() / 60)
                time_str = f"{mins_ago} min ago" if mins_ago < 60 else f"{mins_ago // 60}h {mins_ago % 60}m ago"
            except:
                time_str = timestamp
            
            context_parts.append(f"""
--- Analysis #{invocation} ({time_str}) ---
{analysis_snippet}...
""")
        
        context_parts.append("═" * 70)
        context_parts.append("""
⚠️ IMPORTANT: Review your previous analyses above. You should:
1. MAINTAIN your thesis unless market conditions have FUNDAMENTALLY changed
2. Note any evolving patterns or developments
3. Update confidence levels based on new data
4. If your thesis is invalidated, clearly state the new view

Output your analysis in JSON format, MUST include:
- "thesis": Your current market view (1-2 sentences)
- "confidence": 0.0 to 1.0
- "invalidation": What would change your view
""")
        context_parts.append("═" * 70)
        
        # Check for state loop / repetitive pattern
        repetition = self.detect_repetition(agent_key)
        if repetition["is_repetitive"]:
            context_parts.append(repetition["message"])
            logger.info(f"🔁 State loop detected for {agent_key}: {repetition['similarity']:.0%} similarity")
        
        # Add portfolio evolution context ONLY for PM and Risk Guardian
        # Domain agents (bull, bear, technical, sentiment) should focus purely on their analysis
        if agent_key in ["pm", "risk"]:
            portfolio_context = self.get_portfolio_context()
            if portfolio_context:
                context_parts.append(portfolio_context)
        
        return "\n".join(context_parts)
    
    def get_all_agents_summary(self) -> str:
        """
        Get summary of all agents' current theses for cross-agent awareness.
        PM uses this to see what all specialists are thinking.
        """
        from datetime import timedelta
        
        summary_parts = []
        for agent_name, data in self._journal.get("agents", {}).items():
            thesis = data.get("active_thesis")
            if thesis and thesis.get("thesis"):
                # Calculate decayed confidence
                original_conf = thesis.get('confidence', 0.5)
                try:
                    thesis_time = datetime.fromisoformat(thesis.get('updated_at', datetime.now().isoformat()))
                    hours_old = (datetime.now() - thesis_time).total_seconds() / 3600
                    decay_factor = max(0.5, 1 - (hours_old * 0.02))
                    adj_conf = round(original_conf * decay_factor, 2)
                except:
                    adj_conf = original_conf
                    hours_old = 0
                
                summary_parts.append(
                    f"  • {agent_name.upper()}: {thesis['thesis'][:80]}... "
                    f"(conf: {adj_conf}, {hours_old:.1f}h old)"
                )
        
        if not summary_parts:
            return ""
        
        return "\n".join([
            "",
            "═" * 70,
            "👥 ALL AGENTS' CURRENT THESES (Cross-Agent Awareness)",
            "═" * 70,
        ] + summary_parts + ["═" * 70])
    
    def get_pm_context(self) -> str:
        """Get context for Portfolio Manager including strategic plan and past analyses"""
        pm_data = self._journal.get("pm_strategy", {})
        active_plan = pm_data.get("active_plan")
        pending_actions = pm_data.get("pending_actions", [])
        recent_decisions = pm_data.get("recent_decisions", [])
        
        # Start with cross-agent summary so PM sees all theses
        context_parts = [self.get_all_agents_summary()]
        
        # Add PM's own past analyses (past 5 invocations)
        pm_agent_data = self._journal.get("agents", {}).get("pm", {})
        pm_analyses = pm_agent_data.get("analyses", [])[:5]
        if pm_analyses:
            context_parts.extend([
                "",
                "═" * 70,
                "📊 YOUR PAST DECISIONS (Last 5 Invocations)",
                "═" * 70,
            ])
            for i, entry in enumerate(pm_analyses, 1):
                inv = entry.get("invocation", "?")
                ts = entry.get("timestamp", "Unknown")[:19]  # Truncate timestamp
                summary = entry.get("summary", {})
                thesis = summary.get("thesis", "No thesis recorded")[:80]
                conf = summary.get("confidence", "?")
                context_parts.append(f"  #{inv} ({ts}): {thesis} (conf: {conf})")
            context_parts.append("═" * 70)
            context_parts.append("⚠️ MAINTAIN CONSISTENCY: Only change view if market conditions changed significantly.")
        
        if not active_plan and not recent_decisions and not pm_analyses:
            return context_parts[0] if context_parts[0] else ""
        
        if active_plan or recent_decisions:
            context_parts.extend([
                "",
                "═" * 70,
                "📋 YOUR STRATEGIC PLAN & MEMORY",
                "═" * 70,
            ])
        
        if active_plan:
            context_parts.append(f"""
🎯 ACTIVE TRADING PLAN:
   Created: {active_plan.get('created_at', 'Unknown')}
   Market Regime: {active_plan.get('market_regime', 'Unknown')}
   Primary Thesis: {active_plan.get('primary_thesis', 'None')}
   Strategy: {active_plan.get('strategy', 'None')}
   Targets: {active_plan.get('targets', [])}
   Invalidation: {active_plan.get('invalidation', 'Not set')}
""")
        
        if pending_actions:
            context_parts.append("\n📌 PENDING ACTIONS:")
            for action in pending_actions[:5]:
                context_parts.append(f"   • {action}")
        
        if recent_decisions:
            context_parts.append("\n📜 RECENT DECISIONS:")
            for decision in recent_decisions[:3]:
                context_parts.append(f"   • {decision.get('action', 'Unknown')} at {decision.get('timestamp', 'Unknown')}")
        
        context_parts.append("""
═══════════════════════════════════════════════════════════════════════════════
⚠️ IMPORTANT: Follow your strategic plan. Only deviate if:
1. Your invalidation level is breached
2. A major unexpected event occurs
3. Position risk management requires it

If modifying the plan, clearly state WHY and update the plan.
═══════════════════════════════════════════════════════════════════════════════
""")
        
        # Check for PM state loop / repetitive decisions
        pm_repetition = self.detect_repetition("pm")
        if pm_repetition["is_repetitive"]:
            context_parts.append(pm_repetition["message"])
            logger.info(f"🔁 State loop detected for pm: {pm_repetition['similarity']:.0%} similarity")
        
        # Add portfolio evolution context for PM to see past 5 invocations
        portfolio_context = self.get_portfolio_context()
        if portfolio_context:
            context_parts.append(portfolio_context)
        
        return "\n".join(context_parts)
    
    def update_pm_strategy(
        self,
        market_regime: str = None,
        thesis: str = None,
        strategy: str = None,
        targets: list = None,
        invalidation: str = None,
        pending_actions: list = None,
    ):
        """Update PM's strategic plan"""
        if "pm_strategy" not in self._journal:
            self._journal["pm_strategy"] = {}
        
        if not self._journal["pm_strategy"].get("active_plan"):
            self._journal["pm_strategy"]["active_plan"] = {
                "created_at": datetime.now().isoformat(),
            }
        
        plan = self._journal["pm_strategy"]["active_plan"]
        
        if market_regime:
            plan["market_regime"] = market_regime
        if thesis:
            plan["primary_thesis"] = thesis
        if strategy:
            plan["strategy"] = strategy
        if targets:
            plan["targets"] = targets
        if invalidation:
            plan["invalidation"] = invalidation
        
        plan["updated_at"] = datetime.now().isoformat()
        
        if pending_actions is not None:
            self._journal["pm_strategy"]["pending_actions"] = pending_actions
        
        self._save_journal()
        logger.info("📋 Updated PM strategic plan")
    
    def clear_position_thesis(self, symbol: str, exit_reason: str = "closed"):
        """
        Clear PM's thesis when a position closes.
        
        This prevents the PM from thinking a position is still active
        after it's been closed by SL, TP, or other exit mechanisms.
        
        Args:
            symbol: The symbol that was closed (e.g. "BTC")
            exit_reason: Why the position was closed (e.g. "stop_loss", "take_profit")
        """
        if "pm_strategy" not in self._journal:
            return
            
        if self._journal["pm_strategy"].get("active_plan"):
            old_thesis = self._journal["pm_strategy"]["active_plan"].get("primary_thesis", "")
            
            # Only clear if the thesis mentions this symbol
            if symbol.upper() in old_thesis.upper():
                self._journal["pm_strategy"]["active_plan"]["primary_thesis"] = (
                    f"[POSITION CLOSED: {symbol} exit via {exit_reason}] "
                    f"No active position. Previous thesis cleared."
                )
                self._journal["pm_strategy"]["active_plan"]["updated_at"] = datetime.now().isoformat()
                
                # Clear pending actions related to this symbol
                pending = self._journal["pm_strategy"].get("pending_actions", [])
                self._journal["pm_strategy"]["pending_actions"] = [
                    a for a in pending if symbol.upper() not in a.upper()
                ]
                
                self._save_journal()
                logger.info(f"🔄 Cleared PM thesis for {symbol} - position closed via {exit_reason}")
    
    def log_pm_decision(self, decision: dict):
        """Log a PM decision for history"""
        if "pm_strategy" not in self._journal:
            self._journal["pm_strategy"] = {"recent_decisions": []}
        if "recent_decisions" not in self._journal["pm_strategy"]:
            self._journal["pm_strategy"]["recent_decisions"] = []
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": decision.get("action", "UNKNOWN"),
            "symbol": decision.get("symbol", "BTC"),
            "direction": decision.get("direction"),
            "reasoning": decision.get("reasoning", "")[:200],
        }
        
        self._journal["pm_strategy"]["recent_decisions"].insert(0, entry)
        self._journal["pm_strategy"]["recent_decisions"] = \
            self._journal["pm_strategy"]["recent_decisions"][:10]
        
        self._save_journal()
    
    def log_mistake(self, mistake: str, lesson: str):
        """Log a trading mistake to avoid in future"""
        self._journal["mistakes_log"].insert(0, {
            "timestamp": datetime.now().isoformat(),
            "mistake": mistake,
            "lesson": lesson,
        })
        self._journal["mistakes_log"] = self._journal["mistakes_log"][:10]
        self._save_journal()
    
    def get_mistakes_context(self) -> str:
        """Get recent mistakes to avoid"""
        mistakes = self._journal.get("mistakes_log", [])
        if not mistakes:
            return ""
        
        context = [
            "",
            "⚠️ RECENT MISTAKES TO AVOID:",
        ]
        for m in mistakes[:3]:
            context.append(f"   • {m.get('lesson', 'Unknown')}")
        
        return "\n".join(context)
    
    def get_full_journal(self) -> dict:
        """Get the entire journal for dashboard display"""
        return self._journal


# Singleton instance
_journal_instance = None

def get_journal() -> AgentJournal:
    """Get or create the journal singleton"""
    global _journal_instance
    if _journal_instance is None:
        _journal_instance = AgentJournal()
    return _journal_instance
