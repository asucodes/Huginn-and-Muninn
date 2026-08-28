# Taknee V2: The Sovereign Agentic Coding Engine & Free-Tier Compute Radar

> **"Give developers frontier-grade coding autonomy without charging a single dollar."**

---

## 1. What is Taknee V2?

Taknee V2 (**Huginn & Muninn 2.0**) is an open-source, local-first agentic coding kernel and IDE extension designed specifically for **hobby developers, indie hackers, freeloaders, and open-weight model enthusiasts**.

Unlike proprietary corporate tools (Cursor, Windsurf, Claude Code, Devin) that lock users behind \$20–\$200/month paywalls and restrict model selection, Taknee V2 is built around two core pillars:

1. **Standardized Next-Gen Agent Harness**: Adopting battle-tested execution patterns from the open-source **OpenAI Harness**, **SWE-agent**, and **mini-SWE-agent** — featuring event-driven ReAct execution, ephemeral Git worktree sandboxing, Tree-sitter AST symbol graphs, and full Model Context Protocol (MCP) extensibility.
2. **Live Free-Tier Compute Radar & Swarm Mesh**: A background intelligence system that monitors, scrapes, and aggregates free AI API tiers, promotional credit drops, and launch deals (Groq, OpenRouter `:free`, Google AI Studio Gemini Flash, DeepSeek, Z.ai, Cerebras, Cloudflare Workers AI, and local Ollama) — load-balancing across them seamlessly so users **never pay for tokens and never get blocked by 429 rate limits**.

---

## 2. High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                TAKNEE V2 SYSTEM TOPOLOGY                                │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│     [VS Code / VSCodium Extension]   <── WebSocket / SSE ──>   [Local Web Console]      │
│                                       │                                                 │
│                                       ▼                                                 │
│  ┌───────────────────────────────────────────────────────────────────────────────────┐  │
│  │                            TAKNEE V2 PYTHON KERNEL                                │  │
│  │                                                                                   │  │
│  │  ┌────────────────────────┐ ┌─────────────────────────┐ ┌──────────────────────┐  │  │
│  │  │  AUTONOMOUS MILESTONE  │ │    FREE-TIER COMPUTE    │ │   CODEBASE INTELLIGENCE│  │
│  │  │      GRAPH (DAG)       │ │     RADAR & SWARM       │ │   & SANDBOX MANAGER    │  │
│  │  │                        │ │                         │ │                        │  │
│  │  │ • Intent & Plan Gate   │ │ • Live Promo Scraper    │ │ • Tree-sitter AST Graph│  │
│  │  │ • Dynamic ReAct Loop   │ │ • Multi-Key Pool Rotator│ │ • Ephemeral Worktree   │  │
│  │  │ • Automated Verifier   │ │ • Prompt Cache Packer   │ │ • Async PTY Terminal   │  │
│  │  │ • Human-in-Loop Review │ │ • 0ms 429 Failover      │ │ • Native MCP Client    │  │
│  │  └───────────┬────────────┘ └────────────┬────────────┘ └──────────┬─────────────┘  │  │
│  │              │                           │                         │                │  │
│  └──────────────┼───────────────────────────┼─────────────────────────┼────────────────┘  │
│                 │                           │                         │                   │
│                 ▼                           ▼                         ▼                   │
│        [SQLite WAL Engine]        [Multi-Provider Swarm]     [Git Isolated Sandbox]       │
│        • Durable Tasks/Spans      • Groq (500 t/s free)      • Zero-risk temp branch      │
│        • Cross-Session Knowledge  • OpenRouter (:free)       • Auto-test validation       │
│        • Append-only Trace Log    • Gemini 2.0 Flash Free    • 1-click merge diff         │
│                                   • Local Ollama / vLLM                                   │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Directory Layout for V2

```
v2/
├── README.md                 # This manifesto & architecture overview
├── ROADMAP.md                # 5-Phase granular execution plan & milestone checkboxes
├── RADAR_SYSTEM_SPEC.md      # Detailed spec of the Free-Tier Radar, Scrapers & Swarm Balancer
├── HARNESS_ARCHITECTURE.md   # Detailed spec of the Autonomous DAG, Sandboxing & MCP Client
└── TODO.md                   # Live task backlog, WIP tracker & agent handoff protocol

src/taknee/ (V2 Target Layout)
├── __main__.py               # Fast CLI entry point
├── api/                      # FastAPI + WebSocket/SSE streaming server
├── swarm/                    # Free-tier radar, scrapers, multi-key rotator & prompt cache packer
├── engine/                   # Autonomous DAG, subagents, and ReAct execution engine
├── index/                    # Tree-sitter multi-language parser & symbol graph indexer
└── execution/                # Git worktree sandbox, async PTY terminal, tools & MCP client
```

---

## 4. Why Developers Choose Taknee V2

* **\$0.00 Monthly Cost**: Designed from day 1 for zero-budget developers, students, and hobbyists.
* **Instant Free-Tier Swarm**: Automatically combines Groq, OpenRouter free models, Gemini Flash, and local Ollama into a unified, high-speed, rate-limit-proof compute pool.
* **Zero-Risk Sandboxing**: Runs all multi-file edits and test commands in background Git worktrees; never corrupts your active workspace.
* **Open & Standard-Compliant**: Reuses proven patterns from OpenAI's open-source Harness, SWE-agent, and the Model Context Protocol (MCP).
