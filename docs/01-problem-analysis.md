# 01 — Problem Analysis

Source: "Takneek PS - High Prep" (PDF, retrieved 2026-08-25). This is our team's working distillation; the original PDF is `docs/problem_statement_download`.

## The problem in one paragraph

Modern agentic coding tools assume frontier models with huge context windows and strong single-model reasoning. Small open-weight models (≤80B total params) can't do multi-step reasoning reliably alone. Build an **agentic coding IDE tuned from the ground up for these small models**, running only on free-tier/pay-as-you-go APIs or local hardware (16GB RAM / 8GB VRAM), maximizing accuracy on hard multi-step coding tasks while keeping **token cost first, execution time second** as low as possible.

## Constraints (hard rules)

1. Every model anywhere in the system: **total params ≤ 80B** (for MoE: TOTAL, not active — Qwen3-30B-A3B qualifies at 30.5B total; gpt-oss-120b does NOT at ~117B total).
2. Only **free-tier or pay-as-you-go** provider APIs or **local hardware**. No subscription APIs.
3. Local models must comfortably run on **16GB RAM + 8GB VRAM**.
4. Per-codebase index isolation — no leakage between projects.
5. **Mandatory settings screen** for users to enter per-provider API keys → **disqualification if missing** (evaluators use it to test our system).
6. Per-task evaluation ceilings: **$0.50 and 2700 seconds**; exceeding either = task scored as failure (A=0).
7. Side-effect commands (write/delete file, git push, package install, state-changing terminal commands) **always require human approval** before running.

## Scoring

Final performance formula (per task; PDF's exact rendering is partially garbled — recheck the original figure):

```
Score ≈ 10 · f(Accuracy) / (1 + (C/C_ref)^γ + (T/T_ref)^γ)   [γ = 2.5]
  A = accuracy ∈ [0,1] on hidden eval tasks
  C = total $ cost across all agent calls;   C_ref = $0.15
  T = wall-clock seconds prompt→output;      T_ref = 1320s
  α = 0.35, β = 0.65 (weighting constants in the formula)
```

**Implications, in order of leverage:**
- Cost and time enter with exponent 2.5 → as C→$0.15 or T→1320s the denominator explodes. Keeping **C ≈ $0 (free tiers)** is the single biggest score lever after accuracy.
- Accuracy multiplies everything → verification loops (run tests/build, read errors, fix) and backtracking are the accuracy levers.
- Working targets we set for ourselves: **C ≤ $0.05 typical / hard stop $0.40; T ≤ 1200s typical / soft stop 2400s** (safety margin under ceilings, graceful best-effort finish rather than halt-fail).

Hidden eval: medium-to-hard, long-horizon tasks on real-world codebases, multi-step, not single-shot fixes. SWE-bench-flavored, run by evaluators inside our IDE with their own API keys.

## The 11 requirements → our feature map (traceability)

| # | Requirement | Our feature (owner doc) |
|---|---|---|
| 1 | Multi-agent orchestration; stuck/runaway detection & safeguards | Orchestrator + plan DAG + Watchdog (03 §4) |
| 2 | Model/hosting constraints ≤80B, free/PAYG/local | Model registry with auditable param manifest (03 §2) |
| 3 | Smart routing, transparent, graceful fallback, settings screen | Router + routing log + live badges + Settings UI (03 §3) |
| 4 | Automatic context compaction without losing relevant info | Memory Bank (structured state) + digest compaction (03 §5) |
| 5 | Code retrieval pipeline, per-repo index | Hybrid retrieval stack (03 §6) |
| 6 | Long-horizon multi-session tasks; resume after crash/close | Event-sourced SQLite + task journal (03 §7) |
| 7 | Manual context control; clickable file/line tags both directions; `/bytheway` | Context manager panel + structured refs + ephemeral threads (03 §8) |
| 8 | Autonomous tool use (terminal, files, web, git) + approval gates | Tool layer with risk classes + approval queue (03 §9) |
| 9 | AGENTS.md project memory, survives compaction | Pinned project memory layer (03 §5.3) |
| 10 | HITL review: diffs, block-level accept/reject, partial approval continuation | Git-based checkpoint/diff review flow (03 §10) |
| 11 | Observability dashboard: full call hierarchy, drill-down, live thoughts, context lifetime, tokens/time | Dashboard webview over event log (03 §11) |

## Judging rubric weights (relative emphasis)

- Final system performance end-to-end: **20%**
- Core agentic architecture **36%** — orchestration 14, retrieval 12, routing 5, compaction 5
- Supporting features **17%** — manual context 6, tool autonomy 6, HITL 3, AGENTS.md 2
- Dashboard/UI/UX **12%** — observability 8, general usability 4
- Docs/code quality/presentation **15%**

## Process rules that can sink us (from the PS Guidelines)

1. If a presenter can't answer a question about a feature that exists in the codebase → **that feature is scored null**. → Every member must own and be able to defend components; docs must be study material, not decoration.
2. Functionality over aesthetics.
3. Trade-off explanations are scored; they explicitly reward trying/comparing >1 approach per core component and original thinking over "the LLM's first suggestion." → Our research notes (02) and ADRs (05) are scoring assets, keep them honest.
4. Dedicated **Y26 Q&A** on implementation specifics; freshers must have actually contributed.
5. Presentation ≤10 min, ≥2 presenters; Q&A adjusts ALL section scores.

## Risks & standing concerns

- **Exact scoring formula** is garbled in text extraction — re-verify from the original PDF before tuning governor thresholds.
- **Evaluator keys**: they paste their own keys for the providers WE support → pick providers with instant, friction-free signup (Groq/OpenRouter/Cerebras) and document key setup for Linux precisely (required deliverable).
- **Free-tier rate limits during eval**: parallelism must be spread across providers; queue + backoff + fallback ladder is core, not an afterthought.
- **8 days**: fork build pipeline is the longest-lead item → set up CI producing nightly artifacts by Day 1 (04-roadmap).
