# 02 — Research Findings (web research, 2026-08-25)

Working notes with sources. Facts marked ⚠ are from search-result summaries we could not fully verify — recheck before publishing in final docs. This file doubles as evidence of "we compared alternatives" for the trade-off-analysis score.

## 1. Models ≤80B total params (the eligible roster)

| Model | Total params | Context | Native tools | Evidence |
|---|---|---|---|---|
| **Qwen3-Coder-30B-A3B-Instruct** | 30.5B (MoE, ~3B active) | 256K native (1M w/ YaRN) | Yes (Qwen-Agent templates) | HF model card; SWE-bench Verified ~51.6% (OpenHands, 100 turns) to ~78.8% (stronger scaffold) — scaffold quality swings +27pts, which is exactly our thesis |
| **Qwen3-Next-80B-A3B** | ~80B total ⚠ (right at the limit — verify exact count before use; if >80B, drop it) | long | Yes | ⚠ |
| **Devstral Small 2 (24B)** | 24B dense | 128K | Yes | SWE-bench Verified ~68% standalone / 72.2% (Devstral 2 full variant ⚠), SWE-bench Codex High 73.7% (HF card, Dec 2025 release 2512) |
| **Llama 3.3 70B** | 70B | 128K | Yes | Served free on Groq |
| **gpt-oss-20b** | 21B total (MoE, 3.6B active) — eligible; **gpt-oss-120b is ~117B total → banned** | 128K | Yes | arXiv 2508.10925 model card |
| Qwen3-32B / Qwen3-30B-A3B (general) | 32B / 30.5B | 40K+ | Yes | general-purpose fallbacks |
| Local small: Qwen3 4B/8B, Qwen2.5-Coder-7B/14B | ≤14B | 32K+ | partial | for 16GB/8GB local box |

2026 additions to watch (verify availability + param counts before relying on them): Qwen3.6-35B-A3B / Qwen3.6-27B dense (⚠ community-reported SWE-bench Verified ~77-96% — unverified), "North Mini Code" ⚠, Gemma 4 (Cerebras lists gemma-4-31b ⚠). If Qwen3.6 A3B is real and ≤80B, it likely becomes our primary — confirm on HF/OpenRouter before the eval.

**Working picks:** primary Qwen3-Coder-30B-A3B (agentic, huge context, cheap, fast MoE), secondary Devstral Small 2 (best SWE-bench per param ⚠), utility tier Qwen3-8B/4B-class for cheap subtasks (titles, classification, summarization), local tier via Ollama for zero-cost/offline.

## 2. Providers (free first — cost is the #2 score lever)

Free tiers (all OpenAI-compatible APIs):

| Provider | ≤80B models ⚠ (lineups drift) | Free limits ⚠ | Notes |
|---|---|---|---|
| **Groq** | Llama-3.3-70B, Qwen3-32B, Qwen3-30B-A3B?, gpt-oss-20b | ~30 RPM, ~14.4K RPD, ~12-30K TPM | Fastest serving (280-1000 tok/s LPU); no card needed |
| **Cerebras** | Qwen3 family, gpt-oss, gemma-4-31b ⚠ | free tier w/ per-model daily caps ⚠ | extreme speed (1000+ tok/s), great for time score |
| **OpenRouter :free** | 28+ free models incl. Qwen3/DeepSeek-distills | 20 RPM, 50-200 RPD (more with $10 credit) | single key → many models; universal tool-calling layer |
| **Mistral La Plateforme** | Devstral Small 2, Mistral Small 3.x | free "Experiment" tier ⚠ (phone verify) | direct Devstral access |
| GitHub Models | various | low RPM ⚠ | backup only |
| NVIDIA build.nvidia.com | many | free credits ⚠ | backup |

PAYG fallback (per 1M in/out, 2026-08, ⚠ verify at integration time):
- DeepInfra: Qwen3-Coder-30B-A3B ≈ **$0.07-0.12 in / ~$0.50 out** — cheapest for primary model
- Mistral direct: Devstral Small 2 = **$0.10 / $0.30**
- Groq paid / Cerebras paid / Together / Fireworks for speed-critical hops

