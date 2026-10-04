# A SYNOPSIS OF MINOR PROJECT II ON

# THE AUTONOMOUS ALPHA: AN LLM-CENTRIC SELF-EVOLVING MULTI-AGENT CRYPTOCURRENCY TRADING SYSTEM

Submitted In Partial
Fulfillment Of the Requirements for The Award of The Degree Of

## BACHELOR OF TECHNOLOGY
### Information Technology

By

**NAME-1 (Enrollment No.-1)**
**NAME-2 (Enrollment No.-2)**
**NAME-3 (Enrollment No.-3)**

GUIDE
*Designation*

Co-GUIDE
*Designation*

---

**School of Information Technology**
**Rajiv Gandhi Proudyogiki Vishwavidyalaya**
**Bhopal**

January – June 2025

---

<div style="page-break-after: always;"></div>

## 1. Introduction

The **Autonomous Alpha** is a fully autonomous, self-evolving cryptocurrency trading system that replaces hard-coded technical rules with the reasoning capability of Large Language Models (LLMs). At its core, a *council* of six specialist LLM agents — Bull Researcher, Bear Researcher, Technical Analyst, Sentiment Analyst, Risk Guardian, and Portfolio Manager — collaboratively debate every trading decision on Binance USDT-M futures markets such as BTC/USDT and ETH/USDT. Each cycle (default every five minutes), the system ingests real-time market microstructure (price, open interest, funding rate, long/short ratio, top-trader positioning, liquidations, multi-timeframe trend confluence, on-chain NVT ratio), news headlines (CryptoPanic, AlphaVantage, RSS feeds), and social sentiment (Fear & Greed Index, Google Trends), then feeds this multi-modal context to the council.

The project is built in **Python 3.10+** using an entirely asynchronous architecture (`asyncio`, `httpx`, `websockets`). The LLM is accessed through an **OpenAI-compatible REST endpoint** (default model: `gemini-3.0-pro-preview`), making the system model-agnostic and deployable with local backends such as Ollama, LM Studio, or vLLM. To solve the well-known "stateless goldfish memory" problem of LLMs, the system implements **four persistent memory subsystems** powered by the **Qdrant** vector database (with JSON fallback) and `sentence-transformers` (MiniLM-L6-v2, 384-dim embeddings): (i) an Agent Journal for per-agent context continuity, (ii) a Domain Memory for technical/sentiment/fundamental pattern recall, (iii) a Market Memory storing 8-dimensional snapshot vectors for historical precedent matching, and (iv) a Reflexion Lessons store containing graded post-mortems of every closed trade. A **Reflexion** module performs an eight-section forensic analysis of each closed trade, assigns an A–F grade, extracts a single-sentence lesson, and stores it for Retrieval-Augmented Generation (RAG) in future cycles. A **Strategy Evolver** monitors win-rate and trade-count metrics and uses the LLM to dynamically rewrite the Portfolio Manager's rule set when performance degrades.

Risk management combines deterministic **programmatic veto rules** (maximum $500 margin per position, 30% maximum portfolio exposure, 20× leverage cap, mandatory stop-loss) with an LLM-driven **Risk Guardian** that evaluates soft rules such as volatility regime, correlation, liquidation proximity, and funding-rate extremes. The system exposes a real-time **Flask + Socket.IO dashboard** at port 5000, **Prometheus** metrics at port 8080, and optional **Telegram/Discord** alerting. It is fully containerized via Docker Compose (services: trading-agent, Qdrant, Prometheus, Grafana) and includes a one-click VPS deployment workflow for Vultr.

---

<div style="page-break-after: always;"></div>

## 2. Rationale: Justification, Why Needed?

Traditional algorithmic trading systems rely on rigid, hand-coded technical indicator rules (e.g., "buy when RSI < 30 and MACD crosses positive"). These systems fail catastrophically when market regimes shift — a strategy optimised for trending markets bleeds capital in ranging conditions, and vice versa. Furthermore, retail traders today face an information asymmetry crisis: institutional desks deploy teams of analysts who simultaneously process price action, order-flow data, news flow, on-chain metrics, and social sentiment, while individual traders cannot manually integrate this volume of multi-modal information in real time. Existing retail "bots" address only the execution layer, not the reasoning layer.

