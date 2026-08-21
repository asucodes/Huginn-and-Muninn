# The Harness Is the Product

## A long-form technical book chapter on **Huginn & Muninn** (`E:\taknee-ide`, package `taknee` v0.1.0)

*Written from a full read of the repository: 15 kernel modules in `src/taknee/`, 6 TypeScript panels in `apps/extension/src/`, 9 offline test files in `tests/`, 15 documents in `docs/`, `pyproject.toml`, `uv.lock`, `apps/extension/package.json`, `.vscode/launch.json`, and git history (3 commits). All 84 tests pass offline (`84 passed, 1 warning in 4.30s`). File paths, class names, function names, constants, and numbers below are quoted from the code, not invented.*

---

# Phase 1 — Read This First

## The one best starting page

**[Building Effective Agents — Anthropic Engineering, Dec 19 2024](https://www.anthropic.com/engineering/building-effective-agents)**

Read it before this chapter. Here is why that page and not something flashier:

1. **It draws the exact line this repository is built on.** The essay's central distinction is *workflows* — "systems where LLMs and tools are orchestrated through predefined code paths" — versus *agents* — "systems where LLMs dynamically direct their own processes." Your repo's `orchestrator.py` opens its docstring with "No free-form ReAct loop: tools are available at named stages only" (`docs/decisions.md`, D2). The whole system is a workflow wearing agent clothing, and the essay gives you the vocabulary to see why that is a feature, not a compromise.
2. **It names the design pressure the repo is answering.** "The most successful implementations use simple, composable patterns rather than complex frameworks" — `pyproject.toml` lists exactly five runtime dependencies (fastapi, uvicorn, httpx, pydantic, litellm). No LangChain. No agent framework. That is the essay's advice implemented as a lockfile.
3. **It introduces the agent-computer interface (ACI) idea** — "plan to invest just as much effort in creating good agent-computer interfaces (ACI)" — which is what `tools.py`, `patches.py`, and the SEARCH/REPLACE prompt format in `orchestrator.py` are all about.

The close second — and the *direct ancestor* of the orchestrator — is the **Agentless paper** (arXiv:2407.01489), which proved on SWE-bench Lite that a three-phase pipeline (localize → repair → validate) beat open-ended agent loops on **both accuracy (32.00%) and cost ($0.70)**. This repo cites it by name in `orchestrator.py`'s docstring ("deterministic state machine (Agentless-style)") and in `docs/decisions.md` D2. Read the Anthropic essay first for the frame; read Agentless second to understand the specific machine you are about to study.

## A definition you can reuse

> **A harness is the deterministic machinery wrapped around a non-deterministic model**: the code that assembles each prompt, decides which model and provider handles it, executes the tools the model asks for, checks the results against reality, records everything that happened, and enforces the budgets the model cannot enforce on itself. The model proposes; the harness disposes. A chatbot is one call; an IDE plugin is an interface; a harness is a *control system* — it makes a stochastic component behave like a dependable subsystem in a larger program.

## The reading path

**Foundations**
- Anthropic, *Building Effective Agents* — workflows vs. agents; the augmented LLM; "find the simplest solution possible."
- ReAct: *Synergizing Reasoning and Acting in Language Models* ([arXiv:2210.03629](https://arxiv.org/abs/2210.03629)) — the canonical observe→think→act loop. Read it to know exactly what this repo *rejects*, and why.
- SWE-agent: *Agent-Computer Interfaces Enable Automated Software Engineering* ([arXiv:2405.15793](https://arxiv.org/abs/2405.15793)) — SWE-bench pass@1 of 12.5% achieved via interface design alone. The ACI thesis explains this repo's `PATCH_PROMPT` and its `OUTPUT_MAX` caps.

**Implementations**
- *Agentless* ([arXiv:2407.01489](https://arxiv.org/abs/2407.01489)) — the paper this orchestrator is modeled on.
- Aider, *Edit formats* ([aider.chat/docs/more/edit-formats.html](https://aider.chat/docs/more/edit-formats.html)) — the origin of the `<<<<<<< SEARCH / ======= / >>>>>>> REPLACE` format in `patches.py`; documents which edit formats suit which model classes.
- Thorsten Ball, *How to Build an Agent* ([ampcode.com/how-to-build-an-agent](https://ampcode.com/how-to-build-an-agent)) — "It's an LLM, a loop, and enough tokens." A working code-editing agent in under 400 lines; the best demystifier of the core loop.
- Anthropic, *Claude Code best practices* ([Claude Code docs](https://www.anthropic.com/engineering/claude-code-best-practices)) — the production-grade version of the same loop; see "Give Claude a way to verify its work" (this repo's `verify` stage) and its context-window management guidance.

**Philosophy**
- Anthropic, *Effective context engineering for AI agents* ([Sep 29, 2025](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)) — "context rot": recall degrades as tokens accumulate; context is "a finite resource with diminishing marginal returns." This is the citation behind `TARGET_WORKING_CONTEXT = 24_000` and compaction-as-addresses.
- Model Context Protocol intro ([modelcontextprotocol.io](https://modelcontextprotocol.io/docs/getting-started/intro)) — "like a USB-C port for AI applications." Read to understand what this repo's *static* `plugins.py` registry is a local, dependency-free alternative to.
- SQLite WAL mode ([sqlite.org/wal.html](https://www.sqlite.org/wal.html)) — why `store.py:113` runs `PRAGMA journal_mode=WAL` for crash-safe, append-only state.

**Failure modes**
- Simon Willison's agent archive ([simonwillison.net/tags/agents/](https://simonwillison.net/tags/agents/)) — his working definition: "LLMs calling tools in a loop to achieve a goal," plus years of collected real-world loop and prompt-injection failures. Search his prompt-injection tag for why `web_fetch` output is capped and treated as untrusted data.
- For community signal on the exact models in `catalog.py`, search **r/LocalLLaMA** for "Qwen3-Coder-30B-A3B agentic" and "Devstral Small 2" — `docs/02-research-findings.md` holds the repo's own model-selection research; the subreddit is where small-model agentic behavior (tool-call adherence, drift) is discussed in the wild.

---

# Chapter 1 — What This Thing Is

## 1.1 The problem it exists to solve

The problem statement (`docs/problem-statement.txt`) is unusually specific: build an agentic coding IDE for **small and medium open-weight models with a *total* parameter count ≤ 80B** (total, not active — a 480B-total MoE with 35B active is illegal), running only on **free-tier or pay-as-you-go APIs or local hardware**, achieving high accuracy on hard multi-step coding tasks while keeping **token cost first and execution time second** as low as possible. Scoring punishes cost with an exponent of 2.5 against a $0.15 reference (`docs/00-executive-summary.md`), and there are hard eval ceilings: 2700 seconds and $0.50 per task.

Small models fail in well-understood ways, and the repo catalogues them in its own docs: long contexts rot them (`docs/02` §4.3, cited at `orchestrator.py:32`), they drift across multi-step plans, they emit malformed JSON and hallucinate tool arguments, and they "lazily" elide code. The thesis of this repository is that **each of those failure modes is a harness problem, not a model problem**. Every module in `src/taknee/` exists to patch one specific small-model weakness:

| Small-model failure | Harness mechanism | Where |
|---|---|---|
| Long contexts rot recall | Fixed 24K-token working context; compaction to addresses, not summaries | `orchestrator.py:32`, `compaction.py` |
| Open-ended tool loops spiral | No free-form loop; tools exist only at named pipeline stages | `orchestrator.py` docstring |
| JSON/tool-call non-adherence | Strict output contracts + tolerant parsers + retry ladder | `patches.py`, `_extract_json`, `router.py` |
| Lazy / drifting edits | SEARCH/REPLACE blocks with exact anchors, fuzzy fallback | `PATCH_PROMPT`, `patches._fuzzy_find` |
| Repeating the same failed step | Fingerprint counting → `CapHit` | `orchestrator.py:296` |
| Cost blowout | Free-first routing, per-task governors 2400 s / $0.40 / 120 steps | `router.py`, `_check_caps` |

The repo's own naming encodes the thesis. It is called **Huginn & Muninn** after Odin's ravens: **Huginn** (thought) is the part that flies out and acts — the task pipeline; **Muninn** (memory) recalls context, spans, and session history — the SQLite store and retrieval index (`README.md`). The package and CLI keep the old codename `taknee` for compatibility.

## 1.2 What it is not

- **Not a chatbot.** Chat messages that look like questions are deliberately *diverted away* from the code pipeline: `api.py:294` (`_is_question`) checks for question starters, and `_thread_reply`'s docstring explains why — "Questions must never enter the patch pipeline: forcing 'what did we make here?' through retrieve→patch makes the model invent SEARCH/REPLACE edits for whatever retrieval surfaced (observed as no-op blocks on unrelated files)."
- **Not a frontier-model wrapper.** `catalog.py` hard-fails at import time if any entry exceeds 80B total params (`assert_catalog_compliance`, called in `__main__.py:16` before the server starts). Claude, GPT, and Gemini are in the ban list with reasons.
- **Not a framework.** There is no plugin loading, no graph DSL, no declarative YAML pipelines. `plugins.py` is 27 lines and static. The only things that look like a framework are two dicts in `tools.py` (`DISPATCH`, `TOOL_SCHEMAS`).
- **Not an editor fork.** The editor is stock prebuilt VSCodium; all agent behavior lives in the Python kernel plus a thin extension (`docs/decisions.md` D1, which documents the rejection of forking `microsoft/vscode` on the evidence of EclipseSource's fork-treadmill analysis).

## 1.3 The one-sentence thesis

*Give a small, cheap model a short context, one small job, a strict output format, and a test to pass — and wrap it in a deterministic state machine that routes, records, gates, and stops — and it will do real coding work for roughly zero dollars.*

---

# Chapter 2 — The Walkthrough: One Task, End to End

The entrypoint is `src/taknee/__main__.py`, wired as a console script (`taknee = "taknee.__main__:main"` in `pyproject.toml`). Running `uv run taknee` does three things: parses `--host` (default `127.0.0.1`) and `--port` (default `47821`), calls `catalog.assert_catalog_compliance()` to fail fast on any >80B catalog entry, then starts uvicorn with the FastAPI `app` from `api.py`. There is no Makefile, no Dockerfile, and no `.env.example` — configuration lives in `~/.taknee/settings.json` (written by the Settings screen) and per-workspace state lives in `<workspace>/.taknee/`.

## 2.1 The hop-by-hop life of a request

**Hop 0 — the editor syncs the workspace.** `apps/extension/src/extension.ts` hardcodes `KERNEL_URL = 'http://127.0.0.1:47821'` and posts the first workspace folder's `fsPath` to `POST /workspace` on activation *and* on a 4-second interval. The kernel validates it is a directory (`api.py:135`), stores it in module state, and resets the store. Per-workspace isolation is by construction: the SQLite DB goes to `<workspace>/.taknee/taknee.db` (`api.py:43`) and the retrieval index to `<workspace>/.taknee/index.json`.

**Hop 1 — task creation.** `POST /tasks` with `{prompt, auto_approve}` (Pydantic models `TaskIn`). `store.create_task` inserts a row in `tasks` (status `created`, stage `start`), `add_message` records the user's prompt, and an `Orchestrator(store, Router(), workspace, auto_approve=...)` is constructed and stashed in `_state["orchestrators"][task_id]`. The orchestrator then runs on a **daemon thread** (`threading.Thread(target=_run, daemon=True, name=f"task-{task_id}")`), because the HTTP handler must return immediately. A **watchdog** thread joins with a 180-second timeout and fails the task if a provider call hangs (`api.py:229-237`).

**Hop 2 — the state machine.** `Orchestrator.run()` (`orchestrator.py:103`) is a `while stage not in ("done", "stopped")` loop over a literal string variable. The stages, in order: `retrieve → localize → patch → approval → apply → verify`, with `diagnose` as the repair lane back into `patch`. Before every stage it calls `_check_caps()` and increments `_steps`. Two exceptions carry control flow: `CapHit` ("A governor fired: stop the task, persist state, never run forever") and `Parked` ("A human decision is required; task state is durable until resolved").

**Hop 3 — retrieve.** `_stage_retrieve` builds-or-loads a `retrieval.Index` for the workspace. If the saved `index.json` is missing or `stale_files()` is non-empty, it rebuilds. Then `index.search(prompt, k=8)` runs the BM25-lite + identifier-Jaccard + import-hop scorer (`retrieval.py:107`), and each hit chunk is written into the working context via `_remember(f"chunk:{header}", text)`. A pinned `repo_map` (skeleton view of files→symbols, 900-token budget) is added, plus the pinned `AGENTS.md` digest if the project has one, plus the pinned `task_prompt`. A heuristic on the prompt (`"web", "search online", "scrape"...`) may trigger a pinned `web_search` span.

**Hop 4 — localize.** The first LLM call. `_stage_localize` sends `LOCALIZE_PROMPT` ("Reply ONLY with JSON: {\"files\": [...]}") plus `_context(prompt)` — the assembled working context — through `_llm(...)` on the `primary` tier. The reply is parsed by `_extract_json` (first `{` to last `}`, `json.loads`, `.get("files", [])` — tolerant, never raises), capped at `files[:8]` with the comment "small models dump the whole repo otherwise" (`orchestrator.py:273`). Each localized file's first 4000 chars are read (through the jail) and remembered unpinned.

**Hop 5 — routing, the sub-loop inside every call.** `_llm()` (`orchestrator.py:415`) estimates tokens (`len(text)//4` via `compaction.estimate_tokens`), then loops up to **4 attempts**: `router.pick(tier, est_tokens, iteration)` → add an `llm` span with `route_reason` → call `chat_fn` → on `RateLimited`, `router.record_failure(provider, retry_after)` and continue; on `ProviderError`, either cool the whole provider down (401/403, or a refused Ollama connection) or skip just that `(provider, model)` pair (404) and continue; on success, `router.record_success`, end the span with tokens and USD, `store.add_usage`, and return. `Router.pick` (`router.py:69`) is pure feature-based logic — no LLM meta-router, rejected explicitly in `docs/decisions.md` D3 as "circular, costs money, hides the decision": filter providers by `_PROVIDER_ORDER`, skip cooling providers, skip providers without keys, skip models whose `context_window < est_tokens + 2_048`; at `iteration == 0` sort cheapest-healthy (`price_in > 0, total_params`), on repair iterations sort strongest-first (params descending) — "harder attempts get the strongest eligible model." If no API lane is healthy, local Ollama models become the zero-cost recovery path regardless of the `prefer_local` toggle.

**Hop 6 — patch.** `_stage_patch` sends `PATCH_PROMPT` — the SEARCH/REPLACE contract with rules like "SEARCH must match existing file content exactly" and "keep blocks small" — plus the context. The reply goes to `patches.parse()`, whose regex `BLOCK_RE` extracts `PatchBlock(file, search, replace)` tuples, with a guard that a bare language-tagged fence (``` ```python ```) is prose, not a patch (`patches.py:77`). Then **stuck detection**: `patches.hash_text(result.content)` is counted in `self._fingerprints`; at `fingerprint_limit` (3) repeats of the identical patch output, `CapHit("patch stage repeated identical output (stuck)")` fires (`orchestrator.py:296`).

**Hop 7 — approval (the park).** `_stage_approval` writes the hunks — `blocks_to_review_payload` with per-block `fingerprint` — into the `approvals` table as `pending`, sets task status `awaiting_approval`, and **raises `Parked`**. The daemon thread ends; nothing is lost. The extension's Review webview polls `GET /approvals`, renders hunk-level accept/reject, and `POST /approvals/{id}/resolve` calls `orch.resume(task_id, decision, accepted_ids)`. `resume()` (`orchestrator.py:187`) rebuilds the accepted `PatchBlock` list, records `accepted`/`rejected` fingerprints, resets the time-cap clock base (with an honest `TODO` about wall-clock vs active seconds), and re-enters `run(start_stage="apply")`. Crucially, `api.py:431` reconstructs the Orchestrator from durable state if the kernel restarted — "kernel restarted — reconstruct the runner from durable task state (req 6)."

**Hop 8 — apply.** `_stage_apply` calls `patches.apply_blocks(blocks, read_file=self._read_jailed, write_file=self._write_jailed)`. The applier is strict and never raises: `_fuzzy_find` tries exact `content.find(search)` first, then a whitespace-insensitive line-by-line window compare ("catches indentation drift and internal spacing like 'f( )' vs 'f()'"); failures become `ApplyReport.failed` entries with reasons like `"SEARCH anchor not found"`. New files are detected by empty SEARCH and written directly, parent directories implicit. A unified diff is generated via `difflib` and pinned into context as `last_diff`. If **nothing** applied, `CapHit("patch produced no applicable file changes")`.

Then comes a genuinely original check (`orchestrator.py:331-358`): the **deliverable guard**. If the prompt looks like a create/build request and mentions specific paths, the applied files must match — `CapHit("task requested a solver but patch created no solver file")`. And if a "create something new" prompt produced only edits to *existing* files, `CapHit` fires with a comment citing the observed failure: "the model docstring-ing an unrelated password checker." This is the harness noticing that the model gamed the done-condition — verification beyond the test suite.

**Hop 9 — verify.** The done-check is **the project's own test command**, parsed from `AGENTS.md` by `agents_md.py` (`test_cmd`, e.g. `pytest -q`, extracted from headings matching `TEST_HINTS` and shell-shaped lines or backticks). No test command → verify passes trivially, and the final summary says so honestly: "No project test command was configured, so only patch application was verified" (`orchestrator.py:183`). With a command: unless `auto_approve`, even **running the tests parks the task** — "even the test command (a side-effecting terminal run) is gated" (`tests/test_orchestrator_tools.py:207`). Approved runs execute with `subprocess.run(cmd, shell=True, cwd=self.workspace, timeout=300)`; the last 3000 chars of output are pinned as `last_fail_log`.

**Hop 10 — the repair loop or the stop.** Verify failed → `iteration += 1`; past `MAX_REPAIR_ITERATIONS = 3` → `_stop()` writes status `stopped` and the message "The raven did not return: verify failed after 3 repair attempts." Otherwise → `diagnose` (a `utility`-tier call whose system prompt *forbids* emitting patches: "Do not emit SEARCH/REPLACE blocks. Reply with plain text"), whose output is **pinned** into context, then back to `patch`. Verify passed → status `done`, and the assistant message is "The ravens have returned. Changed: app.py. Verification passed."

One more look at `_context()` (`orchestrator.py:484`): every LLM call's user message is assembled by `compaction.assemble(items, TARGET_WORKING_CONTEXT=24_000)` — pinned items always ship in full; non-pinned items are kept newest-first until budget runs out; the rest are demoted to one-line `[compacted]` previews. Compaction stats are recorded as events. This is the *entire* memory system for a task: a list of `ContextItem`s in RAM, with durable memory living in SQLite and the index, rehydratable on demand.

---

# Chapter 3 — Architecture and Philosophy

## 3.1 The shape of the system

Classify it precisely and the design falls into place:

- **Single-agent pipeline, multi-model, not multi-agent.** There is one `Orchestrator` and one task context. "Multi-agent orchestration" from the problem statement is satisfied by *multi-stage specialization with model routing* — localize/patch run on the `primary` tier, diagnose and `/bytheway` on the `utility` tier, embeddings/rerank on `local` — rather than by independent agents with their own conversations. There is no orchestrator-workers fan-out. A thread (`thread_id`, `parent_task_id`, `followups`) chains *sequential runs*, each a fresh pipeline over shared durable memory.
- **A graph, but hard-coded.** The state machine *is* a graph (with cycles: `patch → apply → verify → diagnose → patch`), but it is written as a `while` loop over a string rather than a node/edge structure like LangGraph. Why: at three repair iterations the graph has seven nodes; a data structure would be ceremony. The loop is also honest about state — everything durable goes through `store`, so the loop is re-enterable via `run(start_stage=...)`.
- **Sync pipeline on async host.** FastAPI handlers are plain `def` (threadpool) and the orchestrator runs on a daemon thread; nothing in the pipeline is `async`. For a single-user loopback tool this is the right call — blocking calls are simple, and the `store` serializes access with an `RLock` (`store.py:_locked`) because orchestrator threads share one SQLite connection with the API thread.

## 3.2 The philosophies visible in the code

**"The harness is the product."** The models are commodity — that is the point of the ≤80B constraint. The value is everything around them: catalog compliance, routing with visible reasons, jail, caps, approvals, traces. The repo says this out loud in `docs/00-executive-summary.md`: "The system compensates for weak models — that's the product."

**"Deterministic wrappers around a non-deterministic model."** Every stage transition is deterministic Python. The model is consulted only inside a stage, produces exactly one artifact (a JSON list, or a set of S/R blocks), and the harness validates the artifact before acting on it. Compare ReAct, where the model also chooses the next action — here `orchestrator.py` chooses; the model only fills in the step.

**"Files are the source of truth; the filesystem is memory."** The workspace's real files are the state that matters; everything else (index, spans, approvals) is derived or recorded state in `<workspace>/.taknee/`. Code is never *summarized* into memory — `compaction.py`'s docstring: "Code is addressable; summarizing code is how small models invent APIs — so we don't." Demoted context items become addresses (`[compacted span #<id>: 40-token preview...]`) rehydratable from the index/store.

**"Verify, don't trust."** Verification is the project's *own test command* (from `AGENTS.md`), not an LLM critic — `docs/decisions.md` D2: "Verification is tests, not an LLM critic." Small "reviewer" models rubber-stamp; exit codes do not. The deliverable guard extends this: even a green test run can't pass a create-task that created nothing.

**"Fail closed."** Unknown model → refused (`is_allowed` returns `False, "not in catalog — add with published total params first"`). Unknown tool name → error string (`tools.execute`). File write outside the workspace → `ValueError` escapes `_write_jailed` deliberately ("caller records a failed block"). No API key → the route chip says so instead of silently falling back to something the user didn't configure. Catalog violation → the kernel refuses to *start*.

**"Cheap model for routing / expensive model for hard steps" — inverted correctly.** There is no model for routing at all: the router is a function. Model *spending* is graduated by stage tier: `primary` for localize/patch (the hard parts), `utility` for diagnose/status/question-answering, `local` (Ollama) as the free recovery lane. And repair iterations escalate *upward* (strongest healthy model), not sideways — the opposite of the common "retry with the same cheap model" bug.

**"Routing must be visible."** Every `Route` carries a human-readable `reason` string, e.g. `"primary stage, est 8123 tok, iteration 0 -> cheapest healthy: qwen/qwen3-coder-30b-a3b-instruct (30.5B) @ groq, cooling=openrouter"` — stored on every span as `route_reason` and surfaced by the extension's status-bar Route chip. The problem statement's requirement 3.b ("the routing decision can never be hidden") is satisfied structurally, not by a debug flag.

## 3.3 What was *not* chosen, and why the choice is coherent

- **ReAct / free tool loops** (SWE-agent-class): rejected in D2 with the Agentless evidence — higher accuracy at *lower* cost without letting the LLM pick arbitrary next actions. Coherent because the models are small: a 7–30B model in an open loop repeats calls, hallucinates paths, and burns the $0.50 cap.
- **Planner–coder–reviewer swarms / Mixture-of-Agents debate**: rejected in D2 — "Triples tokens. Small 'reviewer' models rubber-stamp." Coherent under a cost-dominated score with exponent 2.5.
- **An LLM meta-router**: rejected in D3. Circular (a model call to avoid a model call), slow, and hides the decision the PS requires be visible.
- **Vector RAG as the retrieval story**: rejected in D4 — the PS says "beyond keyword or plain vector," English embeddings miss identifiers like `token_for`, and whole-file dumps violate the "no excess code" criterion. Chosen instead: AST-shaped chunks + BM25-lite + identifier Jaccard + one import-graph hop — the honest v1 of the hybrid plan (v2 embeddings/reranker are specified but not implemented; see Appendix).
- **Unified diffs as the edit format**: SEARCH/REPLACE won (D6) on aider's published benchmarks — "weak/small models apply S/R blocks far more reliably — exact anchors instead of drifting line numbers" (`patches.py` docstring). Unified diff requires the model to count lines before writing code; S/R requires it to copy the anchor exactly. Small models copy better than they count.
- **Summarizing compaction / LLMLingua**: rejected in D5 (addresses, not summaries).
- **MCP as the tool protocol**: not adopted — `plugins.py` is a static, 27-line registry. For a local, single-process kernel with 12 tools, a client/server JSON-RPC protocol would add process boundaries and a dependency for zero capability. The registry's docstring states the boundary that matters: "The kernel owns policy, approvals, workspace jail and execution; plugins only provide capabilities." Adopting MCP later is a `plugins.py` + `tools.py` refactor, not an architecture change.
- **async everywhere**: rejected implicitly. A loopback kernel serving one editor, where each request performs seconds-long blocking LLM calls, gains nothing from an event loop and loses debuggability.

---

# Chapter 4 — Tech Stack and Why

**Language: Python ≥ 3.11** (`requires-python` in `pyproject.toml`). Gives: the retrieval stack the plan calls for (tree-sitter, ONNX runtimes) is Python-native; subprocess/jail code is short; the whole kernel is ~2,500 readable lines. Costs: GIL-bound threading (fine here — the workload is I/O-bound LLM calls), and slow imports (litellm's import is explicitly measured in the code as "~30s+", hence the lazy `_get_litellm()` in `providers.py`). Alternative not chosen: a TypeScript kernel inside the extension process — rejected in `06-plan-of-record.md` D2 because "extension holds no logic" is a stated invariant, and because a kernel that is a separate process *survives IDE restarts* (the resume requirement) and can run headless for evals.

**Runtime shape: loopback FastAPI server.** `api.py` binds `127.0.0.1` only; the extension talks HTTP to `http://127.0.0.1:47821`. Gives: the kernel is editor-agnostic (there is also a standalone `console.html` test UI at `/`), CORS is trivially safe-ish on loopback, and eval harnesses can POST `/tasks` without an editor at all. Costs: the kernel must be started separately (`uv run taknee`), and CORS `allow_origins=["*"]` on loopback means *any* local web page could POST to the kernel — see Chapter 7.

**Package manager: uv** (`uv.lock` at the repo root, `uv sync --group dev` in the README). Gives: reproducible lock, single binary, fast syncs. Cost: one more tool to learn. Alternative: pip + requirements — loses the lock; poetry — slower, and uv is already the de-facto standard in the small-model community this project targets.

**Model transport: LiteLLM 1.98.0 (locked), with a raw-`httpx` fallback.** `providers.chat()` prefers litellm when installed (prefix map `LITELLM_PREFIX`: `groq/`, `openrouter/`, `nvidia_nim/`, `ollama/`, ...) so provider quirks (auth headers, slug formats, error shapes) are maintained upstream. The fallback path posts directly to `ENDPOINTS[provider]` — the OpenAI-compatible `/chat/completions` — proving the point that OpenAI-compatibility *is* the universal adapter of this era. Costs: litellm is a heavy transitive dependency (the lock pulls in openai, jinja2, boto3, huggingface-hub, tiktoken-class artifacts); its slow import is hidden behind a lazy global. What we would have used instead: hand-maintained per-provider adapters (what `ENDPOINTS` + the httpx path already sketch), or the `openai` SDK pointed at base URLs — but the fallback already *is* that, minimal.

**Providers: free-tier-first (Groq, OpenRouter, NVIDIA NIM, Ollama), PAYG-guarded (Mistral, Cerebras, DeepInfra, Fireworks, Together).** `catalog.FREE_PROVIDERS` and `PAYG_PROVIDERS` encode the cost philosophy; `settings.DEFAULTS["allow_paid"] = False` makes PAYG opt-in. Gives: ~$0 marginal cost, instant onboarding for evaluators. Cost: free tiers 429 often — which is exactly why `RateLimited` + cooldowns + fallback are first-class.

**Schemas: Pydantic ≥ 2.9 at the API edge; hand-rolled OpenAI function dicts inside.** API inputs (`TaskIn`, `ApprovalIn`, `ToolCallIn`...) are Pydantic models validated by FastAPI. Tool definitions are plain dicts matching the OpenAI function-calling format (`tools.TOOL_SCHEMAS`), because every provider in `ENDPOINTS` speaks that dialect. No `jsonschema` in our own code (the lock only carries it transitively). Cost: two schema idioms; benefit: zero ceremony at the edge that matters (the model), full validation at the edge that matters (HTTP).

**Storage: SQLite (WAL) for state; JSON file for the index.** `store.py:113` sets `PRAGMA journal_mode=WAL`; five tables — `tasks`, `spans`, `events`, `approvals`, `messages` — one shared connection guarded by an `RLock`. The retrieval index persists to `<workspace>/.taknee/index.json` (hashes, chunks, imports). Gives: crash-safe append-only history ("a crash leaves a consistent prefix → exact resume"), zero-install ops, and the traces UI reads the same tables live and post-hoc ("no gaps by construction," per the plan). Cost: single-process scale ceiling — irrelevant for a loopback tool. Alternatives rejected: Postgres (ops burden for a contest artifact), pure logs (no queryable state for resume).

**Frontend: VSCodium + a TypeScript extension with webviews.** `apps/extension/package.json` contributes one activity-bar container (`taknee`) with four webview views — `taknee.chat`, `taknee.traces`, `taknee.review`, `taknee.settings` — plus `routeChip.ts` for the status-bar routing indicator. Dev-only dependencies: `typescript ^5.6.0`, `@types/vscode ^1.85.0`, `@types/node ^22.0.0` — **no runtime npm dependencies at all**; the panels are hand-rolled HTML-in-webview calling `fetch` against the kernel. That is the "the extension holds no logic" invariant made concrete: no state, no keys, no agent code in the editor.

**Streaming: deliberately absent.** No SSE, no token streaming — tasks are long-running jobs polled via `GET /tasks/{id}` and `GET /tasks/{id}/spans`. Streaming would couple the UI to a single provider call's tokens; this system's unit of progress is the *span*, not the token. (The chat panels poll messages; a status reply like "Huginn takes flight. Currently in retrieve" comes from `_status_reply` in `api.py:275` — narration as data, not as a token stream.)

---

# Chapter 5 — Libraries: What Each One Actually Handles

The runtime dependency list is five entries long (`pyproject.toml`); the `uv.lock` resolves it to ~50 packages, almost all transitive. Grouped by job:

**LLM / SDK / provider transport**
- `litellm` 1.98.0 — the multi-provider transport. *Job here:* one call path (`providers.chat`) across Groq/OpenRouter/NIM/Mistral/Cerebras/DeepInfra/Together/Ollama, preserving the OpenAI response shape (`choices[0].message`, `usage`). *Failure it prevents:* N hand-maintained provider adapters drifting apart — the exact bug class that makes multi-provider agents break silently. *Touch it when:* adding a provider not in `ENDPOINTS`/`LITELLM_PREFIX`; *leave it alone when:* everything routes — the raw-httpx fallback already covers you if litellm misbehaves. Note the import discipline: `_get_litellm()` lazy-imports on first call ("litellm's import is slow (~30s+)"), so `taknee --help` stays instant.
- `httpx` 0.28.1 — the raw HTTP client for the fallback transport, `web_fetch`, `test_key`, and the extension-sync path. *Prevents:* nothing dramatic; it is the boring, correct client (sync, timeouts, `follow_redirects`). *Touch when:* changing provider endpoints or adding headers like `EXTRA_HEADERS["openrouter"]` (`HTTP-Referer`, `X-Title` — "some keys 404 without a referer").

**Agent / graph / orchestration — none.** There is no LangGraph, AutoGen, CrewAI, or OpenAI Agents SDK. The orchestrator is 530 lines of stdlib Python. This is a deliberate, documented stance (Chapter 3.3); if you add a framework you are overriding a decision, so update `docs/decisions.md` D2/D3 with new evidence first.

**Tools / shell / browser**
- **stdlib `subprocess`** — the entire tool execution story: `run_terminal` (`shell=True`, `cwd=workspace`, timeout), `search_code` (shells out to **ripgrep**, with a pure-Python `_search_code_fallback` when `rg` isn't on PATH — a nice degradation ladder), git tools, verify runs, and even `web_search` (curl against DuckDuckGo's HTML endpoint, regex-parsed). *Prevents:* dependency sprawl and daemon processes; every tool is a function that returns a string. *Cost:* `shell=True` is powerful and dangerous — the deny-list is regex, and the *real* control is the approval gate (Chapter 7).

**Parsing / validation**
- `pydantic` ≥ 2.9 — FastAPI request models (`TaskIn`, `ApprovalIn`, `ToolCallIn`, `KeyIn`, `ByTheWayIn`). *Prevents:* malformed HTTP bodies reaching the kernel; gives free OpenAPI docs at `/docs`. *Leave alone:* it's glue.
- **`re` (stdlib) — the real parsing engine of this repo.** `patches.BLOCK_RE` parses SEARCH/REPLACE blocks; `retrieval._PY_DEF/_JS_DEF/_IMPORT` do the "AST-ish" chunking and import extraction; `settings._KEY_PATTERNS` (`nvapi-`, `sk-or-v1-`, `gsk_`) auto-extract keys from pasted snippets; `tools.DENY_PATTERNS` block destructive commands; `agents_md` regex-parses project conventions. *Philosophy:* for bounded, machine-checked formats, a strict regex plus a strict fallback ("exact → whitespace-tolerant → recorded failure") beats an LLM parser and a parser library you'd have to trust.

**Persistence**
- **`sqlite3` (stdlib)** — the event store. *Prevents:* lost work on crash, unauditable behavior, unresumable tasks. *Touch when:* adding state that resume needs; *never* bypass `_locked`.
- `difflib` (stdlib) — unified diffs for the review UI and the pinned `last_diff`.

**Observability / tracing**
- **None installed — by design.** No LangSmith, Phoenix, or OpenTelemetry. The `spans`/`events` tables *are* the tracing system, with exactly the OTel vocabulary (parent_id, timestamps, attributes as JSON, token/cost attributes) and none of the dependencies; `GET /tasks/{id}/spans` and the Traces webview are the "exporter." *Failure it prevents:* opaque agent behavior — every LLM call is queryable with its `route_reason`, tokens, and USD. If you outgrow SQLite, the migration target is OTel semantics, not a vendor SDK bolted onto the loop.

**Infra**
- `uvicorn` ≥ 0.32 — the ASGI server for the loopback API.
- `hatchling` — build backend; the wheel force-includes `console.html` (`pyproject.toml` force-include section), so the packaged CLI still serves the test UI.
- `pytest` ≥ 8.3 (dev group) — 84 tests, all offline (see Chapter 9 on the fake-model pattern).
- **No dotenv, no Docker, no CI config in this repo.** (`docs/linux-setup.md` covers manual cross-platform setup; the roadmap reserves Day 6 for cross-platform run-throughs.) This is a contest artifact, not a deployed service — and the code is honest about it.

**The extension's package.json** deserves its own sentence: runtime dependencies `[]` (none), devDependencies only `typescript`/`@types`. In a field where "IDE agent" usually means shipping Electron-scale bundles, a no-dependency extension talking to a stdlib-Python kernel is the "small tools + strong loop" philosophy applied to the frontend too.

---

# Chapter 6 — Prompts, Contracts, and "The Brain"

The prompts live as module-level constants at the top of `orchestrator.py` — three of them, each a *contract*, not a personality.

## 6.1 The three contracts

**`LOCALIZE_PROMPT`** — output contract: `"Reply ONLY with JSON: {\"files\": [{\"path\": \"...\", \"why\": \"...\", \"symbols\": [\"...\"]}]}."` The model that matters here cannot do reliable native JSON mode, so the harness (a) demands the shape in the prompt, (b) parses defensively with `_extract_json` (substring from first `{` to last `}`, `json.loads` inside try/except, `.get(key, default)`), and (c) clamps the result `files[:8]`. When the model is messy, the parser is tolerant, the clamp is absolute, and a garbage reply degrades to "no localization" — which the pipeline survives by falling back to retrieval chunks.

**`PATCH_PROMPT`** — the most carefully engineered text in the repo. It defines the SEARCH/REPLACE format inside fences, then adds *rules that are actually ACI design decisions*: "SEARCH must match existing file content exactly (including indentation)"; "To create a new file, use an empty SEARCH section"; "Create parent directories implicitly by naming the desired relative file path"; "One block per logical change; keep blocks small"; "Do not rewrite whole files unless the file is under 40 lines"; "No explanation outside the fences." Each rule forecloses a known small-model failure: lazy whole-file rewrites, broken relative paths, kitchen-sink diffs, chatty output breaking the regex. Recovery when the model is messy anyway: `parse()` ignores prose and language-tagged fences, `_fuzzy_find` rescues indentation drift, and failed blocks are *reported per-block* so three good hunks and one bad hunk become a partial apply, not a crash.

**`DIAGNOSE_PROMPT`** — a *negative* contract: "Do not emit SEARCH/REPLACE blocks. Reply with plain text." Note what this says: the failure being prevented is the model's own momentum — after several patch-stage turns, diagnose would happily emit another patch; the prompt refuses the artifact it must not produce.

## 6.2 How structure is forced without native tools

The deepest design point is `_chat_with_readonly_tools` (`orchestrator.py:404`), whose docstring should be memorized:

> "Retrieval and file reads already happen in named stages. Advertising native tools here caused some models to return only tool calls, which this stage pipeline does not consume, leaving an empty patch response."

So: `TOOL_SCHEMAS` exists, `tool_defs()` and `read_only_tool_defs()` exist, `catalog` even carries a `native_tools` flag per model — and the pipeline **never sends the tools**. The model is called with messages only; agency comes from the stage machine. This is the "harness is the product" idea in its purest form: the repo built a complete tool-calling layer and then chose not to use it, because *the model's* tool-call adherence is the weakest link in the chain. The empty-patch failure it describes is real (it's why `empty_patch_limit` and the `diagnose` lane exist too — belt and suspenders).

## 6.3 The knowledge contract: AGENTS.md

`agents_md.py` turns the project's own `AGENTS.md` into structured `ProjectRules(test_cmd, build_cmd, style_rules, instructions)` via hint-matched headings (`TEST_HINTS`, `BUILD_HINTS`, `STYLE_HINTS`), shell-line and inline-backtick extraction, and a final fallback that scans for any test-runner-looking line. Three uses: (1) `pinned_digest()` — "The always-in-context summary (survives compaction)" — is pinned into every stage's context; (2) `test_cmd` *is* the verify stage's done-check; (3) style rules are to be enforced by review. The parser is deliberately tolerant ("headings vary by project") — the philosophy is that conventions belong to the *project* and the harness is their enforcer, which is the same idea as Claude Code's `CLAUDE.md` and aider's conventions file.

## 6.4 Where "the brain" actually is

If you search for intelligence in this repo, you find it distributed: the *model* contributes maybe 30 words per artifact (a file list, some hunks, a diagnosis); the *context assembly* (`_remember` + `compaction.assemble` + the decision ledger — `decision_ledger` renders decisions as a numbered, append-only list "so nothing is misremembered") decides what the model even sees; and the *state machine* decides what happens next. A first-year CS student should internalize this: in a well-built harness, prompt text is the smallest part of the cognition.

---

# Chapter 7 — Safety, Limits, and Ops

## 7.1 The threat model, concretely

What could a runaway agent do here, worst case? Write files inside the workspace, run a shell command in the workspace, commit/checkout git, and fetch web content. It cannot (by construction) touch files outside the workspace, spend more than ~$0.40 or 2400 seconds or 120 steps per task, run a command without a human click (by default), or secretly use a model the catalog forbids. Each of those is an explicit mechanism:

**1. The path jail.** Every tool path goes through `jail_path` (`tools.py:65`): resolve, then `p.relative_to(ws)` — on escape, it *clamps back* to `ws / name` rather than raising; the orchestrator's `_write_jailed` lets the `ValueError` escape so failed blocks are recorded. Tests assert both: `test_jail_blocks_escape` feeds `../../etc/passwd` and expects clamping inside.

**2. The side-effect split + approvals.** `READ_ONLY` vs `SIDE_EFFECT` sets (`tools.py:28-29`); `needs_approval(name)` is membership in `SIDE_EFFECT`. Patches and verify commands land in the `approvals` table as `pending` and the task *parks* until a human resolves them (`Parked`). The API enforces it independently too — `POST /tools` refuses side-effect names without `approved: true` (`api.py:538`). Hunk-level review means the user can accept two of three hunks (`select_blocks`, `decision: "partial"`), and rejected hunks are recorded with fingerprints.

**3. The deny-list.** `DENY_PATTERNS` blocks `rm -rf /`-class deletion, `mkfs`/`dd if=`/`shutdown`/`reboot`/`format`, `git push --force`, `chmod 777 /`, and `curl|sh`/`wget|sh`. Honest assessment: a regex deny-list on `shell=True` is bypassable (encoding tricks, variable indirection) — the code treats it as a *first* rail, with the approval gate as the *structural* rail. The `test_deny_list` test pins the obvious cases.

**4. Output and context caps.** `OUTPUT_MAX = 20_000` chars on every tool result ("cap command output to ~5K tokens"); `list_files` truncated at 500 entries; verify logs pinned at 3000 chars; diffs at 6000; localization files at 8; context at `TARGET_WORKING_CONTEXT = 24_000`. A tool that dumps a huge blob cannot rot the context — the SWE-agent ACI lesson applied to every channel.

**5. Governors.** `_check_caps` (settings `caps`: `max_seconds 2400`, `max_usd 0.40`, `max_steps 120`, `max_llm_calls 200`, `fingerprint_limit 3`, `empty_patch_limit 3`) — deliberately inside the eval ceilings (2700 s / $0.50) with margin. Cost accounting is exact because every `ChatResult` carries `tokens_in/tokens_out/usd` computed from the catalog's per-1M prices, and `store.add_usage` accumulates per task. Stuck detection is two-layer: identical patch fingerprints (content-hash) and empty patches. Plus a kernel-level watchdog (180 s provider hang) and stale-worker recovery on `GET /tasks` (>300 s unupdated `running` task → `failed`).

**6. The catalog as policy.** Compliance is enforced at *three* points: process start (`assert_catalog_compliance`), every route selection (`models_for` only returns catalog entries), and every raw call (`chat()` validates the model against the catalog "before any request" — `providers.py` docstring). Budget is policy-as-code: `is_allowed` refuses unlisted models; `BANNED` documents the refusals with reasons (including the subtle one: `gpt-oss-120b` banned while its 20b sibling is legal, `qwen3-next-80b` legal "exactly at the cap" — total params, not active).

**7. Secrets.** Keys live in `~/.taknee/settings.json` (0600 where the OS supports it), are written only via the Settings screen, are normalized out of pasted snippets (`normalize_provider_key` — the API even answers "Did not ping Groq. Pasted N characters but no `gsk_` key was found" rather than guessing), and **never leave the kernel**: `settings.masked()` replaces every key with `"set"`, `providers.test_key` returns messages not keys, and the docstring is blunt — "Keys are never logged and never returned in full." The extension holds no keys at all.

**8. Rate limits as a first-class state.** `RateLimited` carries the provider's `retry-after`; the router cools the provider for 45 s (or longer if told); fallback continues on another lane "without losing the task's progress" (PS req 3.c) because state lives in the store, not in the failed call.

## 7.2 What's weaker than it looks (ops honesty)

- `run_terminal` uses `shell=True`; the deny-list is advisory relative to a determined model. The approval gate is the real boundary — keep `auto_approve` off for untrusted tasks.
- `web_search`/`web_fetch` are classified **READ_ONLY** (`tools.py:28`), so fetched content could flow into context without a gate — a prompt-injection surface (Willison's classic). Mitigations present: output capped at `OUTPUT_MAX`, content pinned at most 6000 chars, and stages never *execute* fetched instructions (the pipeline only consumes JSON and S/R blocks). Still, if you extend this repo, treat tool output as data, never as instructions.
- CORS `allow_origins=["*"]` on a loopback port: any local page could hit the API while the kernel runs. Loopback-only + no secrets echoed is the defense; an origin allowlist or a token would close it properly.
- `git_commit` runs `git add -A` — everything, including files the task didn't touch. Gated, but blunt.

---

# Chapter 8 — How to Read the Code, In Order

Read in dependency order; every file assumes only the ones above it.

1. **`pyproject.toml`** — the whole dependency story in 33 lines. Then `uv run taknee` mentally.
2. **`src/taknee/__main__.py`** — 25 lines. Note `catalog.assert_catalog_compliance()` before the server starts: policy before services.
3. **`src/taknee/catalog.py`** — the policy artifact. Look at `is_allowed()` next: the three-part refusal (banned → unlisted → over-cap).
4. **`src/taknee/settings.py`** — `DEFAULTS` is the de-facto config schema; note `caps` and `allow_paid: False`. Then `masked()`.
5. **`src/taknee/providers.py`** — `chat()` is the only door to a model. Trace both transports (litellm / httpx), then `test_key()` (the Settings screen's honesty: "Did not ping" vs "Ping OK").
6. **`src/taknee/router.py`** — `Router.pick()`: the filter → sort → reason pipeline. Compare iteration 0 vs `iteration > 0` sorting; that asymmetry *is* the cost policy.
7. **`src/taknee/store.py`** — the five-table schema (tasks/spans/events/approvals/messages) is the system's true data model; read `SCHEMA` as the architecture diagram.
8. **`src/taknee/retrieval.py`** — `chunk_file` (AST-ish spans, 60-line cap) → `search()` (BM25-lite + Jaccard + import-hop) → `repo_map()`.
9. **`src/taknee/compaction.py`** — 86 lines; `assemble()` is the pinned/floating/address algorithm. Read with `orchestrator._remember`/`_context`.
10. **`src/taknee/patches.py`** — `parse()` then `_fuzzy_find()` then `apply_blocks()`: the strict→tolerant→recorded ladder.
11. **`src/taknee/agents_md.py`** — the project-contract parser.
12. **`src/taknee/tools.py`** — the three dicts (`READ_ONLY`/`SIDE_EFFECT`, `DISPATCH`, `TOOL_SCHEMAS`) and `jail_path`.
13. **`src/taknee/orchestrator.py`** — now everything is vocabulary. Read `run()` first, then `_llm()`, then the five `_stage_*` methods, then `resume()`.
14. **`src/taknee/api.py`** — the HTTP skin; note the watchdog, `_is_question`/`_thread_reply` (questions never enter the pipeline), and orchestrator reconstruction in `/approvals/{id}/resolve`.
15. **`src/taknee/plugins.py`**, then **`apps/extension/src/*.ts`** — the capability registry and the six-panel UI (chat/traces/review/settings/routeChip).
16. **`tests/`** — start with `test_orchestrator_tools.py`: the scripted-fake-model pattern shows the whole machine offline. Then `test_patches.py` and `test_retrieval_agents.py`.
17. **`docs/decisions.md` + `docs/06-plan-of-record.md`** — the "why" behind everything you just read.

## Glossary of internal names

- **Huginn / Muninn** — acting pipeline / memory (store + index). "The raven did not return" = task stopped; "The ravens have returned" = done.
- **kernel** — the Python server (`src/taknee/`); the extension is a *host*, not the brain.
- **stage** — a named state in the machine (`retrieve|localize|patch|approval|apply|verify|diagnose`); also the `stage` column on tasks and the kind `stage` on spans.
- **span** — one recorded operation (kind: `stage|llm|tool|approval|compaction`), with parent, model, provider, `route_reason`, I/O, tokens, USD, timing.
- **event** — append-only task journal entry (`status|route|cap|compaction|approval|note`).
- **pinned / floating / address** — context items that never compact / compact newest-first / were demoted to a preview.
- **hunk** — one PatchBlock in the review UI; **fingerprint** — sha1-based identity of a patch (or a full reply) used for stuck detection and reject bookkeeping.
- **park / Parked** — suspension for a human decision; the durable twin of "awaiting_approval."
- **CapHit** — a governor fired; always terminal for the task, always recorded.
- **jail** — the workspace path containment (`jail_path`, `_read_jailed`, `_write_jailed`).
- **tier** — model class in the catalog (`primary|utility|embed|rerank|local`) used by the router.
- **route chip** — the extension's status-bar indicator fed by `route_reason`.
- **/bytheway** — the isolated one-question endpoint (retrieval + one `utility` call, no task, no memory side effects).

---

# Chapter 9 — How to Extend It

## 9.1 Add a tool (the canonical extension)

Six touchpoints, all in existing patterns — adding a `lint_file` tool:

1. **Implementation**: a function `def _lint_file(file_path: str, *, workspace: str) -> str:` in `tools.py`, using `jail_path(file_path, workspace)`, returning a string, capping output at `OUTPUT_MAX`.
2. **Dispatch**: add `"lint_file": _lint_file` to `DISPATCH`. `execute()` inspects the signature and injects `workspace` (and `index_ref` if accepted) automatically.
3. **Classification**: read-only → add to `READ_ONLY`; runs commands → `SIDE_EFFECT` (free approval gate from `needs_approval` + `POST /tools` enforcement).
4. **Schema**: a `TOOL_SCHEMAS["lint_file"]` entry in OpenAI function format — even though the pipeline doesn't advertise tools, `GET /tools` and the console UI do, and a future tool-using stage will.
5. **Capability**: optionally list it in `plugins.py` `_PLUGINS` under a plugin name; that's all `plugins.py` wants.
6. **Test**: extend `test_orchestrator_tools.py`'s tool-safety section (`test_execute_read_and_unknown` shows the shape).

Rule of thumb from this codebase: *read-only tools return data; side-effect tools return blocked-without-approval or a record of what they did.*

## 9.2 Add a specialist "agent"

There is no agent registry to join — a specialist is **a stage (or an endpoint) plus a tier**. Pattern: write a new prompt constant, a `_stage_thing` method that calls `self._llm(task_id, span, "thing", "utility", [...])` and pins its result, and a case in the `run()` loop — e.g. a "review the hunks against `rules.style_rules`" pass before approval. If the specialist must never edit, copy `DIAGNOSE_PROMPT`'s move: forbid the artifact in the prompt. The tier ladder is your cost lever: cheap `utility` for critique, `primary` only for generation.

## 9.3 Swap or add a model

Add a `ModelEntry` to `catalog.MODELS` with the *published total* param count from the HF card (MoE: total, not active), context window, tier, providers, and per-1M prices. The router picks it up automatically: `context_window` gates it against `est_tokens + 2_048`; price feeds the cheapest-healthy sort; params feed the strongest-first repair sort. New provider additionally needs: an `ENDPOINTS` entry + `LITELLM_PREFIX` prefix in `providers.py`, an entry in `_PROVIDER_ORDER`/`FREE`/`PAYG_PROVIDERS`, and a label in `settings.PROVIDER_LABELS`. Never bypass the catalog — `is_allowed` and the startup assertion are the compliance spine.

## 9.4 Add evals

The repo's test pattern is your eval harness seed: `test_orchestrator_tools.py` builds an `Orchestrator` with a `FakeRouter` (returns a fixed `Route`) and a `fake_chat` that replays scripted `providers.ChatResult` replies against a temp workspace — **the entire pipeline runs offline with zero keys** (84 tests prove it). To grow into evals: swap `fake_chat` for a real provider, point the workspace at a task repo with an `AGENTS.md` test command, and record the triple the plan of record demands (accuracy / $ / seconds) — all three already exist as data: verification exit code, `store.get_task(tid)["usd"]`, and `created_at → updated_at`. The `spans` table gives per-stage routing and token breakdowns for free. Failure drills worth adding, per the roadmap: 429 storms (cooldown behavior), bad keys (the 401/403 provider-cool path), huge repos (stale-index paths).

## 9.5 Extending memory and retrieval

Retrieval v2 is *specified* (docs D5: local Qwen3-Embedding-0.6B + Qwen3-Reranker-0.6B + RRF fusion + LSP hooks) and *stubbed by design*: `retrieval.py`'s docstring says "v2 adds local embeddings + reranker + LSP hooks **behind the same `search()` interface**," and the catalog already carries `embed`/`rerank` tiers. That is your extension lane: implement `search()` with RRF over lexical + vector scores; nothing else in the kernel changes. Memory extensions bolt onto `_remember`/`assemble` — the invariant to preserve: *pinned survives compaction; code becomes addresses, never summaries.*

---

# Appendix

## A. Annotated file tree

```
E:\taknee-ide\
├── pyproject.toml            # taknee 0.1.0; 5 runtime deps; hatchling; console script
├── uv.lock                   # locked resolution (litellm 1.98.0, fastapi 0.141.1, httpx 0.28.1…)
├── README.md                 # quickstart: uv sync / pytest / taknee; enforced constraints
├── .vscode/launch.json       # F5: Extension Development Host for apps/extension
├── src/taknee/
│   ├── __main__.py           # CLI: catalog compliance check → uvicorn on 127.0.0.1:47821
│   ├── api.py                # FastAPI: workspace/settings/keys/tasks/spans/approvals/bytheway/tools
│   ├── orchestrator.py       # the state machine + stage prompts + caps + deliverable guard
│   ├── router.py             # free-first, cooldown-aware, explainable route selection
│   ├── catalog.py            # ≤80B allowlist + ban list + tiers + prices (policy-as-code)
│   ├── providers.py          # litellm/httpx transports; RateLimited; test_key
│   ├── store.py              # SQLite WAL: tasks, spans, events, approvals, messages
│   ├── retrieval.py          # AST-ish chunks, BM25-lite+Jaccard+import-hop, repo_map, index.json
│   ├── compaction.py         # pinned/floating/address context assembly; decision ledger
│   ├── patches.py            # SEARCH/REPLACE parse → fuzzy apply → review payloads
│   ├── agents_md.py          # AGENTS.md → test/build commands + style rules
│   ├── tools.py              # 12 tools, jail, deny-list, output caps, OpenAI schemas
│   ├── plugins.py            # static capability registry (web/workspace/git/terminal)
│   ├── settings.py           # ~/.taknee/settings.json; key masking; default caps
│   └── console.html          # standalone kernel test UI served at /
├── apps/extension/           # VSCodium extension (TS, zero runtime deps)
│   ├── package.json          # activity bar + chat/traces/review/settings webviews
│   └── src/extension.ts      # kernel URL, 4s workspace sync, panel registration
├── tests/                    # 9 files, 84 tests, fully offline
├── docs/                     # 00-executive … 06-plan-of-record + decisions/ADR evidence
└── .taknee/                  # this workspace's own db + index (the kernel has run here)
```


## B. Environment variables and configuration

**There is no `.env.example` and the kernel reads no required environment variables** — configuration is deliberately file/UI-based:

- **API keys**: `~/.taknee/settings.json` under `providers.<name>.key` for `groq`, `openrouter`, `nim`, `mistral`, `cerebras`, `deepinfra` — written via the Settings screen (`POST /settings/providers/{name}/key`), never env vars, never echoed. Legacy flat field names (`groq_api_key`, `nvidia_nim_api_key`, `openrouter_api_key`) are still read by `get_key()` for compatibility.
- **Provider knobs**: `ollama_base_url` (default `http://127.0.0.1:11434/v1`), `allow_paid` (default false), `prefer_local` (default false).
- **Caps**: `max_seconds 2400.0`, `max_usd 0.40`, `max_steps 120`, `max_llm_calls 200`, `fingerprint_limit 3`, `empty_patch_limit 3` — tunable live via `POST /settings` (caps merged).
- **CLI**: `taknee --host 127.0.0.1 --port 47821` (`__main__.py` argparse).
- *Indirectly*, litellm may consult provider SDK env vars internally, but the kernel always passes the key explicitly (`headers = {"Authorization": f"Bearer {key}"}`), so nothing is required.

## C. Annotated reading list (why each link matters *for this codebase*)

- **Building Effective Agents** (Anthropic) — the workflow-vs-agent distinction is the repo's founding decision (D2); the ACI advice explains `PATCH_PROMPT` and `OUTPUT_MAX`.
- **Agentless (arXiv:2407.01489)** — the orchestrator's direct ancestor; its localize/repair/validate phases map 1:1 onto `_stage_localize`/`_stage_patch`/`_stage_verify`; its result (32.00% / $0.70) is the cost-effectiveness argument D2 cites.
- **SWE-agent (arXiv:2405.15793)** — the ACI concept that justifies `jail_path`, output caps, and tool schemas even when unused.
- **Aider edit formats** — the provenance of SEARCH/REPLACE and the evidence behind D6; also shows the *alternative* (udiff) this repo rejected.
- **How to Build an Agent** (Thorsten Ball) — the minimal loop this repo deliberately exceeds: it adds what a 400-line agent lacks for *small* models — routing, caps, approval parking, compaction, verification.
- **Effective context engineering for AI agents** (Anthropic) — "context rot" is the cited justification for `TARGET_WORKING_CONTEXT = 24_000` (`orchestrator.py:32` references docs/02 §4.3) and for compaction-as-addresses (D5).
- **Model Context Protocol intro** — the standard this repo's `plugins.py` is a local alternative to; read before extending tools beyond 12.
- **Claude Code best practices** — "give the agent a way to verify its work" is exactly the `verify` stage; its failure-mode list (kitchen-sink sessions, polluted context) matches the repo's `/bytheway` isolation and question-diversion design.
- **SQLite WAL** — why exact resume after a crash works (`PRAGMA journal_mode=WAL`, `store.py:113`).
- **ReAct (arXiv:2210.03629)** — read to understand the alternative the repo measured and rejected for weak models.
- **r/LocalLLaMA** (search: "Qwen3-Coder-30B-A3B agentic", "Devstral Small 2") — community empiricism on the exact models in `catalog.py`; complements `docs/02-research-findings.md`.


## D. Open questions and inconsistencies found in the repo

Found while reading; each is a real, checkable observation, not a complaint:

1. **`MAX_TOOL_ROUNDS = 4` (`orchestrator.py:31`) is defined but never used** — consistent with the "never advertise tools" decision, but a vestige; either remove it or it is a trap for readers expecting a tool loop.
2. **`caps.max_llm_calls` (200, `settings.py:69`) is never enforced** — `_check_caps` checks seconds/USD/steps only. An easy first PR: count `_llm` entries per task.
3. **`Router.fallback_chain()` is never called** — `_llm()` implements its own 4-attempt loop; the method is dead code awaiting either use or removal.
4. **`compaction.SOFT_TRIGGER`/`should_compact` are unused by the orchestrator** — `_context` assembles to a fixed 24,000 tokens rather than 70% of the *selected model's* window, which is what D7 and `compaction.py`'s docstring promise. Per-model-window compaction is partially implemented at best.
5. **Retrieval v2 (embeddings, reranker, RRF, LSP) is documented but absent** — `retrieval.py` is honest about it ("v2 (Day 4-5) adds…"), and the catalog already carries the `embed`/`rerank` tiers waiting to be used.
6. **The bounded task splitter (plan-of-record D3's addition for long-horizon tasks) is not implemented** — `orchestrator.py` has one pipeline; `tasks.parent_task_id`/`thread_id` implement chaining, not decomposition.
7. **`BANNED` wildcard entries can't match** — `is_allowed` does exact dict lookups, so `"anthropic/claude-*"` is documentation, not enforcement. (Safe today because Claude/GPT/Gemini are also *unlisted* — fail-closed — but the wildcard syntax promises more than the code delivers.)
8. **`web_search`/`web_fetch` are READ_ONLY** — fetched web content can enter pinned context without a human gate (prompt-injection surface; mitigated by output caps and by the pipeline only consuming JSON/S-R artifacts, but worth an explicit policy decision).
9. **CORS `allow_origins=["*"]` on the loopback kernel** — any local browser page could drive the API while it runs. Loopback + masked keys limit exposure; a token or origin check would close it.
10. **`resume()` resets `created_at` to now** — keeping the time cap from insta-tripping after a multi-day park, with an honest `TODO: track active vs wall-clock seconds properly (docs/03 §7)`. Cost of the workaround: a parked task could legally run another 2400 s of *active* time.
11. **`providers.chat` accepts `transport` and `client` params** used by tests/console; the main path always goes litellm-then-httpx internally — fine, but the parameter surface is wider than the docstrings describe.
12. **README says the kernel "indexes that folder only"** — true of the index, but `web_search`/`web_fetch` and the console `/tools` endpoint are workspace-independent by design; worth one clarifying sentence.

---

*End of the book. One repo, fifteen modules, five dependencies, 84 passing tests, and one idea — the model proposes, the harness disposes.*
