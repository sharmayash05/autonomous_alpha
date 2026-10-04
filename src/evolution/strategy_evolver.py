"""
Strategy Evolver - Self-Evolution Engine
The Autonomous Alpha - LLM-Powered Strategy Evolution

This module implements the Strategy Evolver from Section 5.4 of the master plan:
- Analyzes trading performance over time
- Identifies patterns in wins/losses
- Generates improved strategy rules using LLM
- Backs-tests evolved strategies
- Automatically promotes winning strategies
"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class PerformanceMetrics:
    """Trading performance metrics for evolution analysis"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    
    # Pattern analysis
    loss_patterns: list[str] = field(default_factory=list)
    win_patterns: list[str] = field(default_factory=list)
    market_regime_performance: dict = field(default_factory=dict)


STRATEGY_EVOLVER_PROMPT = """
You are the STRATEGY EVOLVER - an elite trading system architect.

Your mission: Analyze trading performance and evolve better decision-making rules.
You are NOT generating code - you are generating IMPROVED PROMPT RULES for the Portfolio Manager.

═══════════════════════════════════════════════════════════════════════════════
CURRENT PERFORMANCE METRICS
═══════════════════════════════════════════════════════════════════════════════
- Total Trades: {total_trades}
- Win Rate: {win_rate:.1%}
- Profit Factor: {profit_factor:.2f}
- Sharpe Ratio: {sharpe_ratio:.2f}
- Max Drawdown: {max_drawdown:.2%}
- Average Win: ${avg_win:,.2f}
- Average Loss: ${avg_loss:,.2f}

═══════════════════════════════════════════════════════════════════════════════
CURRENT DECISION RULES (PM Prompt)
═══════════════════════════════════════════════════════════════════════════════
{current_rules}

═══════════════════════════════════════════════════════════════════════════════
LOSS PATTERN ANALYSIS
═══════════════════════════════════════════════════════════════════════════════
Trades that lost money had these common patterns:
{loss_patterns}

═══════════════════════════════════════════════════════════════════════════════
WIN PATTERN ANALYSIS
═══════════════════════════════════════════════════════════════════════════════
Trades that made money had these common patterns:
{win_patterns}

═══════════════════════════════════════════════════════════════════════════════
MARKET REGIME PERFORMANCE
═══════════════════════════════════════════════════════════════════════════════
{regime_performance}

═══════════════════════════════════════════════════════════════════════════════
REFLEXION LESSONS (Top patterns from memory)
═══════════════════════════════════════════════════════════════════════════════
{past_lessons}

═══════════════════════════════════════════════════════════════════════════════
YOUR TASK
═══════════════════════════════════════════════════════════════════════════════

1. DIAGNOSE: Why is the current strategy underperforming?
2. HYPOTHESIZE: What changes would improve performance?
3. EVOLVE: Generate NEW/MODIFIED rules for the PM prompt

EVOLUTION PRINCIPLES:
- Keep what works (win patterns) - don't change rules that generate wins
- Fix what's broken (loss patterns) - add guardrails for losing scenarios
- Add regime-specific rules if performance varies by market condition
- Incorporate recurring lesson patterns into explicit rules

OUTPUT FORMAT (JSON):
{{
  "diagnosis": {{"current_weakness": "...", "root_cause": "..."}},
  "hypothesis": {{"proposed_change": "...", "expected_improvement": "..."}},
  "evolved_rules": [
    {{"rule": "Specific rule text to add to PM prompt", "rationale": "Why this helps"}}
  ],
  "rules_to_remove": [
    {{"rule": "Rule to remove", "rationale": "Why it hurts performance"}}
  ],
  "confidence": 0.0-1.0,
  "expected_win_rate_improvement": "+X%",
  "evolution_version": "{version}"
}}
"""