The Autonomous Alpha is needed because it directly addresses both gaps. By replacing static rules with LLM-driven reasoning, it can **adapt its decision logic to changing market regimes without re-coding**. By orchestrating six specialised agents with distinct viewpoints (bullish thesis, bearish risks, pure technicals, crowd sentiment, capital protection, synthesis), it mirrors the structure of a professional trading desk while costing only the compute of the underlying LLM. The persistent memory and Reflexion loop give the system something no rule-based bot possesses: **the ability to learn from its own mistakes**, store graded lessons, and retrieve them as RAG context the next time a similar setup appears — effectively compounding intelligence over time. The Strategy Evolver closes the loop by allowing the agent to rewrite its own playbook based on realised profit-and-loss, making the system genuinely self-improving rather than statically programmed.

---

## 3. Objectives

1. **Design and implement an LLM-orchestrated multi-agent trading council** in which six specialised agents (Bull, Bear, Technical, Sentiment, Risk Guardian, Portfolio Manager) collaboratively analyse market data and produce a single, risk-vetted trading decision every N minutes.

2. **Eliminate LLM statelessness** by engineering four integrated persistent memory subsystems — Agent Journal, Domain Memory, Market Memory, and Reflexion Lessons store — using the Qdrant vector database and sentence-transformer embeddings for semantic retrieval of relevant historical context.

3. **Implement a self-evolving Reflexion learning loop** that performs an eight-section A–F graded forensic on every closed trade, extracts generalisable lessons, and dynamically rewrites the Portfolio Manager's rule set when win-rate degrades below configurable thresholds.

4. **Build a complete, production-grade trading framework** with realistic margin accounting (fees, leverage, partial closes, trailing stops, liquidation tracking), a real-time web dashboard, Prometheus metrics, alerting integrations, and one-command Docker deployment — all running unattended on a single commodity VPS in either paper-trading or live-trading mode.

---

<div style="page-break-after: always;"></div>

## 4. Feasibility Study

### 4.1 Technical Feasibility

The project is technically feasible with widely available open-source components. The entire stack — Python 3.10+, `asyncio`, `httpx`, Flask, Socket.IO, Qdrant, `sentence-transformers`, CCXT, and Prometheus — is mature, well-documented, and runs comfortably on a 4 GB / 2 vCPU VPS. LLM inference is offloaded to an OpenAI-compatible REST endpoint (cloud-hosted Gemini, OpenAI, Anthropic via proxy, or self-hosted Ollama/vLLM), so the local resource budget is minimal. The Binance public REST and WebSocket APIs provide all required market microstructure data free of charge, and testnet credentials allow safe end-to-end live-trading validation without capital risk. Vector embeddings (384-dim MiniLM) and Qdrant's in-memory mode keep retrieval latency under 50 ms even with thousands of stored snapshots.

### 4.2 Economic Feasibility

The development cost is effectively zero: all libraries, market data, and even the LLM (when self-hosted with Ollama) are free. Cloud-hosted LLM inference costs depend on the chosen provider — a 5-minute cycle calling six agents averages roughly 50,000–80,000 tokens per cycle, which on commodity Gemini/Llama-3 endpoints translates to under $1–3 per day. A Vultr VPS instance suitable for 24×7 operation costs $12–24 per month. The Binance API is free for retail volume tiers. No proprietary data feeds or paid market services are required.

### 4.3 Operational Feasibility & Significance

Operationally, the system is designed to run unattended: the trading loop self-heals (60-second backoff on exceptions), memory is auto-pruned every 10 invocations to prevent prompt flooding, the portfolio state is persisted to disk on every event, and Docker Compose handles process restart on failure. The dashboard provides full observability, while Prometheus exporters allow long-horizon performance analysis in Grafana. The significance of this project lies in demonstrating that LLM-driven reasoning, when coupled with rigorous memory engineering and deterministic risk controls, can match or exceed traditional rule-based algorithmic trading systems while remaining auditable (every decision has a chain-of-thought rationale stored in the journal). The architecture generalises naturally beyond crypto — the same council pattern could be applied to equities, forex, or commodity markets by swapping the data fetcher.

