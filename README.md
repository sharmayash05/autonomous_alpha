# Autonomous Alpha: LLM-Centric Multi-Agent Trading System

> A fully-autonomous, LLM-centric, self-evolving multi-agent cryptocurrency trading system.
> Six specialist agents debate every decision, four memory subsystems keep the brain stateful,
> a Reflexion loop scores every closed trade A–F, and a Strategy Evolver rewrites its own
> playbook from realised P&L. Designed to run unattended on a single VPS, 24/7.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)]()

---

## Table of Contents

1. [What This Is](#1-what-this-is)
2. [End-to-End Architecture](#2-end-to-end-architecture)
3. [The Trading Loop (cycle-by-cycle)](#3-the-trading-loop-cycle-by-cycle)
4. [Multi-Agent Council](#4-multi-agent-council)
5. [The Four Memory Systems](#5-the-four-memory-systems)
6. [Reflexion Learning Loop](#6-reflexion-learning-loop)
7. [Strategy Evolver (self-rewriting rules)](#7-strategy-evolver)
8. [Portfolio Manager Internals](#8-portfolio-manager-internals)
9. [Risk Guardian (programmatic + LLM veto)](#9-risk-guardian)
10. [Data Pipeline](#10-data-pipeline)
11. [Technical Indicators](#11-technical-indicators)
12. [Executor (paper & live)](#12-executor)
13. [Dashboard](#13-dashboard)
14. [Prometheus Metrics & Alerts](#14-metrics--alerts)
15. [Configuration Reference](#15-configuration-reference)
16. [Environment Variables](#16-environment-variables)
17. [CLI & Entry Points](#17-cli--entry-points)
18. [Full File-by-File Tree](#18-full-file-by-file-tree)
19. [Data Files Inventory](#19-data-files-inventory)
20. [Local Setup](#20-local-setup)
21. [Docker Deployment](#21-docker-deployment)
22. [Vultr VPS Deployment](#22-vultr-vps-deployment)
23. [Testing & Diagnostics](#23-testing--diagnostics)
24. [Memory Pruning Cadence](#24-memory-pruning-cadence)
25. [Troubleshooting](#25-troubleshooting)
26. [Disclaimer & License](#26-disclaimer--license)

---

## Results (Binance Testnet)
18-day run: 39 trades, 59% win rate, 2.54 profit factor, 1.18% max drawdown.
Testnet only. Not financial advice.

## Team & Contributions
Major Project I, B.Tech CSE (AIML), SOIT, RGPV (July - Dec 2026).
Team: Yash Sharma, Ayush , Naman.

Yash Sharma: Data Engineer. Built the async data ingestion pipelines,
feature vectors, and embedding/Qdrant retrieval layer.


## 1. What This Is

The Autonomous Alpha is **not** a rule-based bot. It is an LLM cortex wrapped in a real
trading framework:

- A **council of six LLM specialists** (Bull, Bear, Technical, Sentiment, Risk, Portfolio
  Manager) analyses the market every *N* minutes.
- Decisions are **veto-gated** by a programmatic + LLM Risk Guardian.
- Four persistent **memory subsystems** (Agent Journal, Domain Memory, Market Memory,
  Reflexion Lessons) eliminate the LLM's "goldfish" amnesia and inject historical precedents,
  failed theses, A–F graded post-mortems and confirmed market patterns back into every prompt.
- A **Reflexion** module performs an 8-section forensic on every closed trade, grades it
  A–F, extracts a single-sentence lesson, and stores it in an in-memory **Qdrant** vector DB
  (with a JSON fallback) for RAG retrieval next cycle.
- A **Strategy Evolver** monitors trade history and, when win-rate drops below 40% (or every
  50 trades), uses the LLM to *rewrite the Portfolio Manager's own rule set*.
- A **PortfolioManager** with realistic margin accounting (fees, leverage, partial closes,
  trailing stops, liquidation tracking, draw-down high-water mark) handles execution.
- A **real-time Flask + Socket.IO dashboard** at `:5000` streams everything live.
- **Prometheus** metrics at `:8080` plus optional **Telegram / Discord** alerts.

The default LLM is `gemini-3.0-pro-preview` served through an OpenAI-compatible proxy
at `http://localhost:3000/gemini-antigravity/v1` (baked in as the default in
`src/core/llm_client.py` and `config/agents.yaml` — overridable via env vars). Any
OpenAI-compatible endpoint works: Ollama, OpenAI, LM Studio, vLLM, etc.

---

## 2. End-to-End Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          THE AUTONOMOUS ALPHA — DATA FLOW                              │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│   ┌─────────────────────┐    ┌──────────────────┐    ┌──────────────────────────┐     │
│   │ RealTimeDataFetcher │    │ NewsAggregator   │    │ SentimentAggregator      │     │
│   │ Binance: price,     │    │ CryptoPanic,     │    │ Fear & Greed, Funding    │     │
│   │ funding, OI, L/S,   │ +  │ AlphaVantage,    │ +  │ rate (weighted aggregate)│     │
│   │ top traders, liq,   │    │ Cointelegraph,   │    │                          │     │
│   │ 4h+1d MTF, NVT,     │    │ Coindesk,        │    └──────────────────────────┘     │
│   │ Google Trends       │    │ Decrypt, RSS     │                                      │
│   └──────────┬──────────┘    └────────┬─────────┘                                      │
│              │                        │                                                 │
│              └────────────┬───────────┘                                                 │
│                           ▼                                                             │
│              ┌─────────────────────────┐                                                │
│              │  market_data dict       │  (rich JSON: ~50KB of context per cycle)       │
│              └────────────┬────────────┘                                                │
│                           │                                                             │
│         ┌─────────────────┼─────────────────────────────────────────┐                  │
│         ▼                 ▼                                          ▼                  │
│  ┌──────────────┐  ┌──────────────────────────────────────────┐  ┌──────────────┐      │
│  │ AgentJournal │  │             TRADING COUNCIL              │  │ MarketMemory │      │
│  │ last 5/agent │◄─┤  PHASE 1 (parallel): Bull / Bear /       │─►│ 8-dim vector │      │
│  │ active thesis│  │           Technical / Sentiment          │  │ Qdrant inmem │      │
│  │ portfolio    │  │  PHASE 2:  PortfolioManager.synthesize() │  └──────────────┘      │
│  │ history,     │  │  PHASE 3:  RiskGuardian (prog + LLM veto)│                        │
│  │ mistakes log │  └────────────┬─────────────────────────────┘                        │
│  └──────┬───────┘               │                                                       │
│         │              ┌────────┴────────┐                                              │
│         │              │  DomainMemory   │  3 vector lanes (technical / sentiment /     │
│         │              │  MiniLM 384-dim │  fundamental). Patterns scored & pruned by   │
│         │              └─────────────────┘  realised PnL outcome.                       │
│         │                                                                                │
│         ▼                                                                                │
│   ┌─────────────────────────────────┐                                                   │
│   │     PortfolioManager            │  ────────► PaperExecutor / ExchangeExecutor       │
│   │  open/close, SL/TP, trailing,   │            (CCXT Binance futures testnet)         │
│   │  liquidation, partial close,    │                                                    │
│   │  HWM drawdown, equity curve     │                                                    │
│   └────────────┬────────────────────┘                                                   │
│                │ on_trade_closed callback                                                │
│                ▼                                                                         │
│   ┌──────────────────────────┐     ┌──────────────────────────┐                        │
│   │   ReflectorAgent         │ ──► │  TradingMemory (Qdrant)  │                        │
│   │   8-section forensic     │     │  trade_lessons coll.     │                        │
│   │   A–F grade + lesson     │     │  embed → RAG next cycle  │                        │
│   └──────────────────────────┘     └──────────────────────────┘                        │
│                │                                                                         │
│                ▼                                                                         │
│   ┌──────────────────────────┐                                                          │
│   │   StrategyEvolver        │  Win-rate < 40% OR every 50 trades                       │
│   │   rewrites PM rules      │  → mutates PortfolioManager.prompt_template              │
│   └──────────────────────────┘                                                          │
│                                                                                          │
│   Side-cars:                                                                             │
│     • Dashboard  http://0.0.0.0:5000   (Flask + SocketIO)                               │
│     • Prometheus http://0.0.0.0:8080/metrics                                            │
│     • AlertManager → Telegram / Discord                                                  │
│     • Logs       logs/trading_*.log, logs/trading_*.json, logs/trades.log               │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. The Trading Loop (cycle-by-cycle)

`run_trading_loop()` in [src/main.py](src/main.py) executes the following on every interval
(default 5 min, configurable via `--interval` or `TRADING_INTERVAL`):

1. **Journal tick** — `journal.increment_invocation()` and `log_portfolio_snapshot()` capture
   equity, cash, unrealised/realised PnL, exposure %, every open position.
2. **Fetch market data** — `RealTimeDataFetcher.fetch_all(["BTC","ETH"])` returns a dict
   containing 13+ concurrent feeds (see §10). News fetcher appends ~50 KB of headlines.
3. **Update live prices** on every open position *before* serialising account state to the
   LLM so the council sees fresh unrealised P&L (not stale numbers).
4. **Recall lessons** — `reflexion.get_relevant_lessons(query)` queries the Qdrant
   `trade_lessons` collection by the embedding of `"BTC at $X with RSI Y and Z trend"`
   and injects top-K lessons into `market_data["past_lessons"]`.
5. **Per-position housekeeping** for every open position:
   - **Liquidation** check (margin loss ≥ 100% → immediate close, reason `liquidation`).
   - **Stop-loss** trigger (long: price ≤ SL / short: price ≥ SL).
   - **Take-profit** trigger (mirror logic).
   - **Trailing stop** — once unrealised P&L on margin exceeds **1.0%**, the SL is moved to
     **0.5%** behind the current price; it can only move in the favourable direction
     (locks in gains).
   - **Stale exit** — if held > **48 h** and |unrealised P&L| < **5%**, force-close
     (reason `stale_position`).
6. **Save portfolio** — `portfolio_manager.save()` plus a legacy dict written to
   `data/portfolio.json` for the dashboard.
7. **Council analyse** — `await council.analyze(market_data)` runs Phase 1 → 2 → 3
   (see §4). Returns `{"decision": …, "analyses": {bull, bear, technical, sentiment},
   "risk_assessment": …}`.
8. **Apply decisions** — for each entry in `decision["decisions"]`:
   - `OPEN`  → `portfolio_manager.open_position(...)` with SL/TP/leverage; quantity is
     derived from `size_usd × leverage / entry_price`.
   - `CLOSE` → `portfolio_manager.close_position(...)`; supports `close_percent` for
     partial exits. Triggers the `on_trade_closed` callback (see step 11).
   - `MODIFY` → mutates `pos.stop_loss` / `pos.take_profit`.
   - `HOLD`  → logged.
   Every decision is also `journal.log_pm_decision(d)` so it appears in next cycle's PM
   context.
9. **Veto path** — if Risk Guardian vetoed, `journal.log_mistake(...)` so future cycles
   see the failure.
10. **Snapshot market memory** — `market_memory.store_snapshot(market_data, decision, …)`
    persists an 8-dim vector for future similarity search, then
    `market_memory.reconcile_snapshots(btc_price)` walks back through unreconciled snapshots
    older than 24 h and tags each `CORRECT` / `INCORRECT` based on actual price movement.
11. **Trade-closed callback** (`on_trade_closed_callback` registered with the
    PortfolioManager) — for every closed trade:
    - Builds a `TradeRecord` and fires `reflexion.process_completed_trade(record)` as a
      background task → 8-section forensic → graded lesson → stored in Qdrant.
    - `market_memory.update_outcome(snapshot_timestamp, pnl_percent, direction)` ties the
      snapshot to its realised P&L.
    - `domain_memory.update_recent_pattern_outcomes(domain, pnl)` rewards/penalises every
      pattern recently surfaced by the specialists.
12. **Strategy evolution** (after a `CLOSE`) — if `evolver.should_evolve(trade_history)`
    returns true (win-rate < 40% OR every 50 trades), `evolver.evolve(history, pm_rules)`
    rewrites the Portfolio Manager's prompt template with new rules.
13. **Dashboard broadcast** — `update_dashboard({...})` pushes everything (portfolio,
    market data, all four agent analyses, PM decision, risk assessment, lessons,
    journal stats, evolved rules, memory stats, trade history) over Socket.IO and to
    `data/dashboard_state.json`.
14. **Periodic pruning** — every **10 invocations** (≈ every 50 min at 5-min cadence)
    the loop runs: `memory.prune_lessons(llm, max=50)`,
    `domain_memory.prune_stale_patterns(max_age=30d, max=100/lane)`,
    `domain_memory.prune_patterns_intelligent(llm, max=100/lane)`,
    `market_memory.prune_snapshots_quality(max=500)`, and
    `evolver.prune_rules(recent_lessons, perf_metrics)`.
15. **Sleep** for `interval_minutes × 60` seconds. Errors are caught, logged with the full
    stack, and the loop sleeps 60 s before retrying.

---

## 4. Multi-Agent Council

Implemented in [src/core/council.py](src/core/council.py). The council is **three phases**:

### Phase 1 — Specialists (parallel, asyncio.gather)

| Agent              | Temp | Role               | Sees                                                              |
|--------------------|------|--------------------|-------------------------------------------------------------------|
| Bull Researcher    | 0.7  | fundamental long   | filtered market_data + journal context + domain `fundamental` + lessons (filtered) |
| Bear Researcher    | 0.7  | fundamental short  | same as Bull (different prompt)                                                    |
| Technical Analyst  | 0.3  | pure price/volume  | market_data + domain `technical` patterns + filtered lessons                       |
| Sentiment Analyst  | 0.5  | crowd & social     | market_data + domain `sentiment` patterns + filtered lessons                       |

Specialist state is **strictly filtered** — they never see `account`, `past_lessons` (raw)
or other agents' theses, preventing leakage and groupthink. Every specialist call uses
`BaseAgent.analyze()` which:

1. Loads its `prompts/<role>.md` template.
2. Injects fresh **journal context** (last 5 of that agent's own analyses + active thesis +
   repetition warning if loop detected).
3. Queries **market memory** for the top-3 most similar past snapshots → injects them as
   *historical precedents*.
4. Queries **domain memory** for the top-3 most relevant patterns in that domain.
5. Queries **trading memory** with domain-keyword-filtered lesson retrieval.
6. Builds the final prompt, calls `LLMClient.generate_with_think(...)`, parses JSON via
   `extract_json()` which has **5 fallback strategies** (code-fence, balanced-brace scan,
   greedy regex, salvage, default skeleton).
7. Updates the journal: stores the analysis, sets/updates `active_thesis` if confidence
   ≥ 0.6, detects repetition (≥ 70% similarity to last analysis + same action → loop
   warning logged for next cycle).

### Phase 2 — Portfolio Manager synthesis

`PortfolioManager.synthesize(state)` (in council.py — distinct from the accounting class
in `portfolio.py`):

- Sees **all** specialist analyses, full account state, raw past lessons, journal `PM
  context` (past 5 PM decisions + portfolio history + strategic plan).
- Prompt is `prompts/system_prompt.md` (the "Trading Cortex" — see file for the full
  protocol: macro → position review → order flow → opportunity scan → risk → synthesis).
- Returns JSON with `analysis`, `market_regime` (TRENDING/RANGING/VOLATILE/UNKNOWN),
  `decisions[]` (each with `action`, `symbol`, `direction`, `size_usd`, `entry_price`,
  `take_profit`, `stop_loss`, `leverage`, `confidence`, `reasoning`, `invalidation`),
  `portfolio_assessment`, `reflexion_notes`.
- Every `size_usd` is **programmatically capped at $500** regardless of what the LLM said.

### Phase 3 — Risk Guardian (two-stage gate)

`RiskGuardian.evaluate(decision, account)`:

1. **Programmatic pre-validation** (`_programmatic_check`) — instant deterministic veto for:
   - `size_usd > 500` → veto `size_exceeds_500`
   - total exposure > 30% of equity → veto `exposure_30pct`
   - `leverage > 20` → veto `leverage_20x`
   - > 5 open positions → veto `max_positions`
   - duplicate position on same symbol → veto `duplicate_position`
   - missing `stop_loss` → veto `no_stop_loss`
   - risk-reward ratio < 1.0 → veto `low_rr`
2. **LLM Risk Guardian** (temperature 0.1) — if the programmatic gate passes, the LLM is
   prompted with `prompts/risk_guardian.md` to apply soft rules (volatility, correlation,
   liquidation proximity, funding extremes, OI spikes) and can still veto with reasoning.

A veto sets `decision["vetoed"] = True`, stores `veto_reason`, and increments the
Prometheus `RISK_VETOS` counter labelled by reason.

### LangGraph optional path

If `langgraph` is installed, the council uses a state graph for orchestration; otherwise
it falls back to plain sequential `asyncio.gather` + manual phase calls. Both paths are
functionally identical.

---

## 5. The Four Memory Systems

All four memory systems are independent singletons (`get_agent_journal()`,
`get_domain_memory()`, `get_market_memory()`, `TradingMemory()`), all use **in-memory
Qdrant** with a **JSON file fallback** so the system works even without `qdrant-client`
installed.

### 5.1 Agent Journal — `data/agent_journal.json`

[src/memory/agent_journal.py](src/memory/agent_journal.py)

Per-agent rolling history (last **5** analyses each). Each entry stores `timestamp`,
`text`, `action`, `confidence`, `thesis_summary`.

Additional state:

- **`active_thesis`** per agent (set when confidence ≥ 0.6). Decays **2% per hour**, floored
  at 50%. Cleared automatically when position closes (with reason).
- **Repetition detection** (`detect_repetition`) — compares the current analysis to the
  last one; if action matches **and** Jaccard word similarity > 70%, the next prompt is
  injected with a `⚠️ REPETITION DETECTED` warning so the LLM breaks state loops.
- **PM strategic plan** — `update_pm_strategy(market_regime, thesis)` keeps a single
  `current_plan` that survives across cycles.
- **Mistakes log** (`log_mistake`) — every Risk Guardian veto plus any explicit error.
- **Portfolio history** — last 20 hourly equity snapshots (used in PM prompts).
- **`get_pm_context()`** assembles: every specialist's last summary + active thesis +
  PM's last 5 decisions + portfolio history + the strategic plan + mistakes log.

### 5.2 Domain Memory — `data/domain_patterns.json`

[src/memory/domain_memory.py](src/memory/domain_memory.py)

**Three** independent vector lanes, embedded with `sentence-transformers/all-MiniLM-L6-v2`
(384-dim):

| Lane          | Search-text builder uses…                                              |
|---------------|------------------------------------------------------------------------|
| `technical`   | RSI / trend / pattern / EMA cross / MACD divergence / S-R levels      |
| `sentiment`   | Fear&Greed / social / news polarity / funding rate / long-short ratio |
| `fundamental` | event / actor / event_type (ETF flows, macro, regulatory)             |

Patterns are stored when a specialist explicitly returns a pattern, then later **rewarded
or penalised** by `update_recent_pattern_outcomes(domain, pnl_percent)` when the trade
closes. Pruning happens via:

- `prune_stale_patterns(max_age_days=30, max_per_domain=100)` — age & outcome scoring.
- `prune_patterns_intelligent(llm, max_per_domain=100)` — LLM quality scoring (deletes the
  worst-performing low-confidence patterns).

### 5.3 Market Memory — `data/market_memory.json`

[src/memory/market_memory.py](src/memory/market_memory.py)

A **bespoke 8-dimensional vector** is computed for every market snapshot:

```
[ price_norm, rsi/100, fear_greed/100, trend_enc,
  ema20_distance, ema50_distance, hour_norm, day_norm ]
```

| Method                            | What it does                                                          |
|-----------------------------------|-----------------------------------------------------------------------|
| `store_snapshot(market_data, decision, position_open)` | Persist new snapshot + decision label.        |
| `query_similar(market_data, min_age_hours=1, top_k=3)` | Return historical precedents matching now.    |
| `reconcile_snapshots(current_price)` | Walk all unreconciled snapshots ≥ 24 h old, compute 24-h forward Δ, tag `CORRECT` / `INCORRECT` based on the original decision direction. |
| `update_outcome(timestamp, pnl_percent, direction)` | Bind a snapshot to its actual realised P&L.  |
| `prune_snapshots_quality(max=500)` | Quality score = reconciled +10, CORRECT +20, INCORRECT +5, plus a recency bonus; lowest-scoring snapshots evicted first. |

### 5.4 Trading Memory / Reflexion — `data/lessons.json`

[src/memory/reflector.py](src/memory/reflector.py)

Qdrant collection `trade_lessons`. Each lesson is the output of the `ReflectorAgent` (see
§6) and contains: `trade_id`, `trade_grade` (A–F), `thesis_flaw`, `missed_signals[]`,
`lesson_learned`, `embedding_text`, `timestamp`, `pnl_percent`, full reflection JSON.

Semantic de-duplication: if a candidate lesson shares > **80% word overlap** with an
existing one, the duplicate is skipped. Retrieval has two flavours:

- `recall_similar(query, top_k)` — generic vector search.
- `recall_domain_lessons(query, domain, top_k)` — additionally filters by domain
  keywords (technical: `rsi/ema/macd/atr`; sentiment: `fear/fud/fomo/funding`;
  fundamental: `microstrategy/etf/halving/regulation`).

LLM-driven pruning (`prune_lessons(llm, max=50)`) scores each lesson on impact,
recency and quality, then keeps only the top-N.

---

## 6. Reflexion Learning Loop

`ReflectorAgent.REFLECTION_PROMPT` runs an **8-section forensic** on every closed trade:

1. **Thesis** — was the original conviction valid? what evidence supported it?
2. **Timing** — was the entry early/late? what was the optimal entry?
3. **Signals** — which indicators called it right? which missed it?
4. **Risk** — was sizing appropriate? was SL too tight / TP too greedy?
5. **Regime** — what was the broader market regime? did it shift mid-trade?
6. **Execution** — slippage, fee impact, partial close strategy.
7. **Counterfactual** — would HOLD / opposite trade have done better?
8. **Pattern** — extractable, generalisable pattern for future trades.

Each section is graded **A–F**. An overall grade is derived. A one-sentence
`lesson_learned` is emitted and embedded into Qdrant for RAG.

Reflection is fired asynchronously from the `on_trade_closed_callback` in `src/main.py`
so the trading loop never blocks on it.

---

## 7. Strategy Evolver

[src/evolution/strategy_evolver.py](src/evolution/strategy_evolver.py) — `data/evolved_rules.json`

`should_evolve(history)` returns true when:

- recent win-rate < **40%**, **OR**
- total closed trades is a multiple of **50**.

`evolve(history, current_pm_rules)`:

1. **`analyze_performance(history)`** — slices history by `market_regime`, by symbol, by
   direction; computes win-rate, avg PnL, profit factor.
2. Calls the LLM with `STRATEGY_EVOLVER_PROMPT` to propose **new rules** addressing the
   weakest regime/symbol/direction.
3. Versions the rule set (`current_version += 1`), stores `evolved_rules[]`, and
   **mutates `council.portfolio_manager.prompt_template`** so the next PM call sees the
   new rules at runtime — no restart needed.

`prune_rules(recent_lessons, perf_metrics)` calls the LLM to delete contradictory or
provably-bad rules.

---

## 8. Portfolio Manager Internals

[src/core/portfolio.py](src/core/portfolio.py) — `data/portfolio_state.json`

| Dataclass         | Key fields                                                                                     |
|-------------------|------------------------------------------------------------------------------------------------|
| `Position`        | `symbol`, `side`, `quantity`, `entry_price`, `leverage`, `margin`, `stop_loss`, `take_profit`, `current_price`, `entry_time`, `market_context_entry`, `unrealized_pnl_*` (computed), `notional_value`, `liquidation_price` |
| `ClosedTrade`     | All `Position` fields + `exit_price`, `exit_time`, `exit_reason`, `pnl_usd`, `pnl_percent`, `fees_paid`, `market_context_exit`, `snapshot_timestamp` |
| `PortfolioState`  | `initial_balance` ($10,000), `cash_balance`, `positions{}`, `closed_trades[]`, `realized_pnl`, `high_water_mark`, `max_drawdown_percent`, `consecutive_losses`, `daily_pnl`, `daily_reset_date`, `equity_history[]` (hourly), computed properties `total_equity`, `unrealized_pnl`, `total_pnl_usd/percent`, `exposure_percent` |

Methods of interest:

- `open_position(symbol, side, quantity, price, leverage, stop_loss, take_profit, market_context_entry)` — debits margin, applies a **0.04% taker fee**, blocks if cash insufficient or symbol already open.
- `close_position(symbol, price, exit_reason, market_context_exit, close_percent=100, snapshot_timestamp=None)` — supports partial closes, applies fees, updates `consecutive_losses`/`high_water_mark`/`max_drawdown`, appends `ClosedTrade`, and fires `on_trade_closed(closed_trade)` callback.
- `update_price(symbol, price)` — refresh `current_price` for unrealised P&L.
- `save() / load()` — JSON round-trip including `equity_history`.
- `get_stats()` — totals consumed by the trading loop and dashboard.

Defaults: **$10,000** initial, **$500** max margin per position (programmatically enforced
by Risk Guardian), **1–20×** leverage, **0.04%** fees in/out.

---

## 9. Risk Guardian

See §4 Phase 3. Hard rules (programmatic):

| Rule                                 | Value      | Veto code               |
|--------------------------------------|------------|-------------------------|
| Max margin / position                | $500       | `size_exceeds_500`      |
| Max total exposure                   | 30% equity | `exposure_30pct`        |
| Max leverage                         | 20×        | `leverage_20x`          |
| Max concurrent positions             | 5          | `max_positions`         |
| Duplicate symbol                     | blocked    | `duplicate_position`    |
| Missing stop-loss                    | required   | `no_stop_loss`          |
| Risk-reward ratio                    | ≥ 1.0      | `low_rr`                |

Soft rules (LLM-evaluated, from `config/risk_params.yaml`):

- Volatility adjustment (ATR > 2× average → reduce size 50%).
- Correlation check (max 0.7 between assets, max 3 correlated positions).
- Liquidation proximity (block if any position within 5% of liquidation).
- Funding rate extremes (> 0.1%).
- Open interest spikes (> 20% in 24 h).

Circuit breakers (from `config/risk_params.yaml`, monitored by the loop):

- 3 consecutive losses → pause 4 hours.
- Daily loss > 3% → pause until next day.
- Drawdown > 10% from peak → emergency stop.

---

## 10. Data Pipeline

### 10.1 `RealTimeDataFetcher` — [src/data/realtime_fetcher.py](src/data/realtime_fetcher.py)

`fetch_all(symbols)` issues 13+ concurrent fetches:

- **Spot price + 24 h stats** (Binance `/api/v3/ticker/24hr`).
- **Futures funding rate** (`/fapi/v1/premiumIndex`).
- **Open interest** + historical OI (`/futures/data/openInterestHist`).
- **Long/short global ratio** + **top trader ratio** (`/futures/data/topLongShortPositionRatio`).
- Interpreted into buckets: `EXTREME_LONG > 3.0`, `CROWDED_LONG > 2.0`, `BALANCED 0.7–1.5`, `CROWDED_SHORT < 0.5`, `EXTREME_SHORT < 0.33`.
- **Recent liquidations** (`/fapi/v1/allForceOrders`).
- **Multi-timeframe trend** (4 h + 1 d klines) → label confluence `STRONG_BULLISH` /
  `BULLISH` / `MIXED` / `CONFLICTING` / `BEARISH` / `STRONG_BEARISH`.
- **NVT ratio** (network value to transactions, on-chain proxy).
- **Fear & Greed Index** (alternative.me).
- **Google Trends** social interest score.
- **Order-book depth-of-market** (top-20 depth snapshot).
- Computed indicators (EMA20, EMA50, RSI7, RSI14, MACD histogram, ATR, Bollinger bands)
  via `src/utils/indicators.py`.

### 10.2 `NewsAggregator` — [src/data/news_fetcher.py](src/data/news_fetcher.py)

Async parallel pulls from:

- **CryptoPanic** (`CRYPTOPANIC_API_KEY`)
- **AlphaVantage** market news (`ALPHAVANTAGE_API_KEY`)
- RSS: `cointelegraph.com`, `coindesk.com`, `decrypt.co`, `bitcoinist.com`

`format_for_llm(articles, max_chars=100_000)` returns a markdown block that respects the
budget.

### 10.3 `SentimentAggregator` — [src/data/sentiment_fetcher.py](src/data/sentiment_fetcher.py)

Weighted aggregate sentiment:

- Fear & Greed → weight **30%**
- Funding rate (sign-inverted: crowded long = bearish) → weight **40%**
- Other social channels → remaining weight

### 10.4 `BinanceHistoricalFetcher` — [src/data/historical_fetcher.py](src/data/historical_fetcher.py)

Paginated `fetch_range(symbol, timeframe, start, end)` for backtests, with on-disk CSV
caching (`get_with_cache`). `YahooFinanceFetcher` is included as a fallback source.

### 10.5 `BinanceWebSocket` — [src/data/websocket_feed.py](src/data/websocket_feed.py)

Streams `<symbol>@trade`, `<symbol>@depth20@100ms`, `<symbol>@kline_1m`. Maintains an
`OrderBook` dataclass with `best_bid/ask`, `mid_price`, `spread`, plus a rolling
**Order-Flow Imbalance** deque(maxlen=1000) used by the Technical Analyst. Auto-reconnect
with exponential backoff.

---

## 11. Technical Indicators

[src/utils/indicators.py](src/utils/indicators.py)

Pure-NumPy implementations (no `ta-lib` runtime dep):

| Function                                                    | Notes                            |
|-------------------------------------------------------------|----------------------------------|
| `sma(data, period)`                                         | simple MA                        |
| `ema(data, period)`                                         | Wilder-style, multiplier `2/(p+1)` |
| `rsi(data, period=14)`                                      | smoothed-average RSI             |
| `macd(data, 12, 26, 9)` → `MACD(macd_line, signal, histogram)` |                              |
| `atr(high, low, close, 14)`                                 | true-range EMA                   |
| `bollinger_bands(data, 20, 2.0)` → `BollingerBands(upper, middle, lower, bandwidth)` |     |
| `stochastic(high, low, close, 14, 3)` → `Stochastic(k, d)`  |                                  |
| `vwap(h, l, c, v)`                                          | cumulative VWAP                  |
| `obv(close, volume)`                                        | on-balance volume                |
| `cmf(h, l, c, v, 20)`                                       | Chaikin Money Flow               |
| `pivot_points(h, l, c)` → R3/R2/R1/Pivot/S1/S2/S3           | classic floor traders' pivots    |

`TechnicalAnalyzer(prices, high, low, volume)` is a convenience wrapper:

- `.get_all()` returns dict of every indicator's latest value.
- `.get_signal()` produces a composite **STRONG_LONG / WEAK_LONG / NEUTRAL / WEAK_SHORT
  / STRONG_SHORT** score from RSI, MACD-histogram, and EMA20/EMA50 alignment.

---

## 12. Executor

[src/core/executor.py](src/core/executor.py)

Two implementations behind a shared interface:

### `PaperExecutor`

- Synthetic fills with **5 bps slippage** and **4 bps fees**.
- Tracks positions, cash, fills, stats in memory.
- Used by `--mode paper` (default).

### `ExchangeExecutor`

- **CCXT** binding to Binance USDT-M futures.
- Reads `BINANCE_API_KEY` / `BINANCE_API_SECRET` from env.
- `config/exchanges.yaml` selects **testnet** by default.
- `set_leverage`, `place_order` (market / limit / stop), `close_position`,
  `get_positions`, `get_balance`.

### `Backtester`

[src/core/backtester.py](src/core/backtester.py) — `BacktestEngine.run(strategy, df)` iterates bars,
calls the strategy on each, accumulates equity, computes annualised Sharpe assuming hourly
bars (`sqrt(252 × 24)`), and pretty-prints a `BacktestResult` ASCII summary box.

> The `--mode backtest` CLI handler in `src/main.py` currently prints a "coming soon"
> notice; use Freqtrade's engine via `src/strategies/autonomous_alpha.py` for production
> backtests today.

### Freqtrade integration

[src/strategies/autonomous_alpha.py](src/strategies/autonomous_alpha.py) — `AutonomousAlphaStrategy(IStrategy)`:

- `can_short = True`, `interface_version = 3`.
- **`custom_stoploss`** dynamic ATR-based (2× ATR).
- **`confirm_trade_entry`** blocks a candidate trade if any recent matching Reflexion
  lesson has `trade_grade ∈ {D, F}` with similarity > 0.8.
- `StandaloneStrategy` variant runs without Freqtrade installed.

---

## 13. Dashboard

[src/dashboard/server.py](src/dashboard/server.py) + [src/dashboard/templates/index.html](src/dashboard/templates/index.html)

Flask + Flask-SocketIO, threaded, served on **`http://0.0.0.0:5000`**.

| Route                  | Purpose                                                                 |
|------------------------|-------------------------------------------------------------------------|
| `GET /`                | Modern dark-glass UI (Inter font, animated gradient background)         |
| `GET /api/status`      | Full live snapshot (portfolio + agents + decision + memory + journal)   |
| `GET /api/live`        | Reads `data/dashboard_state.json` (cross-thread sync)                   |
| `GET /api/memory`      | Unified stats for all 4 memory subsystems                               |
| `GET /api/portfolio`   | Just the portfolio dict                                                 |
| `GET /api/lessons`     | All stored Reflexion lessons                                            |
| `GET /api/evolved_rules` | Current evolved PM rules + version                                    |
| `GET /health`          | Liveness probe (used by the Dockerfile HEALTHCHECK)                     |
| `WS /socket.io/...`    | Push updates on every trading loop tick                                 |

The HTML uses a 12-column glass-morphism grid, Socket.IO live updates, status badges
(online/offline), and a polling fallback that reloads every 30 s if WS drops.

---

## 14. Metrics & Alerts

### Prometheus — [src/utils/metrics.py](src/utils/metrics.py)

Exposed on **`http://0.0.0.0:8080/metrics`** (port configurable via `METRICS_PORT`).
Scraped by Prometheus container (see [monitoring/prometheus.yml](monitoring/prometheus.yml)).

| Metric                                | Type       | Labels                          |
|---------------------------------------|------------|---------------------------------|
| `trading_trades_total`                | Counter    | symbol, direction, outcome      |
| `trading_trade_pnl_percent`           | Histogram  | symbol, direction               |
| `trading_position_value_usd`          | Gauge      | symbol, direction               |
| `trading_portfolio_value_usd`         | Gauge      | –                               |
| `trading_portfolio_pnl_percent`       | Gauge      | –                               |
| `trading_llm_requests_total`          | Counter    | model, agent, status            |
| `trading_llm_latency_seconds`         | Histogram  | model, agent                    |
| `trading_llm_tokens_total`            | Counter    | model, type                     |
| `trading_council_decisions_total`     | Counter    | action, vetoed                  |
| `trading_council_latency_seconds`     | Histogram  | –                               |
| `trading_risk_vetos_total`            | Counter    | reason                          |
| `trading_drawdown_current_percent`    | Gauge      | –                               |
| `trading_system`                      | Info       | version, name, start_time       |
| `trading_heartbeat_timestamp`         | Gauge      | –                               |
| `trading_invocations_total`           | Counter    | –                               |

A `@track_llm_latency(model, agent)` decorator (sync + async variants) records latency
on any LLM call.

### Alerts — [src/utils/logging.py](src/utils/logging.py)

`AlertManager` fans out to `TelegramAlerts` and `DiscordAlerts` in parallel.

| Helper                                                                       | When fired                       |
|------------------------------------------------------------------------------|----------------------------------|
| `alerts.trade_opened(symbol, side, quantity, price, leverage)`               | new position                     |
| `alerts.trade_closed(symbol, side, pnl_usd, pnl_pct, reason)`                | closed trade                     |
| `alerts.risk_warning(message, data)`                                         | soft-rule warning                |
| `alerts.system_error(error, details)`                                        | uncaught exception, LLM failure  |

Custom handlers can be registered with `alerts.add_handler(callable)`.

### Logging

`setup_logging()` configures three sinks:

- **Console** — colourised loguru.
- `logs/trading_{date}.log` — human readable, 10 MB rotation, 1 week retention.
- `logs/trading_{date}.json` — JSON-serialised for analysis.
- `logs/trades.log` — filtered to records bound with `trade=True`, monthly rotation.

---

## 15. Configuration Reference

### `config/agents.yaml`

Per-agent `model`, `temperature`, `max_tokens`, `role`, `description`. All six agents
default to `gemini-3.0-pro-preview`. Temperatures: Bull/Bear 0.7, Technical 0.3,
Sentiment 0.5, Risk 0.1, PM 0.4. PM `max_tokens = 32768`, others 16384.

Council parameters: `max_debate_rounds: 10`, `min_consensus_threshold: 0.6`,
`debate_timeout_seconds: 120`.

`endpoints.llm_api` is the OpenAI-compatible base URL; `endpoints.api_key` is baked in
as a fallback if no env var is set.

### `config/exchanges.yaml`

`primary_exchange: binance`. Binance enabled, **testnet: true** by default, six pairs:
`BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT, DOGE/USDT`. Timeframes
`1m, 5m, 15m, 1h, 4h, 1d`. Rate limits 1200 req/min, 10 orders/sec. Bybit and OANDA
stubs included but disabled. WebSocket: 5 reconnect attempts, 5 s delay, 30 s heartbeat.

### `config/risk_params.yaml`

Full hard-rule and soft-rule schema (covered in §9). Kelly sizing: fractional Kelly at
**0.25**, min position $50, max $10,000 (the in-code Risk Guardian still caps each entry
to $500). ATR-based stop-loss 2× ATR, max 5% SL. Take-profit: 2:1 R:R default + partial
levels `[{1.5%: 30%}, {2.5%: 40%}]`, remaining 30% rides trailing stop. Circuit breakers
3 consecutive losses → 4 h pause; 3% daily loss breaker; 3 system errors → pause.

---

## 16. Environment Variables

| Variable                    | Purpose                                              | Default                                                |
|-----------------------------|------------------------------------------------------|--------------------------------------------------------|
| `LLM_BASE_URL`              | OpenAI-compatible base URL                           | `http://localhost:3000/gemini-antigravity/v1`         |
| `LLM_API_KEY`               | Bearer token                                         | `123456` (loader) / `your_llm_api_key` (client) |
| `LLM_MODEL`                 | Default model name                                   | `gemini-3.0-pro-preview`                              |
| `TRADING_MODE`              | `paper` \| `live`                                    | `paper`                                                |
| `TRADING_INTERVAL`          | minutes between cycles                               | `5`                                                    |
| `LOG_LEVEL`                 | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`            | `INFO`                                                 |
| `METRICS_PORT`              | Prometheus port                                      | `8080`                                                 |
| `BINANCE_API_KEY` / `_SECRET` | live-trading credentials                            | unset                                                  |
| `BYBIT_API_KEY` / `_SECRET` | optional                                             | unset                                                  |
| `OANDA_API_KEY` / `OANDA_ACCOUNT_ID` | optional (forex)                            | unset                                                  |
| `CRYPTOPANIC_API_KEY`       | enable CryptoPanic news                              | unset                                                  |
| `ALPHAVANTAGE_API_KEY`      | enable AlphaVantage news                             | unset                                                  |
| `TWITTER_BEARER_TOKEN`      | optional social sentiment                            | unset                                                  |
| `REDDIT_CLIENT_ID` / `_SECRET` | optional Reddit polling                           | unset                                                  |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | enable Telegram alerts                  | unset                                                  |
| `DISCORD_WEBHOOK_URL`       | enable Discord alerts                                | unset                                                  |
| `GRAFANA_PASSWORD`          | docker-compose Grafana admin password                | `admin`                                                |

Put them in a `.env` file at the repo root — `python-dotenv` loads it automatically.

---

## 17. CLI & Entry Points

### Primary CLI — `python -m src.main`

```text
--mode {paper,live,backtest,health}   Operating mode (default: health)
--interval N                          Minutes between cycles (default: 5)
--start YYYY-MM-DD                    Backtest start date
--end YYYY-MM-DD                      Backtest end date
--config PATH                         Path to config directory (default: ./config)
```

Examples:

```powershell
# Health check (no trading, just verifies LLM/config/memory)
python -m src.main --mode health

# Paper trade every 5 minutes
python -m src.main --mode paper --interval 5

# Live trade every 3 minutes (REAL money — testnet recommended first)
python -m src.main --mode live --interval 3
```

### Other entry points

| Script                                 | Purpose                                                              |
|----------------------------------------|----------------------------------------------------------------------|
| [start_autonomous_alpha.py](start_autonomous_alpha.py) | Simplified launcher that boots a minimal dashboard + paper loop in one process (no Unicode). |
| [test_llm.py](test_llm.py)             | Quick parallel-request test against the LLM endpoint.                |
| [stress_test_api.py](stress_test_api.py) | Comprehensive 6-phase stress test of the LLM proxy (connectivity, parallelism 2/4/6/8/10, JSON mode, long prompts, agent simulation). |
| [view_lessons.py](view_lessons.py)     | Pretty-prints every stored Reflexion lesson with grade + PnL.        |
| [run.bat](run.bat) / [run.sh](run.sh)  | Cross-platform venv + deps + launch wrapper.                         |
| [setup.sh](setup.sh)                   | Bare-Linux Vultr bootstrapper (installs Docker + Compose + firewall). |
| [upload_to_vps.bat](upload_to_vps.bat) | SCP push of `src/`, `config/`, `prompts/`, `monitoring/`, Docker files. |

---

## 18. Full File-by-File Tree

```
.
├── README.md                         This file
├── DEPLOYMENT.md                     Vultr VPS step-by-step
├── pyproject.toml                    Hatch build, ruff/mypy/pytest, Python 3.12
├── requirements.txt                  Full pip requirements
├── Dockerfile                        Multi-stage Python 3.11-slim, non-root user
├── docker-compose.yml                Stack: trading-agent + qdrant + prometheus + grafana
├── run.bat / run.sh                  Local launchers (Windows / Unix)
├── setup.sh                          VPS bootstrapper
├── upload_to_vps.bat                 SCP deploy helper
├── start_autonomous_alpha.py         All-in-one paper trader + mini dashboard
├── test_llm.py                       LLM parallel-request smoke test
├── stress_test_api.py                Full LLM proxy stress test
├── view_lessons.py                   Lessons inspector
├── available_models.txt              UTF-16 dump of the LLM proxy `/models` response
├── config/
│   ├── agents.yaml                   Per-agent model / temp / max_tokens
│   ├── exchanges.yaml                Binance/Bybit/OANDA + pairs + rate limits
│   └── risk_params.yaml              Hard rules / soft rules / Kelly / partials / breakers
├── prompts/
│   ├── system_prompt.md              PM "Trading Cortex" master prompt
│   ├── bull_researcher.md            Bull thesis specialist
│   ├── bear_researcher.md            Bear risks specialist
│   ├── technical_analyst.md          Pure TA specialist
│   ├── sentiment_analyst.md          Crowd / social specialist
│   └── risk_guardian.md              Veto agent prompt
├── data/                             Auto-created persistent state
│   ├── agent_journal.json            Per-agent rolling memory
│   ├── domain_patterns.json          Domain pattern fallback storage
│   ├── domain_memory/                Qdrant on-disk
│   ├── market_memory.json            Market snapshot fallback
│   ├── market_memory/                Qdrant on-disk
│   ├── lessons.json                  Reflexion lessons fallback
│   ├── qdrant_lessons/               Qdrant on-disk
│   ├── evolved_rules.json            Strategy Evolver versioned rules
│   ├── portfolio.json                Legacy dict (dashboard compatibility)
│   ├── portfolio_state.json          PortfolioManager canonical state
│   └── dashboard_state.json          Cross-thread dashboard payload
├── logs/                             Loguru sinks (rotation enabled)
├── monitoring/
│   └── prometheus.yml                Scrape config (self, trading-agent:8080, qdrant:6333)
├── reports/
│   ├── codebase_file_summary.tsv     File-by-file synopsis
│   ├── codebase_line_ratings.tsv     Per-line ratings (dev artefact)
│   └── codebase_rating_rubric.txt    Rubric used for the above
├── src/
│   ├── __init__.py
│   ├── main.py                       Entry point + trading loop
│   ├── agents/__init__.py            (reserved for future split-out)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── llm_client.py             OpenAI-compatible async client + retry
│   │   ├── council.py                Multi-agent orchestration (3 phases)
│   │   ├── portfolio.py              PortfolioManager + Position/ClosedTrade
│   │   ├── executor.py               Paper + CCXT executors
│   │   └── backtester.py             BacktestEngine, BacktestResult
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── agent_journal.py          Agent journal singleton
│   │   ├── domain_memory.py          3-lane vector domain memory
│   │   ├── market_memory.py          8-dim market snapshot RAG
│   │   └── reflector.py              ReflectorAgent + TradingMemory + ReflexionLoop
│   ├── data/
│   │   ├── __init__.py
│   │   ├── realtime_fetcher.py       Binance / F&G / OI / NVT / Google Trends
│   │   ├── news_fetcher.py           CryptoPanic / AlphaVantage / RSS
│   │   ├── sentiment_fetcher.py      Weighted sentiment aggregator
│   │   ├── historical_fetcher.py     Paginated klines + Yahoo fallback
│   │   └── websocket_feed.py         Binance WS trades/depth/kline + OFI
│   ├── evolution/
│   │   ├── __init__.py
│   │   └── strategy_evolver.py       Self-rewriting PM rules
│   ├── strategies/
│   │   ├── __init__.py
│   │   └── autonomous_alpha.py       Freqtrade IStrategy + StandaloneStrategy
│   ├── dashboard/
│   │   ├── __init__.py
│   │   ├── server.py                 Flask + SocketIO + REST + WS
│   │   └── templates/
│   │       └── index.html            Glass UI front-end
│   └── utils/
│       ├── __init__.py
│       ├── indicators.py             SMA/EMA/RSI/MACD/ATR/BB/Stoch/VWAP/OBV/CMF/Pivots + TechnicalAnalyzer
│       ├── config_loader.py          Pydantic Config tree + env override
│       ├── logging.py                setup_logging + Telegram/Discord + AlertManager
│       └── metrics.py                Prometheus exporters + decorators
└── tests/
    ├── __init__.py
    └── test_integration.py           Pytest-asyncio integration suite
```

---

## 19. Data Files Inventory

| File                              | Owner                       | Lifecycle                                          |
|-----------------------------------|-----------------------------|----------------------------------------------------|
| `data/agent_journal.json`         | `AgentJournal`              | Rolling, autosaves on every entry                  |
| `data/domain_patterns.json`       | `DomainMemory` (fallback)   | Pruned every 10 invocations                        |
| `data/domain_memory/`             | Qdrant on-disk              | Three collections (patterns_technical/sentiment/fundamental) |
| `data/market_memory.json`         | `MarketMemory` (fallback)   | Pruned by quality every 10 invocations             |
| `data/market_memory/`             | Qdrant on-disk              | Collection `market_snapshots`                      |
| `data/lessons.json`               | `TradingMemory` (fallback)  | LLM-pruned every 10 invocations                    |
| `data/qdrant_lessons/`            | Qdrant on-disk              | Collection `trade_lessons`                         |
| `data/evolved_rules.json`         | `StrategyEvolver`           | Versioned, mutated on evolve()                     |
| `data/portfolio_state.json`       | `PortfolioManager` (canonical) | Saved every cycle and on every position event  |
| `data/portfolio.json`             | Legacy dict for dashboard   | Mirror of state, written by `save_portfolio_legacy` |
| `data/dashboard_state.json`       | Dashboard server            | Cross-thread snapshot for `/api/live`              |

---

## 20. Local Setup

### Prerequisites

- Python **3.10+** (3.12 recommended; `pyproject.toml` pins `>=3.12`).
- 8 GB+ RAM (Qdrant in-memory + sentence-transformers).
- An OpenAI-compatible LLM endpoint reachable from your machine.

### Windows

```powershell
git clone https://github.com/sharmayash05/autonomous_alpha.git
cd autonomous_alpha
.\run.bat health
.\run.bat paper --interval 5
```

`run.bat` creates `venv/`, installs `requirements.txt`, then launches `python -m src.main`.

### Linux / macOS

```bash
chmod +x run.sh setup.sh
./run.sh health
./run.sh paper --interval 5
```

### Manual

```bash
python -m venv venv
source venv/bin/activate            # PowerShell: .\venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt

# .env
cp .env.example .env                # if provided
# edit LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

python -m src.main --mode health
python -m src.main --mode paper --interval 5
```

---

## 21. Docker Deployment

`docker-compose up -d` brings up four services:

| Service        | Image                    | Port | Purpose                                  |
|----------------|--------------------------|------|------------------------------------------|
| `trading-agent` | built from `Dockerfile`  | 5000 | Trading loop + dashboard                 |
| `qdrant`       | `qdrant/qdrant:latest`   | 6333 / 6334 | Vector DB                          |
| `prometheus`   | `prom/prometheus:latest` | 9090 | Metrics scraping                         |
| `grafana`      | `grafana/grafana:latest` | 3000 | Dashboards (`admin / ${GRAFANA_PASSWORD}`) |

Resource limits: trading-agent memory limit 4 GB, reservation 2 GB.
Volumes: `qdrant_data`, `prometheus_data`, `grafana_data`, plus host mounts
`./config:ro`, `./logs`, `./data`. Health check curls `http://localhost:5000/health`
every 30 s.

```bash
docker-compose up -d
docker-compose logs -f trading-agent
docker-compose down            # stop everything
docker-compose restart trading-agent
```

---

## 22. Vultr VPS Deployment

Full step-by-step in [DEPLOYMENT.md](DEPLOYMENT.md). Summary:

1. Provision Ubuntu 22.04 LTS, ≥ 4 GB RAM, near your exchange (Tokyo for Binance).
2. SSH in. Upload code via `upload_to_vps.bat` (SCP) or `git clone`.
3. `chmod +x setup.sh && ./setup.sh` — installs Docker, Compose, UFW (opens 22, 5000, 3000).
4. Create `.env` with `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `TRADING_MODE=paper`,
   `GRAFANA_PASSWORD=...`.
5. `docker-compose up -d`.
6. Browse to `http://<vps_ip>:5000`.

Maintenance: `docker-compose down`, `git pull && docker-compose build && docker-compose up -d`,
`docker-compose restart trading-agent`.

---

## 23. Testing & Diagnostics

```bash
# Full pytest suite (LLM client, council, reflexion, indicators, executors, sentiment, WS)
pytest tests/ -v

# One-off integration smoke test
python tests/test_integration.py

# Inspect stored lessons
python view_lessons.py

# Probe the LLM endpoint
python test_llm.py

# Heavy stress test (6 phases, parallel/json/long-prompt)
python stress_test_api.py

# Individual module self-tests
python -m src.utils.indicators       # generates random series, prints signal
python -m src.utils.metrics          # exposes metrics on :8080, ctrl-c to quit
python -m src.utils.logging          # emits sample logs + (dry) alerts
python -m src.utils.config_loader    # prints loaded config tree
python -m src.core.llm_client        # health-checks the LLM endpoint
```

`pyproject.toml` configures `asyncio_mode = "auto"` for pytest, so coroutine tests need
no explicit decorator.

---

## 24. Memory Pruning Cadence

Runs in `run_trading_loop` every **10 invocations** (≈ 50 minutes at 5-minute cadence):

1. `memory.prune_lessons(llm, max_lessons=50)` — LLM scores every lesson, keeps top-50.
2. `domain_memory.prune_stale_patterns(max_age_days=30, max_per_domain=100)` — deterministic.
3. `domain_memory.prune_patterns_intelligent(llm, max_per_domain=100)` — LLM scoring.
4. `market_memory.prune_snapshots_quality(max_snapshots=500)` — quality + recency.
5. `evolver.prune_rules(recent_lessons, perf_metrics)` — drops contradictory/stale rules.

All pruners log how many were pruned and how many kept, per lane.

---

## 25. Troubleshooting

| Symptom                                              | Likely cause / fix                                                                 |
|------------------------------------------------------|------------------------------------------------------------------------------------|
| `health` mode shows ❌ LLM API                       | `LLM_BASE_URL` unreachable. Try `curl $LLM_BASE_URL/models`.                       |
| Empty responses from Bull/Technical                  | LLM proxy struggling under parallelism; run `python stress_test_api.py` to confirm. The client already auto-retries empty content 3×. |
| `qdrant-client not installed` warning                | `pip install qdrant-client sentence-transformers` — the system falls back to JSON otherwise. |
| Dashboard 404 / refuses connection                   | Port 5000 in use. Set `FLASK_PORT=5050` env or stop the conflicting service.       |
| `Address already in use` on 8080                     | Another Prometheus exporter running. Set `METRICS_PORT=8081`.                       |
| `KeyError: portfolio_state.json`                     | Corrupt portfolio file. Delete `data/portfolio_state.json` to reset to $10k.       |
| Council "no decisions"                               | Specialists likely returned malformed JSON. Check `logs/trading_*.log`; the JSON extractor has 5 fallbacks but truly empty content yields HOLD. |
| Risk Guardian vetoes everything                      | Inspect veto reasons; usually `size_exceeds_500` or `no_stop_loss` from the PM.    |
| Memory pruning errors                                | Non-critical; logs at DEBUG level. Run `python view_lessons.py` to confirm storage. |

---

## 26. Disclaimer & License

> **This software is for educational and research purposes only.**
> Trading cryptocurrencies — especially with leverage — carries a substantial risk of total
> capital loss. Past performance is not indicative of future results. Always paper-trade
> first. Never risk capital you cannot afford to lose. The authors accept no liability for
> any losses, however arising.

Released under the **MIT License** — see [`LICENSE`](...) for the full text.

---




### Credits

Built with `loguru`, `rich`, `httpx`, `pydantic`, `pyyaml`, `flask`, `flask-socketio`,
`prometheus-client`, `numpy`, `pandas`, `ccxt`, `qdrant-client`,
`sentence-transformers`, `langchain` / `langgraph` (optional), and the Binance,
CryptoPanic, AlphaVantage and alternative.me public APIs.