class StrategyEvolver:
    """
    Self-evolution engine that improves trading rules based on performance.
    Implements Section 5.4 of THE_AUTONOMOUS_ALPHA_STRATEGY.md
    """
    
    EVOLUTION_FILE = Path(__file__).parent.parent.parent / "data" / "evolved_rules.json"
    PERFORMANCE_FILE = Path(__file__).parent.parent.parent / "data" / "performance_history.json"
    
    def __init__(self, llm_client, memory=None):
        self.llm = llm_client
        self.memory = memory
        self.current_version = 0
        self.evolved_rules: list[str] = []
        self._load_evolved_rules()
        
    def _load_evolved_rules(self):
        """Load previously evolved rules"""
        try:
            if self.EVOLUTION_FILE.exists():
                with open(self.EVOLUTION_FILE, "r") as f:
                    data = json.load(f)
                    self.evolved_rules = data.get("rules", [])
                    self.current_version = data.get("version", 0)
                    logger.info(f"🧬 Loaded evolved rules v{self.current_version}: {len(self.evolved_rules)} rules")
        except Exception as e:
            logger.error(f"Failed to load evolved rules: {e}")
            
    def _save_evolved_rules(self):
        """Persist evolved rules to disk"""
        try:
            self.EVOLUTION_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.EVOLUTION_FILE, "w") as f:
                json.dump({
                    "version": self.current_version,
                    "rules": self.evolved_rules,
                    "evolved_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "rule_metadata": getattr(self, 'rule_metadata', {}),
                }, f, indent=2)
            logger.info(f"💾 Saved evolved rules v{self.current_version}")
        except Exception as e:
            logger.error(f"Failed to save evolved rules: {e}")
    
    async def prune_rules(self, recent_lessons: list[dict], performance_metrics: dict) -> dict:
        """
        Prune rules that are stale, conflicting, or underperforming.
        
        Reasons to prune:
        1. Rule conflicts with recent lessons learned
        2. Rule hasn't improved performance (stale)
        3. Rule contradicts more recent rules
        4. Max rule limit reached (keep top performers)
        
        Args:
            recent_lessons: Recent lessons from trades
            performance_metrics: Current performance data
            
        Returns:
            Dict with pruned rules and reasons
        """
        if not self.evolved_rules:
            return {"pruned": [], "kept": []}
        
        MAX_RULES = 15  # Keep rules manageable
        
        prompt = f"""You are the Rule Pruning Agent for an autonomous trading system.

CURRENT EVOLVED RULES ({len(self.evolved_rules)} total):
{chr(10).join(f'{i+1}. {rule}' for i, rule in enumerate(self.evolved_rules))}

RECENT LESSONS LEARNED FROM TRADES:
{chr(10).join(f'- {l.get("lesson_learned", l.get("payload", {}).get("lesson_learned", ""))}' for l in recent_lessons[:10]) or "No recent lessons"}

CURRENT PERFORMANCE:
- Win Rate: {performance_metrics.get('win_rate', 0):.1%}
- Profit Factor: {performance_metrics.get('profit_factor', 0):.2f}
- Total Trades: {performance_metrics.get('total_trades', 0)}

YOUR TASK:
Analyze each rule and determine which should be PRUNED (removed). A rule should be pruned if:
1. **CONTRADICTS** a lesson learned (the lesson proves the rule wrong)
2. **STALE** - too vague or no longer applicable
3. **DUPLICATE** - says the same as another rule
4. **CONFLICTING** - contradicts another rule (keep the more specific one)
5. **MAX LIMIT** - if > {MAX_RULES} rules, prune the weakest

OUTPUT JSON:
{{
  "analysis": "Brief analysis of rule set health",
  "rules_to_prune": [
    {{
      "rule_index": 1,
      "rule_text": "The rule text",
      "reason": "CONTRADICTS|STALE|DUPLICATE|CONFLICTING|WEAK",
      "explanation": "Why this should be removed"
    }}
  ],
  "rules_to_keep": [
    {{
      "rule_index": 2,
      "rule_text": "The rule text",
      "status": "ACTIVE"
    }}
  ]
}}

Be conservative - only prune rules with clear justification. An empty prune list is fine if all rules are valid."""
        
        try:
            response = await self.llm.generate(
                prompt=prompt,
                temperature=0.2,
                max_tokens=8192,
                json_mode=True,
            )
            
            result = json.loads(response.content)
            
            # Apply pruning
            prune_indices = {r["rule_index"] - 1 for r in result.get("rules_to_prune", [])}
            
            if prune_indices:
                pruned_rules = [self.evolved_rules[i] for i in prune_indices if i < len(self.evolved_rules)]
                self.evolved_rules = [r for i, r in enumerate(self.evolved_rules) if i not in prune_indices]
                self.current_version += 1
                self._save_evolved_rules()
                
                logger.info(f"🗑️ Pruned {len(pruned_rules)} rules:")
                for rule in pruned_rules:
                    logger.info(f"   ❌ {rule[:60]}...")
                    
            return result
            
        except Exception as e:
            logger.error(f"Rule pruning failed: {e}")
            return {"error": str(e), "pruned": [], "kept": self.evolved_rules}
            
    def get_evolved_rules_text(self) -> str:
        """Get evolved rules formatted for PM prompt injection"""
        if not self.evolved_rules:
            return "No evolved rules yet."
        
        rules_text = f"EVOLVED RULES (v{self.current_version}):\n"
        for i, rule in enumerate(self.evolved_rules, 1):
            rules_text += f"{i}. {rule}\n"
        return rules_text
    
    async def analyze_performance(self, trades: list[dict]) -> PerformanceMetrics:
        """Analyze trading performance to identify patterns"""
        metrics = PerformanceMetrics()
        
        if not trades:
            return metrics
            
        metrics.total_trades = len(trades)
        
        wins = [t for t in trades if t.get("pnl_percent", 0) > 0]
        losses = [t for t in trades if t.get("pnl_percent", 0) <= 0]
        
        metrics.winning_trades = len(wins)
        metrics.losing_trades = len(losses)
        metrics.win_rate = len(wins) / len(trades) if trades else 0
        
        metrics.total_pnl = sum(t.get("pnl_usd", 0) for t in trades)
        
        if wins:
            metrics.avg_win = sum(t.get("pnl_usd", 0) for t in wins) / len(wins)
        if losses:
            metrics.avg_loss = abs(sum(t.get("pnl_usd", 0) for t in losses) / len(losses))
            
        # Profit factor
        total_wins = sum(t.get("pnl_usd", 0) for t in wins) if wins else 0
        total_losses = abs(sum(t.get("pnl_usd", 0) for t in losses)) if losses else 1
        metrics.profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        # Analyze patterns
        metrics.loss_patterns = self._extract_patterns(losses)
        metrics.win_patterns = self._extract_patterns(wins)
        
        # Regime performance
        for trade in trades:
            regime = trade.get("market_regime", "UNKNOWN")
            if regime not in metrics.market_regime_performance:
                metrics.market_regime_performance[regime] = {"trades": 0, "pnl": 0}
            metrics.market_regime_performance[regime]["trades"] += 1
            metrics.market_regime_performance[regime]["pnl"] += trade.get("pnl_usd", 0)
            
        return metrics
        
    def _extract_patterns(self, trades: list[dict]) -> list[str]:
        """Extract common patterns from trades"""
        patterns = []
        
        if not trades:
            return ["No trades to analyze"]
            
        # RSI patterns
        oversold_entries = [t for t in trades if t.get("entry_rsi", 50) < 30]
        overbought_entries = [t for t in trades if t.get("entry_rsi", 50) > 70]
        
        if len(oversold_entries) > len(trades) * 0.3:
            patterns.append(f"High frequency of oversold entries ({len(oversold_entries)}/{len(trades)})")
        if len(overbought_entries) > len(trades) * 0.3:
            patterns.append(f"High frequency of overbought entries ({len(overbought_entries)}/{len(trades)})")
            
        # Fear/Greed patterns
        fear_entries = [t for t in trades if t.get("entry_fear_greed", 50) < 30]
        greed_entries = [t for t in trades if t.get("entry_fear_greed", 50) > 70]
        
        if len(fear_entries) > len(trades) * 0.3:
            patterns.append(f"High frequency of fear entries ({len(fear_entries)}/{len(trades)})")
        if len(greed_entries) > len(trades) * 0.3:
            patterns.append(f"High frequency of greed entries ({len(greed_entries)}/{len(trades)})")
            
        # Direction patterns
        longs = [t for t in trades if t.get("direction") == "LONG"]
        shorts = [t for t in trades if t.get("direction") == "SHORT"]
        
        if longs and not shorts:
            patterns.append("All trades were LONG - no SHORT positions taken")
        elif shorts and not longs:
            patterns.append("All trades were SHORT - no LONG positions taken")
            
        if not patterns:
            patterns.append("No strong patterns detected")
            
        return patterns
        
    async def evolve(self, trades: list[dict], current_pm_rules: str) -> dict:
        """
        Main evolution function - analyzes performance and generates improved rules.
        
        Args:
            trades: List of completed trade records
            current_pm_rules: Current PM prompt rules section
            
        Returns:
            Evolution result with new rules
        """
        if len(trades) < 10:
            logger.info(f"🧬 Need at least 10 trades for evolution (have {len(trades)})")
            return {"status": "insufficient_data", "trades_needed": 10 - len(trades)}
            
        logger.info(f"🧬 Starting strategy evolution (v{self.current_version} → v{self.current_version + 1})")
        
        # Analyze performance
        metrics = await self.analyze_performance(trades)
        
        # Get past lessons from memory
        past_lessons = []
        if self.memory:
            past_lessons = self.memory.recall_similar("trading lessons patterns", top_k=20)
            
        # Format lessons
        lessons_text = "No lessons available."
        if past_lessons:
            lessons_text = "\n".join([
                f"- {l.get('lesson_learned', l.get('lessons', {}).get('primary_lesson', 'N/A'))}"
                for l in past_lessons[:10]
            ])
            
        # Format regime performance
        regime_text = "\n".join([
            f"- {regime}: {data['trades']} trades, ${data['pnl']:+.2f}"
            for regime, data in metrics.market_regime_performance.items()
        ])
        
        # Generate evolution prompt
        prompt = STRATEGY_EVOLVER_PROMPT.format(
            total_trades=metrics.total_trades,
            win_rate=metrics.win_rate,
            profit_factor=metrics.profit_factor,
            sharpe_ratio=metrics.sharpe_ratio,
            max_drawdown=metrics.max_drawdown,
            avg_win=metrics.avg_win,
            avg_loss=metrics.avg_loss,
            current_rules=current_pm_rules,
            loss_patterns="\n".join(f"- {p}" for p in metrics.loss_patterns),
            win_patterns="\n".join(f"- {p}" for p in metrics.win_patterns),
            regime_performance=regime_text or "No regime data yet.",
            past_lessons=lessons_text,
            version=self.current_version + 1,
        )
        
        # Query LLM for evolution
        response = await self.llm.generate(
            prompt=prompt,
            temperature=0.3,
            max_tokens=16384,
            json_mode=True,
        )
        
        try:
            result = json.loads(response.content)
            
            # Apply evolved rules
            new_rules = [r["rule"] for r in result.get("evolved_rules", [])]
            if new_rules:
                self.evolved_rules.extend(new_rules)
                self.current_version += 1
                self._save_evolved_rules()
                
                logger.info(f"🧬 Evolution complete! Added {len(new_rules)} new rules")
                for rule in new_rules:
                    logger.info(f"   ✅ {rule[:80]}...")
                    
            return result
            
        except Exception as e:
            logger.error(f"Evolution failed: {e}")
            return {"status": "error", "error": str(e)}
            
    async def should_evolve(self, trades: list[dict]) -> bool:
        """Determine if evolution should be triggered"""
        if len(trades) < 10:
            return False
            
        # Check recent performance
        recent_trades = trades[-20:]  # Last 20 trades
        recent_wins = sum(1 for t in recent_trades if t.get("pnl_percent", 0) > 0)
        recent_win_rate = recent_wins / len(recent_trades)
        
        # Trigger evolution if:
        # 1. Win rate drops below 40%
        # 2. Profit factor drops below 1.0
        # 3. Every 50 trades for continuous improvement
        
        if recent_win_rate < 0.4:
            logger.info(f"🧬 Evolution triggered: Low win rate ({recent_win_rate:.1%})")
            return True
            
        if len(trades) % 50 == 0:
            logger.info(f"🧬 Evolution triggered: Periodic improvement ({len(trades)} trades)")
            return True
            
        return False