### 4.4 Need

There is no existing open-source retail trading system that combines (a) multi-agent LLM debate, (b) four-tier persistent memory, (c) graded Reflexion learning, and (d) self-evolving rule sets. Most "AI trading bots" available online are single-LLM-prompt wrappers without memory, learning, or risk controls. This project fills that gap with a complete, production-grade reference implementation.

---

<div style="page-break-after: always;"></div>

## 5. Methodology / Planning of Work

The project follows an **incremental Agile methodology** with weekly iteration cycles. Each module is independently testable (every Python file in `src/` has an `if __name__ == "__main__":` self-test block) and integrates into the trading loop only after passing unit tests.

**Research type:** Applied / experimental software engineering with empirical validation against live market data.
**Unit of study:** Individual trading cycles (every 5 minutes) and closed trades (each with full reflexion and grading).
**Data collection:** Real-time market data is collected via Binance REST and WebSocket APIs; news headlines via CryptoPanic, AlphaVantage and RSS feeds; sentiment data from Fear & Greed Index and Google Trends. All collected data, agent decisions, and trade outcomes are persisted in JSON and Qdrant for offline analysis.
**Tools of analysis:** Python pytest suite for unit/integration testing; Prometheus + Grafana for time-series performance metrics; custom `view_lessons.py` script to inspect graded reflexion lessons; backtester (`src/core/backtester.py`) for historical simulation with annualised Sharpe-ratio reporting.

### Development Phases

| Phase | Activity | Deliverable |
|-------|----------|-------------|
| 1 | Requirements analysis, architecture design, technology stack selection | Architecture diagram, module breakdown |
| 2 | LLM client + OpenAI-compatible API integration with retry/fallback | `src/core/llm_client.py` |
| 3 | Six-agent prompt engineering (Bull, Bear, Technical, Sentiment, Risk, PM) | `prompts/*.md` |
| 4 | Multi-agent council orchestration (3-phase: specialists → synthesis → veto) | `src/core/council.py` |
| 5 | Portfolio manager with realistic margin/fees/leverage accounting | `src/core/portfolio.py` |
| 6 | Real-time market data pipeline (Binance + news + sentiment) | `src/data/*.py` |
| 7 | Four memory subsystems (Journal, Domain, Market, Reflexion) | `src/memory/*.py` |
| 8 | Reflexion learning loop + Strategy Evolver | `src/memory/reflector.py`, `src/evolution/strategy_evolver.py` |
| 9 | Dashboard, Prometheus metrics, alerting | `src/dashboard/`, `src/utils/metrics.py`, `src/utils/logging.py` |
| 10 | Containerisation, VPS deployment, integration testing | `Dockerfile`, `docker-compose.yml`, `setup.sh`, `tests/` |
| 11 | Paper-trading validation, performance tuning, documentation | Paper-trade logs, final report |

### Steps to Achieve Objectives

1. Establish a reliable, low-latency connection to the LLM endpoint with automatic retry on empty/malformed responses.
2. Implement and unit-test each technical indicator (RSI, MACD, EMA, ATR, Bollinger, Stochastic, VWAP, OBV, CMF) in pure NumPy.
3. Engineer specialist prompts that produce strictly valid JSON; build a five-fallback JSON extractor for robustness.
4. Wire the Portfolio Manager's `on_trade_closed` callback into the Reflexion module so learning happens asynchronously without blocking the trading loop.
5. Validate end-to-end behaviour on Binance testnet for at least two weeks of paper-trading before any consideration of live deployment.

---

<div style="page-break-after: always;"></div>

## 6. Software / Hardware Required for the Project's Development

### 6.1 Software Requirements

