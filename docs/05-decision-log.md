# 05 — Decision Log (ADRs)

Format: Context → Decision → Alternatives rejected → How we'll validate. This file is a scoring asset ("did you actually try/compare more than one approach") — append real A/B numbers from the eval harness as we go.

## ADR-1: IDE base = Code OSS fork (frozen tag), not Atom/Theia/custom/CLI
- **Context:** need a cross-platform IDE shell with no built-in AI, buildable in 8 days by 8 people.
- **Decision:** Fork microsoft/vscode (Code OSS) at a fixed stable tag; VSCodium-style patches (product.json: our name/telemetry off/Open VSX; strip any AI bits present in core); pre-bundle our extension; GitHub Actions matrix builds win/linux/mac. Never rebase upstream during the competition.
- **Rejected:**
  - *Atom fork* — archived Dec 2022, stale Electron, security-dead. Undefensible.
  - *Eclipse Theia* — real alternative (ext-compatible, Open VSX), but smaller ecosystem, TheiaAI to strip, judges less familiar; no advantage worth the novelty risk in 8 days.
  - *Custom Electron+Monaco* — weeks to rebuild terminal/SCM/diff/file-tree we get free.
  - *Extension-only (vsix into user's VS Code)* — trivial builds, but deliverable demands cross-platform builds + evaluators test OUR product; a fork is a controlled, complete environment. (Our engine still ships CLI-capable for dev/eval harness.)
- **Validate:** Day 1 green CI artifacts on all 3 platforms.

## ADR-2: Engine in TypeScript as a separate Node process
- **Context:** agent engine hosting orchestration, retrieval, persistence; must survive IDE restarts.
- **Decision:** TypeScript/Node child process, JSON-RPC over stdio with the extension; SQLite (better-sqlite3, WAL); headless CLI mode.
- **Rejected:**
  - *Engine in extension host process* — IDE crash kills tasks (violates req 6); harder to test.
  - *Python engine* — richer ML libs, but second language/toolchain for the team; everything needed (tree-sitter, ONNX runtime, ripgrep wrapping, sqlite) exists in Node; one language maximizes the number of teammates who can touch anything.
- **Validate:** resume-after-kill test in Day 3 gate.

## ADR-3: Edit format = SEARCH/REPLACE blocks (aider-style) with fuzz + one repair retry
- **Context:** small models botch edits (lazy diffs, wrong anchors, invalid JSON).
- **Decision:** SEARCH/REPLACE blocks applied with exact match → fuzzy fallback → on failure one retry with the apply error fed back; whole-file rewrite only for files < ~50 lines.
- **Rejected:** *unified diffs* (line-number drift breaks small models), *free JSON patch* (adherence), *whole-file* (token cost + regressions).
- **Validate:** harness A/B: apply-success rate per format on 20 edits with T2 model (record numbers here).

## ADR-4: Routing = deterministic explainable ladder over a declared model manifest
- **Context:** routing must be transparent, cheap-first, rate-limit-aware, fallback-safe.
- **Decision:** manifest of eligible models (≤80B total, open weights, free/PAYG/local) + deterministic policy: capability filter → free-tier first (spread across providers, latency EWMA + remaining quota) → tier match → PAYG under $ governor → local. Every decision logged with reasons + alternatives.
- **Rejected:** *learned router* — can't defend/explain it to judges in Q&A, cold-start data we don't have, risk of weird choices under eval load. Determinism = transparency (req 3.b) for free.
- **Validate:** eval harness: simulated 429 storm → task completes with ≤1 visible disruption; routing reasons review.

## ADR-5: Memory = structured bank (source of truth) + transcript digests; never transcript-only
- **Context:** compaction must not lose relevant info (req 4.b); small models degrade with long contexts.
- **Decision:** typed memory rows (brief, plan state, decisions ledger, file manifest, tool digests, AGENTS.md, pinned user messages); per-turn assembly target ≤16-24K; compaction drops/digests transcript items, bank rows persist; pinned items never compacted.
- **Rejected:** *Claude-Code-style transcript summarization alone* — known state loss; summary-of-summary drift across multiple compactions (PS explicitly probes multi-compaction behavior).
- **Validate:** harness task with 3+ forced compactions → decisions/file facts still correct afterwards; dashboard context-lifetime view shows it.

## ADR-6: Retrieval = hybrid (BM25 + local embeddings) + symbol graph/PageRank repo map + LSP grounding + local reranker, agentic narrow-down loop
- **Context:** 12% of score; must beat keyword/plain-embeddings with justification.
- **Decision:** four orthogonal signals fused (RRF) then reranked locally (Qwen3-Reranker-0.6B, ONNX CPU); AST chunks only (no file dumps); coverage check re-queries when retrieval looks weak; LSP answers definitional queries with ground truth inside the IDE.
- **Rejected:** *pure embeddings RAG* (explicitly called out as insufficient by PS; weak on identifiers), *pure BM25* (misses paraphrase), *cloud rerankers/embeddings* (cost + key friction + closed models), *vector DB service* (SQLite FTS5 + a flat ANN over local embeddings is plenty at repo scale; zero infra).
- **Validate:** harness A/B per signal (BM25-only vs +vectors vs +graph vs +rerank vs +LSP) on retrieval hit-rate@k; record here. (This table becomes a highlight of the final docs.)

## ADR-7: Task safety = git branch + checkpoint commits; backtracking = revert; HITL = git diffs with hunk-level apply
- **Context:** need accurate diffs, undo, partial approval (reqs 1.c.v, 10).
- **Decision:** branch `taknee/<task-id>`; checkpoint per subtask; watchdog backtracks by reverting checkpoints; review UI applies accepted hunks selectively; rejected hunks fed to agent as constraints.
- **Rejected:** *shadow-FS / virtual overlays* (Complex; opaque to users), *no checkpoints* (no undo story for judges).
- **Validate:** partial-approval continuation test in Day 4 gate.

## ADR-8: Cost policy = free-tier-first, PAYG guarded, per-task governors
- **Decision:** default routing to free tiers; PAYG enabled only if user opts in AND task $ < warn ($0.10) / stop ($0.40, margin under $0.50 ceiling); time soft-stop 2400s (margin under 2700s) → graceful best-effort finish.
- **Rejected:** *always-PAYG for reliability* — cost exponent 2.5 destroys the score; *free-only* — rate-limit dead-ends would cost accuracy (tasks halted = A=0).
- **Validate:** harness: cost/time/accuracy triples per policy on the task set.

## Open decisions (resolve by Day 1-2)
- [ ] Exact fork base tag (latest stable at fork time) + whether subtree or separate repo at freeze
- [ ] Primary model default if Qwen3.6-35B-A3B verifies (≤80B?) — recheck HF before freeze
- [ ] Web search tool backend (free tier, e.g., DuckDuckGo HTML / Searxng-style; no paid search APIs)
- [ ] Embedding choice: Qwen3-Embedding-0.6B vs jina-code-v2 (license check) — A/B on our repos
- [ ] Product name + branding pass (last day)

## ADR-9: What we build vs what we adopt (originality / proof-of-work defense)

**Context:** judges audit git history, void unexplainable features, and penalize copied work presented as original. We use OSS where it is undifferentiated plumbing, and write original code where the problem statement scores us.

**Adopted (with attribution, never stripped):**
- **LiteLLM (MIT)** — provider transport: unified OpenAI-compatible calls, provider quirks. Replaces hand-rolling N HTTP adapters. Our catalog gate + router still decide what may be called.
- **FastAPI/uvicorn (MIT)** — loopback API server. **SQLite** (public domain) — WAL store. **VSCodium** (MIT builds of Code OSS) — editor host with no built-in AI.
- **Patterns studied, not copied:** aider (edit formats, repo map — reimplemented in `patches.py`/`retrieval.py` with our own regex/scoring), FCC free-claude-code (catalog/fallback/cooldown patterns), Agentless paper (pipeline shape). All cited in docs/02 and code comments.

**Original work (our IP, every member must be able to defend):**
- `catalog.py` compliance gate (≤80B total-param allowlist + ban list — rejects illegal models *before* any request)
- `router.py` deterministic free-first policy with cooldowns, escalation, explainable route_reason
- `orchestrator.py` state machine with Parked (HITL) + resume, caps (time/$/steps/fingerprint/empty-patch)
- `compaction.py` pin/address model (no transcript summarization)
- `retrieval.py` v1 (AST-ish chunks, identifier scoring, import hop, per-workspace isolation)
- `patches.py` SEARCH/REPLACE applier (exact → whitespace-insensitive → recorded failure)
- `store.py` span/event schema powering traces + resume; extension panels (chat/review/traces/settings/route chip)

**Rule:** any OSS code vendored keeps its license header + a line here. Never strip attribution — it is both a license violation and exactly what judges are trained to catch.

**Validate:** every team member can explain each file above without notes (presentation Q&A + Y26 drill).