**Strategy:** free-tier pool first (spread load across providers to dodge per-key RPM), PAYG ladder only when free pool is exhausted or latency-critical, per-task $ governor stops PAYG spend at ~$0.40 hard / warns at $0.10. Expected eval cost: **≈ $0**.

Signup friction matters (evaluators create keys for OUR supported providers): Groq, OpenRouter, Cerebras are instant email signups → make these the documented core three; Mistral optional fourth; Ollama local optional fifth.

## 3. IDE base: why Code OSS fork

- **Atom: dead.** Archived by GitHub Dec 2022; old Electron; no security updates; forking it would be indefensible in Q&A.
- **Code OSS (microsoft/vscode minus Microsoft build bits):** MIT; ~monthly releases; VS Code at v1.110+ (Feb 2026). Copilot/Chat is a Microsoft-proprietary extension NOT in Code OSS; the open-source core keeps AI scaffolding behind proposal flags — strip/verify at build time (check `product.json`, built-in extensions list). This satisfies "no initial AI features, our own abstraction."
- **VSCodium** = proven recipe: patches product.json (telemetry off, Open VSX marketplace), builds all platforms. Its CI scripts are our template. Fork maintenance strategy for 8 days: **freeze on one stable tag, never rebase upstream.**
- **Marketplace legality:** forks must NOT use Microsoft Marketplace (ToS); use **Open VSX**. VSCodium already wires this.
- **Void editor** (VS Code fork w/ AI): archived June 2026, but its repo is a reference for fork mechanics (diff rendering, Ollama integration). **PearAI** similar. We take inspiration for patch structure only.
- **Eclipse Theia:** viable, VS-Code-ext-compatible, but smaller ecosystem, TheiaAI built in (we'd strip), and judges know VS Code. Higher novelty risk, no upside for us.
- **Custom Electron+Monaco:** rebuild file tree/terminal/SCM/diff from scratch — weeks of work we don't have.
- **CLI-only:** PS demands clickable file:line tags, dashboards, settings screen, diff review → GUI required. Our engine will still be CLI-capable for dev/eval harness (best of both).

Verdict (ADR-1 in 05): **Code OSS fork, frozen tag, VSCodium-style build scripts, GitHub Actions matrix (win-x64, linux-x64, macos x64+arm64 unsigned), Open VSX, our extension pre-bundled.**

## 4. Small-model agent techniques (what actually works, with sources)

From Aider's docs/benchmarks, Claude Code behavior, OpenHands/SWE-agent patterns:

1. **Edit format is a first-class accuracy lever.** Aider's search/replace "diff" format massively helps weaker models (GPT-3.5-class jumped when switched to it); unified diffs reduced GPT-4-Turbo "lazy edits" 3×. → We use SEARCH/REPLACE blocks with exact-match apply, fuzzy fallback, and one repair-retry with error feedback. Never "whole file rewrite" except tiny files.
2. **Separate reasoning from editing (architect/editor split).** Aider Architect mode: strong(er) model reasons, cheap model edits. Maps perfectly to our multi-agent split on free tiers.
3. **Context rot is real for small models** → keep effective working contexts SHORT (target ≤16-24K even though Qwen3-Coder accepts 256K); retrieval quality > window size. Our memory bank exists to make every turn's context small and dense.
4. **Compaction done right = state, not summary.** Claude Code's evolution: early-compact with buffer, preserve recent turns + restore "compact boundary" on resume; community consensus: transcript summarization alone loses state → structured state files survive. → Our memory bank (03 §5) is structured-first, digest-second.
5. **Verification loops**: run tests/build/typecheck as the source of truth; parse errors → targeted fix prompts. SWE-bench evidence: scaffold quality swings Qwen3-Coder-30B from ~51.6% to ~78.8% — the agent framework, not the model, is the multiplier. This is the entire premise of our project.
6. **Checkpoints/backtracking via git**: commit (checkpoint) each subtask; revert bad branches; re-plan after N failed attempts at the same subtask instead of blind retries (PS explicitly scores "diagnose instead of blindly retrying").
7. **Loop detection**: hash (tool, args) pairs; 3 identical calls = stuck → escalate to watchdog → replan or backtrack. Cap total steps (~120), agent spawns (~24), tokens, $ and wall-clock.
8. **Tool-call adherence**: use providers' native function calling (Qwen3, Devstral, gpt-oss trained for it; Groq/Cerebras/OpenRouter support it); JSON-mode where offered; strict parser + 1 repair retry; never free-form JSON prompts.
9. **Parallelism across providers** splits subtasks across free tiers → beats per-key RPM limits and wall-clock time.

## 5. Code retrieval (12% — biggest single architecture component with orchestration)

- **Aider repo map** (the pattern to beat/generalize): tree-sitter extracts symbols → reference/def graph → **PageRank ranks files/symbols** → binary-search a token budget → dynamic map per conversation. Proven; cheap (no embeddings needed); great for navigation. [aider.chat/2023/10/22/repomap.html]
- **Hybrid lexical+semantic is standard practice**: BM25 with code-aware tokenization (camelCase/snake_case splitting, symbol boosting) + embeddings, fused via **Reciprocal Rank Fusion**, then a **cross-encoder reranker**. Local CPU reranking is practical: Qwen3-Reranker-0.6B (ONNX; pairs with Qwen3-Embedding family). Embeddings: Qwen3-Embedding-0.6B (multilingual+code, ONNX available via HF) or jina-embeddings-v2-base-code (161M, code-specialized, MIT ⚠license check). Both run offline in-process via transformers.js/ONNX Runtime — no API cost, no external calls, index stays per-repo.
- **Chunking**: AST-aware chunks (tree-sitter: functions/classes with qualified names + signatures; split oversized defs; include import context header per chunk). Never whole files (explicit PS judging criterion).
- **LSP grounding — our differentiator**: living inside a VS Code fork means language servers are already running; definitions/references/call-hierarchy give *ground-truth* navigation no embedding approximates. Route "where is X used/what implements Y" queries to LSP first; fall back to index. No major agent does this today → original-thinking points (PS rewards it).
- **Agentic narrow-down loop**: retrieval isn't one-shot — the Navigator agent iterates search→read skeleton→expand (like Claude Code's grep/read loop, which works precisely because it's iterative). Add **poor-result detection**: coverage check (needed symbols present? confidence low?) → re-query with expanded/rephrased queries or different strategy.
- **Incremental indexing**: file-watch → re-parse changed files only (merkle-ish per-file hashes), keeps index fresh + cheap.

Our full pipeline design: `03-system-architecture.md §6`.

## Sources (main)

- Groq rate limits/models: console.groq.com/docs/rate-limits, /docs/models; grizzlypeaksoftware.com (2026 breakdown); pricepertoken.com/endpoints/groq/free
- OpenRouter :free limits: openrouter.ai/pricing; klymentiev.com/blog/openrouter-free-tier (2026-06); litellm issue #9035 (20 RPM/200 RPD)
- Qwen3-Coder-30B-A3B: HF model card (256K ctx, MoE 30.5B/3B active); HF discussion #30 (51.6% OpenHands repro); openrouter.ai model page (78.8%); swebench.com leaderboard
- Devstral Small 2: HF mistralai/Devstral-Small-2-24B-Instruct-2512 (73.7% Codex High); mistral.ai/news/devstral-2507 (prior gen 53.6%); swebench.com (56.4% mini-SWE-agent)
- gpt-oss: arXiv 2508.10925 (120b = 116.8B total → banned; 20b = ~21B → allowed)
- DeepInfra pricing: deepinfra.com/pricing; pricepertoken.com compare page; Mistral pricing: mistral.ai/pricing + aipricing.guru guide ($0.10/$0.30 Devstral S2)
- VS Code fork mechanics: VSCodium repo/issue #519; ghuntley.com/fracture; ArchWiki VS Code page; code.visualstudio.com v1.110 release notes; Void status: cursor-alternatives.com + vgtc.io forks landscape 2026 H1
- Aider: edit formats docs; repomap blog; unified-diffs doc; architect-mode post; benchmarks pages
- Claude Code compaction: platform.claude.com/docs compaction; zread.ai source analysis; hyperdev.matsuoka.com context-protection post
- Cerebras: inference-docs.cerebras.ai (model list incl. gpt-oss-120b — banned; qwen/gemma families ⚠ verify current lineup + free tier)
