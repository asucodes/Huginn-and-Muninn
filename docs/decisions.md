# Architectural decisions

Judges asked for alternatives considered, not the first LLM default. This file is the source of those answers.

## D1. IDE shell: VSCodium + our extension, not a VS Code source fork, not Atom

**Choice.** Ship [VSCodium](https://vscodium.com/) (MIT binaries of Code-OSS, telemetry off, **no Copilot**) and install the Taknee extension. The agent lives in `src/taknee/`. The editor is a host, not the product.

**Rejected: fork `microsoft/vscode`.** EclipseSource, 17 Dec 2024, *Is Forking VS Code a Good Idea?* — forks lose the Marketplace, lose proprietary extensions (C++, Live Share, Remote, Copilot), and inherit a rebase treadmill. An 8-day contest cannot own that repo.

**Rejected: Atom / Pulsar.** Atom was archived December 2022. Pulsar is a community fork with a small ecosystem. Building an agent IDE on a dead editor is extra risk with no scoring benefit.

**Rejected: stock Eclipse Theia IDE.** Theia is a real custom-IDE platform, but current Theia IDE ships [Theia AI](https://eclipsesource.com/blogs/2025/03/13/introducing-theia-ai/). The brief said we may use a prebuilt IDE **without** bundled AI so our abstraction stays ours.

**Rejected: CLI-only.** Dashboard (8%), HITL hunks (3%), clickable tags (6%), and “IDE usability” (4%) need a visual surface.

**Rejected: Cursor / Windsurf / Continue.** They already contain AI. We would be scored as a reskin and Y26s could not defend internals.

## D2. Orchestrator: Agentless-style state machine, not ReAct / ChatDev / MoA

**Choice.** Stages: retrieve → localize → patch → approve → apply → verify → diagnose (bounded) → retrieve. Tools exist, but only at named stages.

**Why.** Xia, Deng, Dunn, Zhang, *Agentless* (arXiv:2407.01489, 2024): localization, repair, patch validation **without** letting the LLM pick arbitrary next actions. On SWE-bench Lite they reported **higher accuracy at lower cost** than heavier open-source agents. Small models fail at open-ended tool loops (repeat the same call, hallucinate paths, burn the $0.50 cap).

**Rejected: planner–coder–reviewer swarm.** Standard LLM default. Triples tokens. Small “reviewer” models rubber-stamp.

**Rejected: Mixture-of-Agents debate.** Cost-first scoring (`w_C = 0.65`, `ε = 2.5`) punishes extra proposals.

**Verification is tests, not an LLM critic.** `AGENTS.md` test command is the done-check.

## D3. Routing: features, not an LLM router

**Signals:** task class (regex), estimated tokens, repair iteration, provider cooldown, remaining $ and time, `prefer_local`, allowlist.

**Visible:** status-bar chip + every span’s `route_reason` in the trace view.

**Rejected: “ask 70B which model to use”.** Circular, slow, hides the decision, costs money.

**Fallback:** 429/5xx marks the provider cooling; the same stage retries another provider. Snapshot is unchanged.

## D4. Retrieval: AST-shaped chunks + BM25 + identifier Jaccard + 1-hop imports

**Choice.** Per-workspace index. Chunk on function/class boundaries (regex CST; tree-sitter can replace later). Rank with BM25 plus identifier-set overlap. Expand one import hop.

**Why this is “semantic” for code.** English embeddings miss `token_for`. BM25 hits identifiers. AST keeps a function intact (cAST / tree-sitter literature: line windows split signatures from bodies). Import graph is execution flow, which the PS asked for.

**Rejected: naive vector RAG.** The PS literally says “beyond keyword or plain vector”. Dumping whole files also fails the “no excess code” question.

**Isolation.** Index is built from the opened folder only (`<workspace>/.taknee/`). Workspace B cannot see A’s chunks. Test: `tests/test_retrieval.py`.

**Recovery.** On test failure, re-query with identifiers from the fail log (`recover_query`).

## D5. Compaction: addresses, not summaries

**Pinned forever:** task prompt, `AGENTS.md`, user pins, accepted/rejected hunks, last fail log.

**Compacted:** raw chunk bodies → `span_id` + preview. Hydrate from the index when needed.

**When:** projected prompt > 70% of the *selected* model window, or after diagnose.

**Rejected: LLMLingua / “summarize the chat”.** Summaries of code are how small models invent APIs. Code is addressable.

## D6. Models: published total params ≤ 80B, free/PAYG/local

Allowlist in `src/taknee/catalog.py` with sources. Ban list includes DeepSeek-V3/R1, Qwen3-Coder-480B (480B total MoE — **illegal even if 35B active**), Nemotron 120B, Claude, GPT-4, Gemini (unpublished size).

Qwen3-Next-80B-A3B is **legal**: Hugging Face card says 80B total / 3B active, exactly at the cap.

Local: 7B/8B Q4 on 8GB VRAM. 32B/70B/80B are API only.

**Cost policy.** Prefer free-tier and Ollama so `C → 0`. The formula’s cost term then vanishes and we spend the time budget on repair, not on paid tokens. Hard stop at 2400s / $0.40 (margin under 2700s / $0.50).

## D7. HITL before any side effect

Patches land in an approval payload, **not** the working tree. Accept / reject per hunk. Rejected previews become constraints on the next patch. Tests are a side-effecting terminal command: gated unless the user enables auto-run.

## D8. Keys

Mandatory settings webview writes `~/.taknee/settings.json`. Eval teams without this screen are disqualified. We treat that as a first-class feature, not a footer.
