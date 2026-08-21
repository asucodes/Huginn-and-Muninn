# 04 — Execution Roadmap (8 days: Aug 25 → Sep 2, 23:59)

## Day 0 — Mon Aug 25 (today): foundations
- [ ] `git init` + GitHub repo (private) — **start accumulating git history NOW** (deliverable requires it; also our defense of real contribution)
- [ ] Repo layout: monorepo `ide/` (fork, added as subtree at the END to keep repo light — or separate repo; decide Day 0), `engine/`, `docs/`
- [ ] Everyone reads docs 00-03; assign ownership (below)
- [ ] Fork setup spike: clone microsoft/vscode at chosen stable tag, apply VSCodium-style product.json patch (name, telemetry off, Open VSX), build locally on Windows once
- [ ] Engine scaffold: package, SQLite, event log schema, JSON-RPC channel, first provider adapter (Groq) end-to-end
- [ ] Settings screen skeleton with SecretStorage (the mandatory feature — earliest possible)

## Day 1 — Tue Aug 26: vertical slice
- [ ] CI (GitHub Actions) building the fork for win/linux/macos → nightly artifacts (longest-lead risk killed early)
- [ ] Providers: Cerebras, OpenRouter, Mistral adapters; rate-limit tracker; fallback ladder; routing event log
- [ ] Chat panel MVP: send prompt → single Implementer agent loop with tools (read/search/edit/run) → reply in UI
- [ ] Approval gate UI for side-effect commands
- **Gate: a task runs end-to-end, one agent, one provider, visible in a raw event log.**

## Day 2 — Wed Aug 27: retrieval + memory
- [ ] Indexer: tree-sitter parse, symbols, AST chunks, imports graph, incremental updates
- [ ] BM25 + local embeddings (ONNX) + RRF + reranker; repo map (PageRank) 
- [ ] Memory bank + context assembly + compaction triggers (soft/hard) + digests
- [ ] AGENTS.md parse → pinned memory
- [ ] Eval harness v1 (3-5 local tasks) → first numbers
- **Gate: Navigator answers "where would you change X" with a good file list, cheaply.**

## Day 3 — Thu Aug 28: orchestration
- [ ] Plan DAG, subtask dispatch, parallel leaves + file leases, git branch/checkpoint flow
- [ ] Watchdog: loop detection, caps, no-progress → backtrack/replan
- [ ] Verifier loop: build/test, error parse, targeted fixes
- [ ] Reviewer agent + acceptance checks
- **Gate: a 2-3 subtask task completes with checkpoints, verification, and resume-after-kill.**

## Day 4 — Fri Aug 29: the PS-specific features
- [ ] HITL diff review: per-hunk accept/reject, partial-apply continuation
- [ ] Context manager panel + @-mentions + clickable file:line tags (input & output)
- [ ] `/bytheway` ephemeral threads
- [ ] Dashboard v1: trace tree + node drill-down (live + replay)
- [ ] Multi-session resume UX (reopen → resume task)

## Day 5 — Sat Aug 30: hardening + local tier
- [ ] Ollama adapter + local model tier; settings for all providers finalized; "test key" buttons
- [ ] Dashboard v2: context-lifetime view, cost/time panels, live thoughts
- [ ] Governor tuning via eval harness (routing thresholds, context budgets, retry caps) — record A/B numbers in 05-decision-log
- [ ] Failure drills: kill engine mid-task; 429 storms (mock); bad keys; huge repo indexing

## Day 6 — Sun Aug 31: performance + docs
- [ ] Eval pass on 8-12 tasks; tune for accuracy-vs-cost-vs-time balance (target: C≈$0 on free tiers, T<1200s, accuracy maxed)
- [ ] Cross-platform build QA on clean machines (fresh VMs / teammates' machines)
- [ ] Docs: README (architecture + diagrams, Linux setup from scratch incl. every provider's key setup), ADRs finalized, challenges-and-solutions writeups (from git history + decision log)

## Day 7 — Mon Sep 1: freeze + present
- [ ] Feature freeze; bugfix only
- [ ] Final builds (win/mac/linux) + run-instructions verification
- [ ] Presentation build (10 min, 2+ presenters) + **Q&A drills: every member explains their components; Y26-specific implementation drills** (judges score this hard)
- [ ] Prepare submission zip **including `.git`** (zip the folder; `git archive` would drop it)

## Day 8 — Tue Sep 2: buffer + submit
- [ ] Buffer for build breakage / final polish; submit before 20:00 (never 23:55)

## Ownership split (8 people — adjust to actual skills)

| Stream | Owns | Also |
|---|---|---|
| A: Fork/build (1) | fork patches, CI matrix, packaging, Open VSX | cross-platform QA |
| B: Engine core (2) | event log, task lifecycle, tool layer, approvals, git flow | resume/crash safety |
| C: Retrieval (2) | indexer, BM25+embeddings+graph, reranker, repo map | eval harness |
| D: Routing/providers (1) | provider adapters, rate-limit state, fallback ladder, settings screen | Ollama tier |
| E: UI panels (1) | chat, context manager, tags, /bytheway, HITL review | settings UX |
| F: Dashboard + docs (1) | observability webview, README/diagrams, ADR upkeep | presentation lead |

Everyone: writes commits with real messages, updates 05-decision-log when they reject an approach, and can explain their stream in the Q&A. Y26 members get deep ownership of real components (judges explicitly probe this), paired with a senior for review.

## Git strategy
- `main` protected; feature branches `feat/<stream>-<thing>`; squash-merge with meaningful messages; conventional commits
- Fork of VS Code: **not** in our repo's history (submodule/subtree at freeze time, or separate repo) — keeps OUR history readable for judges
- Nightly tags once CI is green

## Top risks
1. **VS Code build pipeline breaks on some platform** → CI from Day 1, not Day 6; unsigned mac builds acceptable (document it)
2. **Free-tier limits during eval** → multi-provider spread + queue + PAYG guard; document key setup for ≥3 providers
3. **Small-model tool-call flakiness** → native function calling + strict parser + repair retry; edit format = SEARCH/REPLACE (research-backed)
4. **Scope creep on UI** → PS says functionality > aesthetics; minimal, functional panels only
5. **Time** → every day has a gate; if a day slips, cut dashboard v2 frills, never: settings screen, approvals, diff review, resume
