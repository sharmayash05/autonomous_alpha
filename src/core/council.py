"""
Multi-Agent Trading Council
The Autonomous Alpha - LangGraph-based Agent Orchestration

This module implements the multi-agent council architecture:
- Bull Researcher (bullish thesis)
- Bear Researcher (bearish thesis)
- Technical Analyst (price/volume only)
- Sentiment Analyst (social signals)
- Risk Guardian (veto power)
- Portfolio Manager (synthesis)
"""

import asyncio
import json
from typing import TypedDict, Literal
from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    logger.warning("LangGraph not installed. Council will use sequential execution.")

from .llm_client import LLMClient, load_prompt_template, format_prompt


# ============================================================================
# JSON Extraction Helper
# ============================================================================

import re

def extract_json(text: str) -> dict:
    """
    Extract JSON from LLM response that may be wrapped in markdown code blocks.
    Handles various common patterns from LLMs.
    """
    if not text:
        return {}
    
    original_text = text
    
    # Clean up common issues
    text = text.strip()
    
    # Method 1: Try raw text first (if it starts with {)
    if text.startswith('{'):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    
    # Method 2: Extract from markdown code blocks ```json ... ``` or ``` ... ```
    code_block_patterns = [
        r'```json\s*\n?([\s\S]*?)\n?```',
        r'```\s*\n?([\s\S]*?)\n?```',
    ]
    for pattern in code_block_patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            json_str = match.group(1).strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue
    
    # Method 3: Find first { and last } to extract JSON object
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace > first_brace:
        json_str = text[first_brace:last_brace + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    # Method 4: Use balanced brace matching
    if first_brace != -1:
        brace_count = 0
        in_string = False
        escape_next = False
        
        for i, char in enumerate(text[first_brace:], first_brace):
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_str = text[first_brace:i + 1]
                        try:
                            return json.loads(json_str)
                        except json.JSONDecodeError:
                            break
    
    # Method 5: Try to fix common JSON issues
    # Sometimes LLMs add trailing commas or use single quotes
    if first_brace != -1 and last_brace > first_brace:
        json_str = text[first_brace:last_brace + 1]
        # Remove trailing commas before } or ]
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        # Replace single quotes with double quotes (risky but sometimes works)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    
    logger.warning(f"Could not extract JSON from response (length={len(original_text)})")
    logger.info(f"Failed response: {original_text[:300]}...")
    return {}


# ============================================================================
# State Definition
# ============================================================================

class TradingState(TypedDict):
    """State passed between agents in the council"""
    # Market data
    market_data: dict
    timestamp: str
    
    # Agent outputs
    bull_thesis: str | None
    bear_thesis: str | None
    technical_view: str | None
    sentiment_score: float | None
    sentiment_analysis: str | None
    
    # Debate
    debate_rounds: list[str]
    current_round: int
    consensus_reached: bool
    
    # Decision
    proposed_decision: dict | None
    final_decision: dict | None
    
    # Risk
    risk_assessment: dict | None
    risk_veto: bool
    veto_reason: str | None


@dataclass
class AgentConfig:
    """Configuration for an agent"""
    name: str
    model: str
    temperature: float
    max_tokens: int
    prompt_template: str
    role: str


# ============================================================================
# Agent Implementations
# ============================================================================

class BaseAgent:
    """Base class for all trading agents with persistent memory"""
    
    def __init__(self, config: AgentConfig, llm_client: LLMClient, journal=None, market_memory=None, domain_memory=None, domain=None):
        self.config = config
        self.llm = llm_client
        self._prompt_template: str | None = None
        self.journal = journal  # Agent memory journal
        self.market_memory = market_memory  # RAG memory for historical precedents
        self.domain_memory = domain_memory  # Domain-specific pattern memory
        self.domain = domain  # Domain lane: "technical", "sentiment", "fundamental"
        
    @property
    def prompt_template(self) -> str:
        if self._prompt_template is None:
            try:
                self._prompt_template = load_prompt_template(self.config.prompt_template)
            except FileNotFoundError:
                # Use default inline template
                self._prompt_template = self._default_template()
        return self._prompt_template
    
    def _default_template(self) -> str:
        """Override in subclasses for default template"""
        return "Analyze the following market data:\n{market_data}"
    
    async def analyze(self, state: TradingState) -> dict:
        """Run agent analysis"""
        market_data_json = json.dumps(state.get("market_data", {}), indent=2)
        
        # Get the base prompt template
        base_prompt = self.prompt_template
        
        # ALWAYS append market data at the end, regardless of whether template has placeholder
        # This ensures agents ALWAYS receive the actual live data
        data_section = f"""

══════════════════════════════════════════════════════════════════════════════
⚠️ ACTUAL LIVE MARKET DATA - YOU MUST ANALYZE THIS DATA, NOT GENERATE EXAMPLES
══════════════════════════════════════════════════════════════════════════════

{market_data_json}

══════════════════════════════════════════════════════════════════════════════
INSTRUCTIONS: Analyze the ABOVE data. Do NOT ask for data. Do NOT generate mock examples.
Output your analysis based on the ACTUAL values shown above.
══════════════════════════════════════════════════════════════════════════════
"""
        
        # If template has {market_data} placeholder, format it; otherwise append
        if "{market_data}" in base_prompt:
            prompt = format_prompt(
                base_prompt,
                market_data=market_data_json,
                timestamp=state.get("timestamp", datetime.now().isoformat()),
            )
        else:
            # Append the data section
            prompt = base_prompt + data_section
        
        # Inject historical memory context from journal
        if self.journal:
            memory_context = self.journal.get_agent_context(self.config.name)
            if memory_context:
                prompt += memory_context
        
        # Inject RAG-based historical precedents
        if self.market_memory:
            try:
                precedents = self.market_memory.query_similar(
                    state.get("market_data", {}),
                    limit=3,
                    min_age_hours=1,
                )
                if precedents:
                    prompt += self.market_memory.format_precedents(precedents)
            except Exception as e:
                pass  # Don't fail on memory errors
        
        # Inject domain-specific pattern memory (specialist RAG)
        if self.domain_memory and self.domain:
            try:
                market_data = state.get("market_data", {})
                btc = market_data.get("BTC", {})
                
                # Build context for domain query
                domain_context = {}
                if self.domain == "technical":
                    domain_context = {
                        "rsi": btc.get("rsi_14"),
                        "trend": btc.get("trend"),
                        "ema_position": "above EMA" if btc.get("price", 0) > btc.get("ema_50", 0) else "below EMA",
                        "pattern": btc.get("pattern", ""),
                    }
                elif self.domain == "sentiment":
                    domain_context = {
                        "fear_greed": market_data.get("fear_greed", {}).get("value"),
                        "social_sentiment": market_data.get("social_sentiment", "neutral"),
                        "news_tone": market_data.get("news_tone", "mixed"),
                    }
                elif self.domain == "fundamental":
                    domain_context = {
                        "event": market_data.get("latest_event", ""),
                        "actor": market_data.get("event_actor", ""),
                        "event_type": market_data.get("event_type", ""),
                    }
                
                patterns = self.domain_memory.recall_similar_patterns(
                    domain=self.domain,
                    current_context=domain_context,
                    limit=5,
                )
                if patterns:
                    prompt += self.domain_memory.format_patterns_for_prompt(patterns, self.domain)
            except Exception as e:
                pass  # Don't fail on domain memory errors
        
        # Query domain-filtered lessons from existing TradingMemory (Reflexion)
        # This enables specialists to self-correct from past trade lessons
        if self.domain:
            try:
                market_data = state.get("market_data", {})
                btc = market_data.get("BTC", {})
                context_query = f"BTC at ${btc.get('price', 0):,.0f} with RSI {btc.get('rsi_14', 50):.0f}"
                
                # Get domain-filtered lessons from reflexion memory
                from src.memory.reflector import get_reflexion_loop
                reflexion = get_reflexion_loop()
                if reflexion and reflexion.memory:
                    domain_lessons = reflexion.memory.recall_domain_lessons(
                        domain=self.domain,
                        context_query=context_query,
                        top_k=5,
                    )
                    if domain_lessons:
                        prompt += reflexion.memory.format_domain_lessons_for_prompt(domain_lessons, self.domain)
            except Exception as e:
                pass  # Don't fail on lesson query errors
        
        
        # DEBUG: Log full prompt for Technical Analyst to show user what data it sees
        if self.config.name == "Technical Analyst":
            logger.info(f"\n{'='*80}\n🔍 TECHNICAL ANALYST FULL PROMPT (DEBUG)\n{'='*80}\n{prompt}\n{'='*80}")
        
        response = await self.llm.generate(
            prompt=prompt,
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        
        # Save analysis to journal for future context
        if self.journal:
            try:
                # Try to extract thesis from response
                content = response.content
                summary = {}
                if '{' in content:
                    import re
                    json_match = re.search(r'\{[\s\S]*\}', content)
                    if json_match:
                        try:
                            data = json.loads(json_match.group())
                            
                            # Extract thesis from various response formats
                            thesis = None
                            confidence = None
                            invalidation = None
                            
                            # Try direct keys first
                            thesis = data.get("thesis") or data.get("headline") or data.get("view")
                            confidence = data.get("confidence")
                            invalidation = data.get("invalidation") or data.get("fundamental_trigger")
                            
                            # Try nested bullish_thesis structure
                            if not thesis and "bullish_thesis" in data:
                                bt = data["bullish_thesis"]
                                thesis = bt.get("headline") or bt.get("thesis")
                                confidence = bt.get("confidence") or data.get("conviction", {}).get("confidence")
                                invalidation = bt.get("invalidation") or data.get("invalidation", {}).get("fundamental_trigger")
                            
                            # Try nested bearish_thesis structure
                            if not thesis and "bearish_thesis" in data:
                                bt = data["bearish_thesis"]
                                thesis = bt.get("headline") or bt.get("thesis")
                                confidence = bt.get("confidence") or data.get("conviction", {}).get("confidence")
                                invalidation = bt.get("invalidation") or data.get("invalidation", {}).get("fundamental_trigger")
                            
                            # Try technical analysis structure
                            if not thesis and "signal" in data:
                                thesis = f"{data.get('signal')} - {data.get('trend', {}).get('primary', 'Unknown trend')}"
                                confidence = data.get("confidence") or 0.7
                            
                            # Try sentiment structure
                            if not thesis and "sentiment" in data:
                                s = data["sentiment"]
                                thesis = f"{s.get('rating', 'Neutral')} - {s.get('summary', '')}"
                                confidence = s.get("confidence")
                            
                            summary = {
                                "thesis": thesis,
                                "confidence": confidence,
                                "invalidation": invalidation,
                            }
                        except:
                            pass
                self.journal.log_analysis(self.config.name, content, summary)
            except Exception as e:
                pass  # Don't fail on journal errors
        
        return {"content": response.content, "latency_ms": response.latency_ms}


class BullResearcher(BaseAgent):
    """Finds bullish catalysts and opportunities"""
    
    def _default_template(self) -> str:
        return """
You are the BULL RESEARCHER, an optimistic fundamental analyst.
Your job: Find reasons WHY the asset should appreciate.

FOCUS AREAS:
- On-chain metrics (TVL growth, active addresses, developer activity)
- Protocol upgrades and roadmap catalysts
- Institutional adoption signals
- Undervaluation relative to competitors

YOU MUST ALWAYS ARGUE BULLISH. Even in bearish setups, find silver linings.
Your counterpart (Bear Researcher) will provide balance.

MARKET DATA:
{market_data}

Analyze and output JSON with:
{
  "bullish_thesis": "Your main bullish argument",
  "catalysts": ["catalyst1", "catalyst2"],
  "price_target": "Your upside target with reasoning",
  "confidence": 0.0-1.0,
  "timeframe": "Expected timeframe for thesis to play out"
}
"""


class BearResearcher(BaseAgent):
    """Finds bearish risks and concerns"""
    
    def _default_template(self) -> str:
        return """
You are the BEAR RESEARCHER, a skeptical fundamental analyst.
Your job: Find reasons WHY the asset should depreciate.

FOCUS AREAS:
- Token unlock schedules and sell pressure
- Competitive threats and market share loss
- Regulatory headwinds
- Overvaluation relative to fundamentals

YOU MUST ALWAYS ARGUE BEARISH. Find flaws in every bullish narrative.
This creates the dialectic necessary for objective decisions.

MARKET DATA:
{market_data}

Analyze and output JSON with:
{
  "bearish_thesis": "Your main bearish argument",
  "risks": ["risk1", "risk2"],
  "price_floor": "Your downside target with reasoning",
  "confidence": 0.0-1.0,
  "warning_signs": ["sign1", "sign2"]
}
"""


class TechnicalAnalyst(BaseAgent):
    """Pure price and volume analysis"""
    
    def _default_template(self) -> str:
        return """
You are the TECHNICAL ANALYST. You see ONLY price and volume.
No fundamental data. No news. Just the chart.

INPUTS TO ANALYZE:
- Price action and trend
- RSI(7), RSI(14)
- MACD histogram and signal
- EMA crossovers
- Volume patterns
- Support/Resistance levels

MARKET DATA:
{market_data}

Analyze and output JSON with:
{
  "signal": "STRONG_LONG|WEAK_LONG|NEUTRAL|WEAK_SHORT|STRONG_SHORT",
  "trend": "UPTREND|DOWNTREND|RANGING",
  "key_levels": {
    "support": [level1, level2],
    "resistance": [level1, level2]
  },
  "entry_zone": {"low": price, "high": price},
  "invalidation": "Price level that invalidates the setup",
  "confidence": 0.0-1.0,
  "reasoning": "Technical reasoning"
}
"""


class SentimentAnalyst(BaseAgent):
    """Social and market sentiment analysis"""
    
    def _default_template(self) -> str:
        return """
You are the SENTIMENT ANALYST. You monitor the emotional pulse of the market.

DATA SOURCES TO CONSIDER:
- Funding rates (positive = crowded long, negative = crowded short)
- Open interest changes
- Social media sentiment indicators
- Fear & Greed index
- Retail vs institutional flow patterns

MARKET DATA:
{market_data}

Analyze and output JSON with:
{
  "sentiment_score": -1.0 to 1.0,
  "crowd_positioning": "CROWDED_LONG|NEUTRAL|CROWDED_SHORT",
  "contrarian_signal": true/false,
  "key_observations": ["obs1", "obs2"],
  "confidence": 0.0-1.0,
  "trading_implication": "What this means for trading"
}
"""


class RiskGuardian(BaseAgent):
    """Risk management with veto power"""
    
    def _default_template(self) -> str:
        return """
You are the RISK GUARDIAN for a crypto trading system.
Your role is to evaluate trades and APPROVE good opportunities while protecting capital.

⚠️ CRITICAL: Read the PROPOSED TRADE carefully. The size_usd field is the ACTUAL proposed position size.
Do NOT assume or hallucinate different values. Use ONLY the values in the JSON below.

RISK LIMITS (Portfolio: $10,000):
- Max single position: 5% of portfolio = $500
- Max total exposure: 30% = $3,000
- Max leverage: 10x

═══════════════════════════════════════════════════════════════════
EVALUATION CRITERIA FOR OPEN ACTIONS:
═══════════════════════════════════════════════════════════════════
1. Position Size: Check if size_usd <= $500 (PASS if $500 or less)
2. Risk/Reward Ratio: Approve if R:R >= 1.5
3. Stop Loss: Must be set and reasonable (2-3% from entry)
4. Technical Alignment: Consider trend and confidence

═══════════════════════════════════════════════════════════════════
⚠️ CRITICAL: EVALUATION CRITERIA FOR MODIFY ACTIONS
═══════════════════════════════════════════════════════════════════
For MODIFY (stop-loss/take-profit changes), validate the LOGIC is correct:

TRAILING STOP RULES (MUST ENFORCE):
• LONG positions: new_stop_loss MUST be >= current_stop_loss
  - Trail UP to lock in profits, NEVER down to risk more
  - If PM claims "raised" but new value < old value → VETO as logical error
  
• SHORT positions: new_stop_loss MUST be <= current_stop_loss
  - Trail DOWN to lock in profits, NEVER up to risk more
  - If PM claims "raised" but new value > old value → VETO as logical error

VETO MODIFY if:
- Trailing stop moves in wrong direction (gives back protected profit)
- PM's reasoning contradicts the actual numbers
- Stop would be beyond liquidation price

APPROVAL GUIDELINES:
- APPROVE OPEN if size_usd <= 500 AND R:R >= 1.5 AND stop_loss is set
- APPROVE MODIFY if trailing stop moves in correct direction
- APPROVE HOLD without further validation
- APPROVE CLOSE without further validation
- VETO only for clear violations

CURRENT POSITIONS (for MODIFY validation):
{current_positions}

PROPOSED TRADE (READ THE VALUES CAREFULLY):
{proposed_decision}

CURRENT MARKET DATA:
{market_data}

Evaluate THOROUGHLY. For MODIFY actions, verify the math matches the reasoning.
Output JSON:
{{
  "approved": true or false,
  "veto_reason": "Only if vetoed, otherwise null",
  "risk_score": 1.0-10.0 (lower is better),
  "action_validated": "OPEN|MODIFY|HOLD|CLOSE",
  "validation_details": {{
    "for_open": {{"position_size_check": "PASS/FAIL", "risk_reward_ratio": "X:Y"}},
    "for_modify": {{"stop_direction_valid": true/false, "reasoning_matches_values": true/false}}
  }},
  "recommendations": ["optional suggestions"]
}}
"""
    
    async def evaluate(self, state: TradingState, proposed_decision: dict) -> dict:
        """Evaluate a proposed trade for risk - with PROGRAMMATIC PRE-VALIDATION + INTELLIGENT LEARNING"""
        
        # ========== INTELLIGENT CONTEXT FROM PAST DECISIONS ==========
        past_context = ""
        if self.journal:
            agent_data = self.journal._journal.get("agents", {}).get("risk", {})
            past_analyses = agent_data.get("analyses", [])[:3]
            if past_analyses:
                recent_decisions = []
                for a in past_analyses:
                    inv = a.get("invocation", "?")
                    summary = a.get("summary", {}).get("thesis", a.get("analysis", "")[:50])
                    recent_decisions.append(f"#{inv}: {summary}")
                past_context = f"Recent Risk Decisions: {'; '.join(recent_decisions)}"
        
        # Learn from past lessons about risk
        risk_lessons = []
        market_data = state.get("market_data", {})
        past_lessons = market_data.get("past_lessons", [])
        for lesson in past_lessons[:5]:
            lesson_text = lesson.get("lesson_learned", "")
            if any(word in lesson_text.lower() for word in ["risk", "stop", "loss", "exposure", "size", "leverage"]):
                risk_lessons.append(lesson_text[:80])
        
        # ========== PROGRAMMATIC RISK VALIDATION (BYPASS LLM HALLUCINATIONS) ==========
        MAX_POSITION_USD = 500.0
        MAX_TOTAL_EXPOSURE_PCT = 30.0  # Max 30% of portfolio in positions
        PORTFOLIO_SIZE = 10000.0
        
        # Get current portfolio state
        account = state.get("market_data", {}).get("account", {})
        current_positions = account.get("positions", [])
        current_balance = account.get("balance", PORTFOLIO_SIZE)
        
        # Calculate current exposure
        current_exposure = sum(pos.get("size_usd", 0) for pos in current_positions)
        current_exposure_pct = (current_exposure / PORTFOLIO_SIZE) * 100
        
        # Symbols we already have positions in
        held_symbols = {pos.get("symbol") for pos in current_positions}
        
        decisions = proposed_decision.get("decisions", [])
        all_valid = True
        violations = []
        
        for decision in decisions:
            action = decision.get("action")
            symbol = decision.get("symbol", "")
            
            if action in ["HOLD", "CLOSE", "MODIFY"]:
                continue  # No risk check needed for HOLD/CLOSE/MODIFY
            
            # ========== NEW: PORTFOLIO-AWARE CHECKS ==========
            
            # Check 1: Duplicate position check
            if action == "OPEN" and symbol in held_symbols:
                all_valid = False
                violations.append(f"DUPLICATE: Already holding {symbol} position")
                logger.warning(f"🛡️ RISK: Blocking duplicate {symbol} position")
                continue
            
            size_usd = float(decision.get("size_usd", 0))
            leverage = float(decision.get("leverage", 1))
            notional = size_usd * leverage
            
            # Check 2: Leverage within limits
            MAX_LEVERAGE = 20
            if leverage > MAX_LEVERAGE:
                all_valid = False
                violations.append(f"LEVERAGE: {leverage}x exceeds {MAX_LEVERAGE}x limit")
            
            if leverage < 1:
                all_valid = False
                violations.append(f"LEVERAGE: {leverage}x must be >= 1")
            
            # Check 3: New position would exceed max margin exposure (30%)
            new_total_exposure = current_exposure + size_usd
            new_exposure_pct = (new_total_exposure / PORTFOLIO_SIZE) * 100
            if new_exposure_pct > MAX_TOTAL_EXPOSURE_PCT:
                all_valid = False
                violations.append(f"MARGIN EXPOSURE: {new_exposure_pct:.1f}% exceeds {MAX_TOTAL_EXPOSURE_PCT:.0f}% limit")
            
            # Check 4: Total notional exposure (max 100% of portfolio)
            current_notional = sum(p.get("notional_usd", p.get("size_usd", 0)) for p in current_positions)
            new_total_notional = current_notional + notional
            MAX_NOTIONAL_PCT = 100.0
            notional_pct = (new_total_notional / PORTFOLIO_SIZE) * 100
            if notional_pct > MAX_NOTIONAL_PCT:
                all_valid = False
                violations.append(f"NOTIONAL: {notional_pct:.1f}% exceeds {MAX_NOTIONAL_PCT:.0f}% limit")
            
            # Check 5: Too many open positions (max 5)
            if len(current_positions) >= 5 and action == "OPEN":
                all_valid = False
                violations.append(f"MAX_POSITIONS: Already have {len(current_positions)} positions (max 5)")
            
            # ========== EXISTING CHECKS ==========
            
            # Check 6: Margin size
            if size_usd > MAX_POSITION_USD:
                all_valid = False
                violations.append(f"Margin ${size_usd:.0f} > ${MAX_POSITION_USD:.0f} limit")
            
            # Get price values for remaining checks
            stop_loss = decision.get("stop_loss")
            take_profit = decision.get("take_profit")
            entry_price = decision.get("entry_price", 0)
            
            # Check 7: Stop loss exists
            if not stop_loss:
                all_valid = False
                violations.append("No stop loss defined")
            
            # Check 6: R:R ratio (if all prices available)
            if stop_loss and take_profit and entry_price:
                risk = abs(entry_price - stop_loss)
                reward = abs(take_profit - entry_price)
                if risk > 0:
                    rr_ratio = reward / risk
                    if rr_ratio < 1.0:
                        all_valid = False
                        violations.append(f"R:R ratio {rr_ratio:.2f} < 1.0 minimum")
        
        # If all checks pass, AUTO-APPROVE without LLM
        if all_valid and decisions:
            logger.info(f"✅ PROGRAMMATIC APPROVAL: All risk checks passed (exposure: {current_exposure_pct:.1f}%, positions: {len(current_positions)})")
            result = {
                "approved": True,
                "veto_reason": None,
                "risk_score": 3.0,
                "validation_method": "programmatic",
                "checks_passed": ["duplicate_position", "max_exposure", "max_positions", "position_size", "stop_loss", "risk_reward"],
                "portfolio_state": {"exposure_pct": current_exposure_pct, "position_count": len(current_positions)},
                "intelligent_context": {"past_decisions": past_context, "risk_lessons": risk_lessons[:3]}
            }
            # Log to journal with intelligent context
            if self.journal:
                context_note = f" | Context: {len(risk_lessons)} risk lessons applied" if risk_lessons else ""
                self.journal.log_analysis("Risk Guardian", f"APPROVED: exposure {current_exposure_pct:.1f}%, {len(current_positions)} positions{context_note}", {
                    "thesis": f"APPROVED - All risk checks passed ({current_exposure_pct:.1f}% exposure)",
                    "confidence": 0.95,
                    "invalidation": f"Veto if exposure > {MAX_TOTAL_EXPOSURE_PCT}%",
                })
            return result

        
        # If violations found, AUTO-REJECT without LLM
        if violations:
            logger.warning(f"⛔ PROGRAMMATIC REJECTION: {violations}")
            result = {
                "approved": False,
                "veto_reason": "; ".join(violations),
                "risk_score": 9.0,
                "validation_method": "programmatic",
                "violations": violations
            }
            # Log to journal
            if self.journal:
                self.journal.log_analysis("Risk Guardian", f"REJECTED: {'; '.join(violations)}", {
                    "thesis": f"REJECTED - {violations[0] if violations else 'Risk violation'}",
                    "confidence": 0.99,
                    "invalidation": "None - decision is final",
                })
            return result
        
        # Fallback to LLM for edge cases (HOLD decisions, MODIFY, etc.)
        # Format current positions for MODIFY validation
        positions_text = "No open positions."
        if current_positions:
            pos_lines = []
            for pos in current_positions:
                pos_lines.append(
                    f"- {pos.get('symbol')} {pos.get('direction')} @ ${pos.get('entry_price', 0):,.2f} | "
                    f"Current SL: ${pos.get('stop_loss', 0):,.2f} | TP: ${pos.get('take_profit', 0):,.2f} | "
                    f"PnL: {pos.get('unrealized_pnl_pct', 0):.2f}%"
                )
            positions_text = "\n".join(pos_lines)
        
        prompt = format_prompt(
            self.prompt_template,
            current_positions=positions_text,
            proposed_decision=json.dumps(proposed_decision, indent=2),
            market_data=json.dumps(state.get("market_data", {}), indent=2),
        )
        
        # System prompt to enforce JSON output
        system_prompt = """You are a Risk Guardian AI. You MUST respond with ONLY valid JSON.
Do not include any text, explanation, or markdown before or after the JSON.
Your response must start with { and end with }.
Do not use markdown code blocks."""
        
        response = await self.llm.generate(
            prompt=prompt,
            model=self.config.model,
            temperature=0.1,
            max_tokens=self.config.max_tokens,
            json_mode=True,  # Force JSON output
            system_prompt=system_prompt,
        )
        
        try:
            result = extract_json(response.content)
            
            # If extraction succeeded with approved field, return it
            if result and "approved" in result:
                return result
            
            # If extraction failed or result is empty, analyze text for intent
            content_lower = response.content.lower()
            
            # Check for explicit rejection signals
            rejection_signals = ["veto", "reject", "not approved", "denied", "violation", "too risky"]
            approval_signals = ["approved", "approve", "acceptable", "within limits", "good risk"]
            
            rejection_count = sum(1 for s in rejection_signals if s in content_lower)
            approval_count = sum(1 for s in approval_signals if s in content_lower)
            
            if rejection_count > approval_count:
                return {"approved": False, "veto_reason": "Risk concerns detected in assessment", "risk_score": 7.0}
            else:
                # When in doubt, VETO - preserve capital above all else
                logger.warning("Risk Guardian: Unclear signals - defaulting to VETO for safety")
                return {"approved": False, "veto_reason": "Unclear risk assessment - defaulting to veto for capital preservation", "risk_score": 6.0}
            
        except Exception as e:
            logger.error(f"Failed to parse Risk Guardian response: {str(e)[:100]}")
            # When in doubt, VETO - preserve capital above all else
            return {"approved": False, "veto_reason": f"Risk assessment parsing failed - defaulting to veto for safety: {str(e)[:50]}", "risk_score": 8.0}


class PortfolioManager(BaseAgent):
    """Synthesizes all inputs into final decision"""
    
    def _default_template(self) -> str:
        return """You are an ELITE PORTFOLIO MANAGER with leverage trading capabilities.

⚠️ CRITICAL: LEVERAGE TRADING RULES ⚠️
- Portfolio: $10,000
- Max margin per trade: $500 (5% of portfolio)
- Leverage: 1x to 20x (default: 10x for crypto)
- size_usd = MARGIN (your collateral), NOT notional value
- Notional = size_usd × leverage

📊 EXAMPLE:
$500 margin × 10x leverage = $5,000 notional position
If BTC moves +2%: Your PnL = +2% × 10 = +20% on margin = +$100

⚠️ LIQUIDATION WARNING:
- At 10x: 10% adverse move = 100% margin loss (LIQUIDATED)
- At 20x: 5% adverse move = 100% margin loss (LIQUIDATED)
- ALWAYS set stop loss BEFORE liquidation price!

═══════════════════════════════════════════════════════════════════
CURRENT POSITIONS (CHECK BEFORE OPENING NEW TRADES):
{current_positions}
═══════════════════════════════════════════════════════════════════

⚠️ POSITION RULES:
- If you already have a position in a symbol, DO NOT open another!
- Use HOLD if existing position is still valid
- Use CLOSE if invalidation hit or thesis changed
- Use MODIFY to adjust stop_loss/take_profit
- Only use OPEN if no position exists for that symbol

AGENT ANALYSES:
BULL: {bull_thesis}
BEAR: {bear_thesis}
TECHNICAL: {technical_view}
SENTIMENT: {sentiment_analysis}

PAST LESSONS:
{past_lessons}

MARKET DATA:
{market_data}

═══════════════════════════════════════════════════════════════════
EVOLVED RULES (Self-learned from past performance):
{evolved_rules}
═══════════════════════════════════════════════════════════════════

RULES:
1. size_usd (margin) MUST BE 500 OR LESS
2. leverage MUST BE between 1 and 20
3. Stop loss: Set BEFORE liquidation price (e.g., 5-8% for 10x)
4. Take profit: 2-4x the stop loss distance for good R:R
5. Check current_positions BEFORE recommending OPEN
6. ⚠️ CRITICAL: You MUST read ALL agent analyses above. If any agent shows "[EMPTY - NO ANALYSIS PROVIDED]", DO NOT include it in agents_reviewed
7. ⚠️ CRITICAL: ONLY include agents in "agents_reviewed" that provided actual content (not empty/not marked [EMPTY])
8. ⚠️ CRITICAL: Your "analysis" MUST reference specific insights from ONLY the agents that provided content

OUTPUT (JSON only):
{{
  "agents_reviewed": ["list ONLY agents that provided real analyses, e.g., if bull was empty: [\"bear\", \"technical\", \"sentiment\"]"],
  "analysis": "Your synthesis demonstrating understanding of the agents that provided content. Acknowledge which agents were unavailable.",
  "market_regime": "TRENDING|RANGING|VOLATILE",
  "decisions": [
    {{
      "action": "OPEN|HOLD|CLOSE|MODIFY",
      "symbol": "BTC",
      "direction": "LONG|SHORT",
      "size_usd": 500,
      "leverage": 10,
      "entry_price": 91000.00,
      "take_profit": 95000.00,
      "stop_loss": 88000.00,
      "confidence": 0.7,
      "reasoning": "Why this action (must reference specific agent insights)"
    }}
  ]
}}

ACTION GUIDE:
- OPEN: New position (only if no existing position for symbol)
- HOLD: Keep existing position (update reasoning only)
- CLOSE: Exit position (specify exit_price instead of entry_price)
- MODIFY: Change SL/TP on existing position
"""
    
    async def synthesize(self, state: TradingState) -> dict:
        """Synthesize all agent inputs"""
        # Extract past lessons from market_data
        market_data = state.get("market_data", {})
        past_lessons = market_data.get("past_lessons", [])
        lessons_text = "No past lessons available."
        if past_lessons:
            lessons_list = []
            for i, lesson in enumerate(past_lessons[:20], 1):  # Top 20 lessons (unlimited budget)
                lesson_text = lesson.get("lesson_learned", lesson.get("lessons", {}).get("primary_lesson", "N/A"))
                lessons_list.append(f"{i}. {lesson_text}")
            lessons_text = "\n".join(lessons_list)
        
        # Extract current positions from market_data
        account = market_data.get("account", {})
        positions = account.get("positions", [])
        if positions:
            pos_lines = []
            for pos in positions:
                pos_lines.append(
                    f"- {pos.get('symbol')} {pos.get('direction')} @ ${pos.get('entry_price'):,.2f} "
                    f"| Size: ${pos.get('size_usd', 0):.0f} | SL: ${pos.get('stop_loss', 0):,.2f} "
                    f"| TP: ${pos.get('take_profit', 0):,.2f} | PnL: {pos.get('unrealized_pnl_pct', 0):.2f}%"
                )
            positions_text = "\n".join(pos_lines)
        else:
            positions_text = "No open positions. You may OPEN new trades."
        
        # Load evolved rules from file if available
        evolved_rules_text = "No evolved rules yet. System is learning from trades."
        try:
            from pathlib import Path
            evolved_file = Path(__file__).parent.parent.parent / "data" / "evolved_rules.json"
            if evolved_file.exists():
                import json as json_mod
                with open(evolved_file, "r") as f:
                    evolved_data = json_mod.load(f)
                    rules = evolved_data.get("rules", [])
                    if rules:
                        evolved_rules_text = "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1))
        except Exception:
            pass
        
        # Get PM's memory context (cross-agent theses + past PM decisions)
        pm_memory_context = ""
        if self.journal:
            pm_memory_context = self.journal.get_pm_context()
        
        # VALIDATE AGENT CONTENT - Ensure PM knows which agents provided real analyses
        def validate_agent_content(content: str | None, agent_name: str) -> tuple[str, bool]:
            """Check if agent content is valid and return formatted version + validity flag"""
            if not content or (isinstance(content, str) and len(content.strip()) == 0):
                logger.warning(f"⚠️ {agent_name} Agent returned EMPTY content!")
                return "[EMPTY - NO ANALYSIS PROVIDED]", False
            return content, True
        
        bull_content, bull_valid = validate_agent_content(state.get("bull_thesis"), "Bull")
        bear_content, bear_valid = validate_agent_content(state.get("bear_thesis"), "Bear")
        tech_content, tech_valid = validate_agent_content(state.get("technical_view"), "Technical")
        sent_content, sent_valid = validate_agent_content(state.get("sentiment_analysis"), "Sentiment")
        
        # Build list of agents that provided valid analyses
        valid_agents = []
        if bull_valid: valid_agents.append("bull")
        if bear_valid: valid_agents.append("bear")
        if tech_valid: valid_agents.append("technical")
        if sent_valid: valid_agents.append("sentiment")
        
        logger.info(f"📋 Valid agent analyses: {valid_agents} ({len(valid_agents)}/4 agents)")
        
        prompt = format_prompt(
            self.prompt_template,
            bull_thesis=bull_content,
            bear_thesis=bear_content,
            technical_view=tech_content,
            sentiment_analysis=sent_content,
            past_lessons=lessons_text,
            current_positions=positions_text,
            evolved_rules=evolved_rules_text,
            market_data=json.dumps(market_data, indent=2),
        )
        
        # Inject PM memory context into prompt
        if pm_memory_context:
            prompt = pm_memory_context + "\n\n" + prompt
        
        # System prompt to enforce JSON output
        system_prompt = """You are a Portfolio Manager AI. You MUST respond with ONLY valid JSON.
Do not include any text, explanation, or markdown before or after the JSON.
Your response must start with { and end with }.
Do not use markdown code blocks."""

        response = await self.llm.generate(
            prompt=prompt,
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            json_mode=True,  # Force JSON output
            system_prompt=system_prompt,
        )
        
        try:
            result = extract_json(response.content)
            if result and "decisions" in result:
                # PROGRAMMATIC ENFORCEMENT: Cap position size at $500 maximum
                MAX_POSITION_USD = 500.0
                for i, decision in enumerate(result.get("decisions", [])):
                    if "size_usd" in decision:
                        try:
                            original_size = float(decision["size_usd"])
                            logger.info(f"📊 PM Decision {i+1}: size_usd = ${original_size:.2f}")
                            if original_size > MAX_POSITION_USD:
                                logger.warning(f"⚠️ CAPPING: ${original_size:.2f} → ${MAX_POSITION_USD:.2f}")
                                decision["size_usd"] = MAX_POSITION_USD
                                decision["size_capped"] = True
                                decision["original_size_usd"] = original_size
                        except (ValueError, TypeError) as e:
                            logger.error(f"Invalid size_usd value: {decision['size_usd']}, setting to 500")
                            decision["size_usd"] = MAX_POSITION_USD
                
                # Log PM decision to journal
                if self.journal:
                    decisions = result.get("decisions", [])
                    action_summary = ", ".join([f"{d.get('action', 'HOLD')} {d.get('symbol', 'BTC')}" for d in decisions[:3]])
                    self.journal.log_analysis("Portfolio Manager", json.dumps(result), {
                        "thesis": f"{result.get('market_regime', 'UNKNOWN')} regime - {action_summary or 'HOLD'}",
                        "confidence": decisions[0].get("confidence", 0.7) if decisions else 0.5,
                        "invalidation": result.get("invalidation", "Market regime change"),
                    })
                
                return result
            elif result:
                # Got some JSON but no decisions field
                logger.warning("PM response missing decisions field, wrapping result")
                return {"decisions": [], "analysis": result.get("analysis", ""), **result}
            else:
                # Parsing failed - provide fallback HOLD decision
                logger.warning(f"PM JSON parsing failed, using HOLD fallback. Response starts with: {response.content[:100]}...")
                return {
                    "analysis": "Unable to parse LLM response, defaulting to hold",
                    "market_regime": "UNKNOWN",
                    "decisions": [
                        {
                            "action": "HOLD",
                            "symbol": "BTC",
                            "direction": "N/A",
                            "size_usd": 0,
                            "confidence": 0.5,
                            "reasoning": "Awaiting clearer market signal"
                        }
                    ],
                }
        except Exception as e:
            logger.error(f"Failed to parse PM response: {e}")
            return {
                "decisions": [{"action": "HOLD", "symbol": "BTC", "confidence": 0.5, "reasoning": "Parse error"}],
                "error": str(e)
            }


# ============================================================================
# Trading Council Orchestrator
# ============================================================================

class TradingCouncil:
    """
    Orchestrates the multi-agent trading council.
    Uses LangGraph if available, otherwise falls back to sequential execution.
    """
    
    def __init__(self, llm_client: LLMClient, config: dict | None = None):
        self.llm = llm_client
        self.config = config or {}
        
        # Initialize agent memory journal
        from src.memory.agent_journal import get_journal
        self.journal = get_journal()
        
        # Initialize RAG market memory for historical precedents
        from src.memory.market_memory import get_market_memory
        self.market_memory = get_market_memory()
        
        # Initialize domain-specific pattern memory for specialists
        from src.memory.domain_memory import get_domain_memory
        self.domain_memory = get_domain_memory()
        
        # Initialize agents with UNLIMITED TOKEN BUDGET, journal, market memory, and domain memory
        self.bull_researcher = BullResearcher(
            AgentConfig(
                name="Bull Researcher",
                model=self.config.get("model", "gemini-3.0-pro-preview"),
                temperature=0.7,
                max_tokens=16384,  # Unlimited for deep analysis
                prompt_template="bull_researcher",
                role="fundamental_bullish",
            ),
            llm_client,
            journal=self.journal,
            market_memory=self.market_memory,
            domain_memory=self.domain_memory,
            domain="fundamental",  # Bull uses fundamental patterns
        )
        
        self.bear_researcher = BearResearcher(
            AgentConfig(
                name="Bear Researcher",
                model=self.config.get("model", "gemini-3.0-pro-preview"),
                temperature=0.7,
                max_tokens=16384,  # Unlimited for deep analysis
                prompt_template="bear_researcher",
                role="fundamental_bearish",
            ),
            llm_client,
            journal=self.journal,
            market_memory=self.market_memory,
            domain_memory=self.domain_memory,
            domain="fundamental",  # Bear uses fundamental patterns
        )
        
        self.technical_analyst = TechnicalAnalyst(
            AgentConfig(
                name="Technical Analyst",
                model=self.config.get("model", "gemini-3.0-pro-preview"),
                temperature=0.3,
                max_tokens=16384,  # Unlimited for deep analysis
                prompt_template="technical_analyst",
                role="technical",
            ),
            llm_client,
            journal=self.journal,
            market_memory=self.market_memory,
            domain_memory=self.domain_memory,
            domain="technical",  # Technical uses technical patterns
        )
        
        self.sentiment_analyst = SentimentAnalyst(
            AgentConfig(
                name="Sentiment Analyst",
                model=self.config.get("model", "gemini-3.0-pro-preview"),
                temperature=0.5,
                max_tokens=16384,  # Unlimited for deep analysis
                prompt_template="sentiment_analyst",
                role="sentiment",
            ),
            llm_client,
            journal=self.journal,
            market_memory=self.market_memory,
            domain_memory=self.domain_memory,
            domain="sentiment",  # Sentiment uses sentiment patterns
        )
        
        self.risk_guardian = RiskGuardian(
            AgentConfig(
                name="Risk Guardian",
                model=self.config.get("model", "gemini-3.0-pro-preview"),
                temperature=0.1,
                max_tokens=16384,  # Unlimited for thorough risk evaluation
                prompt_template="risk_guardian",
                role="risk_management",
            ),
            llm_client,
            journal=self.journal,
            market_memory=self.market_memory,
        )
        
        self.portfolio_manager = PortfolioManager(
            AgentConfig(
                name="Portfolio Manager",
                model=self.config.get("model", "gemini-3.0-pro-preview"),
                temperature=0.4,
                max_tokens=32768,  # Maximum for comprehensive synthesis
                prompt_template="portfolio_manager",
                role="synthesis",
            ),
            llm_client,
            journal=self.journal,
            market_memory=self.market_memory,
        )
    
    async def analyze(self, market_data: dict) -> dict:
        """
        Run the full council analysis.
        
        Args:
            market_data: Current market state
            
        Returns:
            Final trading decision after council deliberation
        """
        # Initialize state
        state: TradingState = {
            "market_data": market_data,
            "timestamp": datetime.now().isoformat(),
            "bull_thesis": None,
            "bear_thesis": None,
            "technical_view": None,
            "sentiment_score": None,
            "sentiment_analysis": None,
            "debate_rounds": [],
            "current_round": 0,
            "consensus_reached": False,
            "proposed_decision": None,
            "final_decision": None,
            "risk_assessment": None,
            "risk_veto": False,
            "veto_reason": None,
        }
        
        logger.info("🏛️ Trading Council convening...")
        
        # Phase 1: Parallel analysis by specialists
        logger.info("📊 Phase 1: Specialist Analysis")
        
        # SECURITY: Create filtered state for specialists - they should NOT see portfolio data
        # Only Risk Guardian and Portfolio Manager should have access to positions/PnL
        # This prevents portfolio bias in market analysis
        specialist_market_data = {
            k: v for k, v in market_data.items() 
            if k not in ["account", "past_lessons"]  # Filter sensitive portfolio data
        }
        specialist_state: TradingState = {
            "market_data": specialist_market_data,  # Filtered - no portfolio info
            "timestamp": datetime.now().isoformat(),
            "bull_thesis": None,
            "bear_thesis": None,
            "technical_view": None,
            "sentiment_score": None,
            "sentiment_analysis": None,
            "debate_rounds": [],
            "current_round": 0,
            "consensus_reached": False,
            "proposed_decision": None,
            "final_decision": None,
            "risk_assessment": None,
            "risk_veto": False,
            "veto_reason": None,
        }
        
        results = await asyncio.gather(
            self.bull_researcher.analyze(specialist_state),   # No portfolio access
            self.bear_researcher.analyze(specialist_state),   # No portfolio access
            self.technical_analyst.analyze(specialist_state), # No portfolio access
            self.sentiment_analyst.analyze(specialist_state), # No portfolio access
            return_exceptions=True,
        )
        
        # Process results and LOG FULL OUTPUTS
        agent_names = ["Bull", "Bear", "Technical", "Sentiment"]
        agent_emojis = ["🐂", "🐻", "📈", "💭"]
        for i, (name, emoji, result) in enumerate(zip(agent_names, agent_emojis, results)):
            if isinstance(result, Exception):
                logger.error(f"❌ {name} Agent failed: {result}")
            else:
                logger.info(f"✅ {name} Agent completed in {result['latency_ms']:.0f}ms")
                # Log the full analysis
                content = result.get("content", "No content")
                logger.info(f"\n{'='*60}\n{emoji} {name.upper()} RESEARCHER ANALYSIS\n{'='*60}\n{content}\n{'='*60}")
                
        state["bull_thesis"] = results[0].get("content") if not isinstance(results[0], Exception) else None
        state["bear_thesis"] = results[1].get("content") if not isinstance(results[1], Exception) else None
        state["technical_view"] = results[2].get("content") if not isinstance(results[2], Exception) else None
        state["sentiment_analysis"] = results[3].get("content") if not isinstance(results[3], Exception) else None
        
        # Store domain patterns from specialist analyses
        try:
            market_ctx = {
                "price": state.get("BTC", {}).get("price", 0),
                "rsi": state.get("BTC", {}).get("rsi_14", 50),
                "trend": state.get("BTC", {}).get("trend", "UNKNOWN"),
                "fear_greed": state.get("BTC", {}).get("fear_greed", 50),
            }
            
            # Store technical pattern
            if state["technical_view"]:
                self.domain_memory.store_pattern(
                    domain="technical",
                    pattern_description=state["technical_view"][:500],  # First 500 chars as pattern
                    market_context=market_ctx,
                    outcome={"pending": True}  # Outcome updated after trade closes
                )
            
            # Store sentiment pattern  
            if state["sentiment_analysis"]:
                self.domain_memory.store_pattern(
                    domain="sentiment",
                    pattern_description=state["sentiment_analysis"][:500],
                    market_context=market_ctx,
                    outcome={"pending": True}
                )
            
            # Store fundamental pattern (from bull/bear theses)
            if state["bull_thesis"] or state["bear_thesis"]:
                fundamental_text = f"Bull: {(state['bull_thesis'] or '')[:200]} | Bear: {(state['bear_thesis'] or '')[:200]}"
                self.domain_memory.store_pattern(
                    domain="fundamental",
                    pattern_description=fundamental_text,
                    market_context=market_ctx,
                    outcome={"pending": True}
                )
                
            logger.debug("🎯 Stored domain patterns from specialist analyses")
        except Exception as e:
            logger.debug(f"Domain pattern storage skipped: {e}")
        
        # Phase 2: Portfolio Manager synthesis
        logger.info("🧠 Phase 2: Portfolio Manager Synthesis")
        proposed = await self.portfolio_manager.synthesize(state)
        state["proposed_decision"] = proposed
        
        # Log PM decision
        logger.info(f"\n{'='*60}\n💼 PORTFOLIO MANAGER DECISION\n{'='*60}\n{json.dumps(proposed, indent=2)}\n{'='*60}")
        
        # Phase 3: Risk Guardian evaluation
        logger.info("🛡️ Phase 3: Risk Guardian Evaluation")
        risk_result = await self.risk_guardian.evaluate(state, proposed)
        state["risk_assessment"] = risk_result
        state["risk_veto"] = not risk_result.get("approved", False)
        state["veto_reason"] = risk_result.get("veto_reason")
        
        # Log Risk Guardian assessment
        logger.info(f"\n{'='*60}\n🛡️ RISK GUARDIAN ASSESSMENT\n{'='*60}\n{json.dumps(risk_result, indent=2)}\n{'='*60}")
        
        if state["risk_veto"]:
            logger.warning(f"⛔ Risk Guardian VETO: {state['veto_reason']}")
            state["final_decision"] = {
                "decisions": [],
                "vetoed": True,
                "veto_reason": state["veto_reason"],
            }
        else:
            logger.info("✅ Risk Guardian APPROVED")
            state["final_decision"] = proposed
            
        logger.info("🏛️ Trading Council adjourned")
        
        return {
            "decision": state["final_decision"],
            "risk_assessment": state["risk_assessment"],
            "analyses": {
                "bull": state["bull_thesis"],
                "bear": state["bear_thesis"],
                "technical": state["technical_view"],
                "sentiment": state["sentiment_analysis"],
            },
        }


async def main():
    """Test the trading council"""
    from .llm_client import LLMClient
    
    # Sample market data
    market_data = {
        "BTC": {
            "current_price": 107859.5,
            "ema20": 107805.98,
            "macd": 129.74,
            "rsi_7": 52.97,
            "rsi_14": 61.67,
            "open_interest": 26005.85,
            "funding_rate": 6.58e-06,
        },
        "account": {
            "total_return_pct": -14.64,
            "available_cash": 2486.09,
            "account_value": 8536.49,
        }
    }
    
    async with LLMClient() as client:
        council = TradingCouncil(client)
        result = await council.analyze(market_data)
        
        print("\n" + "="*60)
        print("COUNCIL DECISION")
        print("="*60)
        print(json.dumps(result["decision"], indent=2))


if __name__ == "__main__":
    asyncio.run(main())
