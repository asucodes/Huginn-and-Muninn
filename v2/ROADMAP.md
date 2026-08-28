# Taknee V2 Execution Roadmap

This roadmap tracks the engineering evolution of **Taknee V2**. Every phase contains concrete, measurable deliverables with actionable checkboxes for contributors and agents.

---

## Phase 1: Foundation & Tech Debt Purge
**Goal**: Clean the codebase, remove ad-hoc benchmark code, and establish modular structure.

- [ ] **1.1 Purge Ad-Hoc Code**:
  - [ ] Delete or decouple `src/taknee/research.py` (remove hardcoded GAIA benchmark strings).
  - [ ] Consolidate filesystem traversal from `retrieval.py` and `tools.py` into a unified `FileWalker`.
- [ ] **1.2 Clean Async Provider Client (`src/taknee/transport/`)**:
  - [ ] Build a single, async HTTPX/streaming provider client (replacing dual litellm/httpx boilerplate).
  - [ ] Add unified token counting, response streaming, and latency metrics.
- [ ] **1.3 V2 Folder & Documentation Handoff**:
  - [ ] Commit `v2/README.md`, `v2/ROADMAP.md`, `v2/RADAR_SYSTEM_SPEC.md`, `v2/HARNESS_ARCHITECTURE.md`, `v2/TODO.md`.

---

## Phase 2: The Free-Tier Radar & Swarm Mesh
**Goal**: Build the zero-cost compute aggregator and multi-provider rate-limit failover engine.

- [ ] **2.1 Live Free-Tier Radar (`src/taknee/swarm/radar.py`)**:
  - [ ] Live OpenRouter `:free` model probe (auto-syncs active zero-cost models).
  - [ ] GroqCloud / Google AI Studio Gemini Flash free-tier quota & health probes.
  - [ ] Live deal/promotional credit feed parser (Z.ai, DeepSeek, Cerebras, Cloudflare).
- [ ] **2.2 Multi-Key Pool & Swarm Balancer (`src/taknee/swarm/rotator.py`)**:
  - [ ] Multi-key registration for each provider in settings vault.
  - [ ] Instant 0ms failover on HTTP 429 rate limits across provider tiers.
  - [ ] Local Ollama / vLLM automatic offline fallback.
- [ ] **2.3 Prompt Cache Optimizer (`src/taknee/swarm/cache_optimizer.py`)**:
  - [ ] Deterministic prompt prefix alignment ensuring 90%+ cache hit rate on OpenRouter, Gemini, and DeepSeek.

---

## Phase 3: Next-Gen Autonomous Harness (OpenAI / SWE-Agent Patterns)
**Goal**: Replace the rigid conveyor belt with an event-driven, sandboxed execution engine.

- [ ] **3.1 Autonomous Milestone DAG (`src/taknee/engine/graph.py`)**:
  - [ ] Phase 1: Exploration & Planning (AST inspection, file discovery).
  - [ ] Phase 2: Dynamic ReAct Action Loop (bounded multi-tool execution in sandbox).
  - [ ] Phase 3: Automated Verification & Self-Diagnosis.
  - [ ] Phase 4: Human-in-the-Loop Proof & Diff Approval.
- [ ] **3.2 Ephemeral Git Worktree Sandboxing (`src/taknee/engine/sandbox.py`)**:
  - [ ] Automatic branch creation in `.taknee/worktrees/<task-id>`.
  - [ ] Jailed command execution and automatic rollback on failure.
  - [ ] Clean unified diff generation for one-click merge into active branch.
- [ ] **3.3 Async PTY Terminal Manager (`src/taknee/engine/terminal.py`)**:
  - [ ] Persistent pseudo-terminal (PTY) session handling for long-running servers and interactive CLI tools.

---

## Phase 4: Codebase Intelligence & Extensibility
**Goal**: Integrate Tree-sitter AST parsing and Model Context Protocol (MCP).

- [ ] **4.1 Tree-sitter AST Symbol Graph (`src/taknee/index/ast_indexer.py`)**:
  - [ ] Multi-language grammar support (Python, TypeScript, JavaScript, Rust, Go, C++).
  - [ ] In-memory SQLite symbol graph (definitions, references, callers, callees).
- [ ] **4.2 Standard Model Context Protocol (MCP) Client (`src/taknee/execution/mcp_client.py`)**:
  - [ ] Connect to local and remote MCP servers (PostgreSQL, GitHub, Brave Search, Puppeteer).
- [ ] **4.3 Directory-Based Skills (`.taknee/skills/`)**:
  - [ ] Custom domain skill loader (`SKILL.md` parser with execution triggers).

---

## Phase 5: Real-Time Streaming & UI Polish
**Goal**: Deliver a lightning-fast Monaco/VS Code experience.

- [ ] **5.1 WebSocket / SSE Streaming API (`src/taknee/api/`)**:
  - [ ] Real-time token streaming for LLM generations.
  - [ ] Live terminal stdout/stderr streaming.
- [ ] **5.2 "Free Compute Fuel Gauge" & Radar Panel in UI**:
  - [ ] Live visual status indicator of active free providers, available tokens, and 1-click key setups in the web console and VS Code extension.
