# 06 — PLAN OF RECORD (single source of truth)

Supersedes conflicting points in 00-05 and the unnumbered docs (`architecture.md`, `decisions.md`, `linux-setup.md`, `presentation.md`, `ps-mapping.md` — those remain as research/trade-off evidence for judges). Two planning passes converged: the unnumbered docs (team pass) and docs 00-05 (ZCode research pass, 2026-08-25). This file is what we build.

## Final decisions (merged)

| # | Decision | Source | Key evidence |
|---|---|---|---|
| D1 | **Host = prebuilt VSCodium + our extension** (not a self-built Code OSS fork, not Atom/Theia/CLI) | team pass, confirmed by ZCode research | EclipseSource "Is Forking VS Code a Good Idea?" — forks lose marketplace + ride a rebase treadmill; 8 days can't own that repo. VSCodium = prebuilt Code-OSS, MIT, telemetry off, **no Copilot** → satisfies "prebuilt IDE fork without AI". Our product = extension + kernel. |
| D2 | **Kernel = Python** (`src/taknee/`, uv, FastAPI loopback 127.0.0.1:47821), extension holds no logic | team pass | Python strongest for tree-sitter/ONNX retrieval stack; kernel survives IDE restart (req 6); CLI/headless for eval harness. (ZCode's TS option rejected: two thin UI files vs whole kernel — optimize for where the logic lives.) |
| D3 | **Orchestrator = deterministic state machine (Agentless-style) + bounded task splitter** | merged | Agentless (arXiv:2407.01489): localization→repair→validation without open-ended tool loops beat heavier agents on SWE-bench Lite at lower cost. Core pipeline: `retrieve → localize → patch → [approval] → apply → verify → diagnose(bounded) → loop`. **Addition vs team pass:** a single cheap decomposition call splits LONG-horizon tasks into ordered subtasks, each run through the machine with shared memory — because the PS's orchestration rubric explicitly asks "how well does it break a big task into smaller well-scoped sub-tasks", and the hidden eval is long-horizon. Bounded: no swarms, no debate, no reviewer-LLM-as-verifier (tests verify). |
| D4 | **Routing = feature-based, visible, free-first ladder** (both passes, aligned) | both | Deterministic signals: task class, token estimate, iteration count, provider cooldown (429/5xx), remaining $/time, allowlist. Status-bar route chip + `route_reason` on every span. Free tier → Ollama → PAYG-guarded. |
| D5 | **Retrieval = AST chunks + BM25 + identifier overlap + import-graph expansion (v1), + local embeddings + reranker + LSP hooks (v2)** | merged | v1 (team pass) is defensible and cheap: code is identifier-heavy; import graph = execution flow (PS asks for it). v2 (ZCode research) answers the rubric's "meaningfully beyond keyword OR plain vector, well justified": hybrid lexical+semantic+structural, RRF fusion, local Qwen3-Reranker-0.6B (ONNX, CPU, $0), LSP ground truth via the IDE for definition/reference queries. Build v1 Day 2, v2 Day 4-5 — A/B both on the harness and keep the numbers (judges score compared approaches). |
| D6 | **Edit format = SEARCH/REPLACE blocks first** (unified diff as fallback), fuzz apply + 1 repair retry | ZCode research overrides team pass | Aider benchmarks: search/replace measurably lifts weak models (GPT-3.5-class jumped on it); unified diffs reduce laziness on stronger models. Our models are small → S/R first. A/B on harness, record in `05-decision-log.md` ADR-3. |
| D7 | **Compaction = addresses, not summaries** (both passes converge) | both | Pinned forever: task prompt, AGENTS.md, user pins, accepted/rejected hunks, last fail log, decisions ledger. Compacted: raw chunk bodies → `span_id` + preview, hydratable from the index. Trigger: projected prompt > 70% of *selected* model's window (model-dependent — router tells compactor the budget), or after diagnose. Multiple compactions safe: bank rows persist. |
| D8 | **Model catalog** (allowlist w/ published total params, sources; ban list incl. Qwen3-Coder-480B, DeepSeek-V3/R1, Nemotron-120B, all closed models) | team pass + ZCode | Primary API: Qwen3-Coder-30B-A3B-Instruct (30.5B total, 256K ctx, native tools), Devstral Small 2 24B (SWE-bench ~68-73% w/ scaffold), Qwen3-Next-80B-A3B legal at exactly 80B total (HF card). Utility tier: Qwen3-8B/4B class. Local (16GB/8GB): Qwen2.5-Coder-7B/8B Q4 via Ollama. Embed/rerank (local ONNX): Qwen3-Embedding-0.6B / Qwen3-Reranker-0.6B — in the same catalog (PS: "every model used anywhere"). |
| D9 | **Providers** | merged | Core: **Groq, OpenRouter, NVIDIA NIM, Ollama** (team pass, all instant signup). Stretch Day 5: **Cerebras** (fastest free tier — time score) + **Mistral** (Devstral direct, free experiment tier). All OpenAI-compatible → one adapter each. Keys via mandatory Settings screen; never logged; stored per `linux-setup.md`. |
| D10 | **Governors = 2400s / $0.40 hard stops** (both passes identical), plus stuck-fingerprint ×3, empty-patch ×3, step cap | both | Margin under eval ceilings (2700s/$0.50). On cap hit: stop and persist → resume is exact. |
| D11 | **HITL: patches land in approval payloads, never the working tree directly; hunk accept/reject; rejected hunks become constraints; tests gated unless auto-run enabled** | team pass | Also: any side-effect terminal command requires approval (req 8b), deny-list + cwd jail + timeouts regardless. |

## Architecture snapshot (one glance)

```
VSCodium ── Taknee extension (chat, settings, review, traces, route chip, pins, /bytheway)
   │ HTTP 127.0.0.1:47821
taknee kernel (Python, uv)
   settings → router(free-first ladder, cooldowns) → orchestrator(state machine + splitter)
        retrieval(per-workspace index: AST+BM25+ids+imports [+vectors+rerank+LSP])
        providers(Groq/OpenRouter/NIM[/Cerebras/Mistral]/Ollama)
        compaction(pinned bank + addresses)   patches(SEARCH/REPLACE + hunks)
        tools(read-only fs/git, DDG web, gated terminal)   store(SQLite spans/events/tasks)
   → workspace files + <workspace>/.taknee/ + ~/.taknee/settings.json
```

Every agent/tool call = a **span** (parent, model, provider, route_reason, I/O, tokens, $, time, span_ids in context). Traces view reads the same table live and after completion (req 11, no gaps by construction). Task state transitions are transactions → crash-safe resume (req 6).

## Requirement traceability
`ps-mapping.md` (team pass) is correct as written; one addition — req 1 "sub-task breakdown" now maps to the bounded task splitter (D3). Keep that table updated as code lands.

## Build order (adjusted from 04-roadmap.md — no fork CI, freed ~1.5 days)

- **Day 0 (Aug 25):** git init + GitHub repo; kernel scaffold (uv, FastAPI, SQLite spans/events, catalog.py, settings endpoint); extension scaffold (activity bar, chat panel, **settings screen with key fields + test-key**); VSCodium install script (already in `linux-setup.md`). 
- **Day 1:** provider adapters (Groq first, e2e call); router + cooldown + fallback + route chip; state machine skeleton; SEARCH/REPLACE applier. *Gate: one prompt → retrieve → patch → apply → verify, visible as spans.*
- **Day 2:** retrieval v1 (AST chunks, BM25, identifier overlap, import hop; incremental index; isolation test); compaction v1 (pins + addresses); AGENTS.md parser. *Gate: good localization on a real repo, cheap.*
- **Day 3:** approval flow + hunk review UI; traces view v1 (tree + drill-down, live+replay); resume-after-kill test; stuck/cap watchdog. *Gate: kill kernel mid-task → reopen → exact resume.*
- **Day 4:** retrieval v2 (embeddings + reranker + LSP hooks, A/B vs v1); task splitter + file leases; pins/clickable tags both ways; `/bytheway`. *Gate: multi-subtask long-horizon task completes end-to-end.*
- **Day 5:** Ollama tier; Cerebras/Mistral adapters; eval harness (SWE-bench-style local tasks → accuracy/$/s triples); failure drills (429 storms, bad keys, huge repos). Tune router thresholds, compaction trigger, retry caps with recorded numbers.
- **Day 6:** docs finalization (verify `linux-setup.md` on a clean Linux VM/WSL from scratch incl. every provider's key setup; README w/ architecture + diagrams; merge ZCode research + team decisions into final trade-off docs); cross-platform run-throughs (Win/mac/Linux); presentation build (`presentation.md` outline stands).
- **Day 7 (Sep 1):** feature freeze; final artifacts (vsix + kernel; document `uv run taknee` per OS, optional PyInstaller binaries); full-team Q&A drills incl. Y26 implementation questions; submission zip **with `.git`**.
- **Day 8 (Sep 2):** buffer; submit by 20:00.

## Ownership (8 people; adjust to real skills)
A kernel/orchestrator · B retrieval+index · C router/providers+settings · D extension UI (chat/review/traces) · E tools/approvals/git+resume · F splitter+compaction+AGENTS.md · G eval harness+tuning+docs · H builds/cross-platform QA+presentation lead. Every member owns answering rubric questions for their area; pair Y26s with seniors, real components (judges run a dedicated Y26 implementation Q&A).

## Open items (close by Day 2)
- [ ] Confirm Qwen3-Next-80B-A3B & Qwen3.6-35B-A3B param cards on HF (≤80B total → eligible primaries)
- [ ] Web search backend for agents (DDG HTML scrape in `tools.py` — no paid APIs)
- [ ] Key storage hardening: settings.json 0600 vs OS keychain via extension SecretStorage (decide with whoever owns settings)
- [ ] Product name/branding (Day 7, cosmetic)
