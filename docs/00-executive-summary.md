# Takneek High-Prep — Executive Summary (read this first)

**One line:** An agentic coding product (VSCodium + our extension + a Python agent kernel) where a deterministic multi-stage pipeline of small open-weight models (≤80B total params) completes hard, multi-step coding tasks at near-zero cost by using free-tier APIs first, with visible routing, address-based compaction, AST+graph+hybrid retrieval, approval-gated tools, hunk-level HITL review, full tracing, and durable resume.

> **The authoritative plan is `06-plan-of-record.md`** — it merges this research pass with the team's earlier design docs (`architecture.md`, `decisions.md`, `linux-setup.md`, `presentation.md`, `ps-mapping.md`). Where files disagree, 06 wins.

- **Deadline:** 2 Sep 2026, 23:59 (8 days from 25 Aug)
- **Team:** 8 members (≥3 Y26, ≥3 Y25)
- **Deliverables:** zip with full git history, cross-platform builds (Win/mac/Linux), docs, 10-min presentation

## The five decisions that win this competition

1. **Cost ≈ $0 by default.** Scoring penalizes cost with exponent 2.5 against a $0.15 reference. Free tiers (Groq/Cerebras/OpenRouter-free/Mistral-free) make cost ~0, which maximizes the score formula. PAYG only as guarded fallback, hard-capped per task.
2. **The system compensates for weak models — that's the product.** Small models fail at: long contexts, multi-step drift, JSON/tool-call adherence, lazy edits. Every design choice (structured memory bank, small working contexts, search/replace edit format, verification loops, checkpoints + backtrack) exists to patch a specific small-model failure mode.
3. **Retrieval (12%) and orchestration (14%) carry the most architecture points.** Judges explicitly reward going "meaningfully beyond keyword matching or plain embeddings" and non-obvious, well-justified design. Our pipeline: tree-sitter AST + symbol/import graph + PageRank repo map + BM25 + local embeddings + LSP grounding + local reranker, with agentic narrow-down loops and retrieval quality self-checks.
4. **Mandatory features first:** API-key settings screen (disqualification if missing), approval gates for side-effect commands, `/bytheway`, block-level diff review, dashboard. These are pass/fail or heavily weighted; build them early, not last.
5. **The team must be able to explain everything.** Judges void features the builder can't explain, run a dedicated Y26 Q&A, and punish AI-generated explanations. Every doc here is written to be understood, not to impress — and every teammate must own ≥1 component deep enough to answer arbitrary questions on it.

## Recommended stack (decided in 06-plan-of-record.md)

| Layer | Choice | Why |
|---|---|---|
| IDE shell | **Prebuilt VSCodium + our extension** (Code-OSS build, no Copilot) | No fork-maintenance treadmill (EclipseSource evidence); cross-platform via VSCodium installers + our vsix; our product is the extension + kernel |
| Agent kernel | **Python** (`src/taknee/`, uv + FastAPI loopback), survives IDE restarts, CLI/headless for eval | Best ecosystem for tree-sitter/ONNX retrieval; SQLite event-sourced state = resume + traces |
| Orchestration | Deterministic state machine (Agentless-style) + bounded task splitter for long-horizon tasks | Agentless paper: higher accuracy, lower cost than open-ended agent loops; splitter answers the rubric's subtask-decomposition question |
| Models | Qwen3-Coder-30B-A3B primary (30.5B total, 256K ctx, native tools); Devstral Small 2 24B; utility 4-8B; local Qwen2.5-Coder-7B Q4; local embed/rerank 0.6B | Best ≤80B agentic-coding evidence; all open-weight, total params ≤80B |
| Providers | Groq, OpenRouter, NVIDIA NIM, Ollama (core); Cerebras, Mistral (stretch) | Free-tier-first routing → cost ≈ $0; instant signup for evaluators |
| Retrieval | AST chunks + BM25 + identifier overlap + import graph (v1); + local embeddings, reranker, LSP hooks (v2) | Beyond keyword/plain-vector (explicit rubric criterion), offline, per-repo isolated |
| Persistence | SQLite WAL (spans/events/tasks) in `<workspace>/.taknee/` | Crash-safe resume; traces live+post-hoc from one table |

## Document map

- `01-problem-analysis.md` — the PS distilled, scoring math, requirement→feature traceability
- `02-research-findings.md` — web research with sources (models, providers, fork mechanics, prior art, retrieval)
- `03-system-architecture.md` — the full system design with diagrams
- `04-roadmap.md` — 8-day execution plan, team split, git strategy, risks
- `05-decision-log.md` — ADRs: each key decision, alternatives considered, why rejected (judges score this)