| Category | Component | Version | Purpose |
|---------|-----------|---------|---------|
| **Operating System** | Windows 10/11, Ubuntu 22.04 LTS | – | Development & deployment |
| **Language** | Python | 3.10+ (3.12 recommended) | Core implementation |
| **LLM Inference** | OpenAI-compatible endpoint (Gemini / Ollama / OpenAI / vLLM) | – | Multi-agent reasoning |
| **Async Runtime** | `asyncio`, `uvloop` (Linux) / `winloop` (Windows), `httpx`, `websockets` | latest | Non-blocking I/O |
| **Vector Database** | Qdrant | ≥ 1.7 | Semantic memory retrieval |
| **Embeddings** | `sentence-transformers` (MiniLM-L6-v2, 384-dim) | ≥ 2.2 | Text → vector |
| **Exchange Connectivity** | CCXT, `python-binance` | ≥ 4.0 / ≥ 1.0 | Binance REST + WS |
| **Web Framework** | Flask + Flask-SocketIO | ≥ 3.0 / ≥ 5.0 | Real-time dashboard |
| **Configuration** | PyYAML, Pydantic v2, python-dotenv | ≥ 6.0 / ≥ 2.0 | Config & validation |
| **Monitoring** | Prometheus-client, Loguru, Rich | ≥ 0.19 / ≥ 0.7 / ≥ 13.0 | Metrics & logging |
| **Numerical** | NumPy, Pandas | ≥ 1.24 / ≥ 2.0 | Indicator calculations |
| **Backtesting (optional)** | Freqtrade | ≥ 2024.1 | Historical simulation |
| **Containerisation** | Docker, Docker Compose | ≥ 24 / ≥ 2 | Deployment |
| **Visualisation** | Prometheus, Grafana | latest | Dashboards |
| **Testing** | pytest, pytest-asyncio | ≥ 8.0 | Unit/integration tests |
| **IDE** | VS Code, PyCharm | – | Development |
| **Version Control** | Git, GitHub | – | Source management |

### 6.2 Hardware Requirements

**Development Machine:**

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | Dual-core 2.0 GHz | Quad-core 2.5 GHz+ |
| RAM | 8 GB | 16 GB |
| Storage | 20 GB free | 50 GB SSD |
| Network | Stable broadband | Low-latency fibre |

**Production VPS (e.g., Vultr Cloud Compute):**

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| vCPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Storage | 80 GB SSD | 160 GB NVMe SSD |
| Network | 1 Gbps shared | Tokyo region (low Binance latency) |
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |

---

## 7. Expected Outcomes

1. **A working autonomous trading agent** that runs unattended 24×7 on a VPS, executes a complete cycle (data fetch → six-agent debate → risk veto → execution → memory update) every 5 minutes, and demonstrably learns from closed trades through graded reflexion lessons stored in a vector database.

2. **A real-time web dashboard** (`http://<host>:5000`) showing live portfolio equity, open positions, every agent's analysis, the Portfolio Manager's chain-of-thought decision, current evolved rules, memory statistics, and historical trade history — providing full observability into the agent's reasoning.

3. **Empirical validation on Binance testnet** showing the system completes at least 100 paper trades over a continuous two-week run, with each trade accompanied by a stored A–F graded reflexion lesson, demonstrating that the learning loop functions end-to-end.

4. **Quantitative performance metrics** exported to Prometheus/Grafana — including win-rate, profit factor, Sharpe ratio, maximum drawdown, average LLM latency, council decision latency, and risk-guardian veto counts — enabling rigorous post-hoc evaluation of strategy quality.

5. **A reusable, model-agnostic framework**: because the LLM is accessed through an OpenAI-compatible interface, the same codebase can be benchmarked against multiple backend models (Gemini, GPT-4, Claude via proxy, Llama-3, Qwen, etc.) for comparative study.

6. **Demonstrated emergent intelligence**: the Strategy Evolver should produce measurable rule additions/removals across the project timeline, and the dashboard should show that retrieved past lessons influence subsequent trading decisions — providing a concrete demonstration of memory-augmented LLM reasoning in a high-stakes real-world domain.

7. **A complete academic deliverable** including documented source code (≈ 8,000 lines of Python across 25+ modules), Dockerised deployment, full README, integration test suite, and this synopsis — suitable for submission as Minor Project II and as a foundation for further research in LLM-augmented decision systems.

---

<div align="right">

**Signature(s) of student**

</div>

---

*— END OF SYNOPSIS —*
